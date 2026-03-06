# HBK Parser Redesign - Streaming Memory-Based Approach

## Проблема

Текущая реализация парсера HBK использует:
1. Извлечение всех файлов во временную директорию (~75MB на диске)
2. 7zip subprocess с чтением из temp файлов
3. Таймауты 600с+ для извлечения

**Симптомы:**
- Таймауты при извлечении (300с+)
- Блокировка event loop через `asyncio.run_coroutine_threadsafe`
- Избыточное использование диска

## Решение

**Streaming подход с прямым чтением в память:**

```
7z x -so archive.hbk filename → bytes в памяти
```

### Преимущества

1. **Нет temp файлов** - экономия диска, нет I/O накладных расходов
2. **Ленивое чтение** - извлекаем только нужные файлы
3. **Кэширование** - LRU кэш для прочитанных файлов
4. **Контроль таймаутов** - `asyncio.wait_for` напрямую

### Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    HBKParser                            │
├─────────────────────────────────────────────────────────┤
│ - _cache: LRUCache[str, bytes]  # извлеченные файлы    │
│ - _doc_cache: LRUCache[str, Documentation]  # docs     │
│ - _file_index: List[HBKEntry]  # метаданные            │
└─────────────────────────────────────────────────────────┘
         │
         ├── list_archive() → List[HBKEntry]
         │       └── 7z l archive.hbk
         │
         ├── extract_file(filename) → bytes
         │       └── 7z x -so -an archive.hbk filename
         │
         └── parse() → ParsedHBK
                 └── HTMLParser.parse_html_content()
```

## Компоненты

### 1. SevenZipStreamReader

```python
class SevenZipStreamReader:
    """Чтение файлов из 7z архива прямо в память."""
    
    async def extract_file(self, archive_path: Path, filename: str, 
                          timeout: float = 60.0) -> Optional[bytes]:
        """
        Извлекает файл в память через 7z x -so.
        
        Флаги:
        - `-so`: вывод в stdout (extract to stdout)
        - `-an`: не использовать имена файлов из командной строки
        """
        cmd = ['7z', 'x', '-so', '-an', str(archive_path), filename]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout
        )
        
        if proc.returncode != 0:
            raise SevenZipError(stderr.decode())
        
        return stdout
```

### 2. HBKFileCache (LRU)

```python
from functools import lru_cache
# или collections.OrderedDict для ручного управления

class HBKFileCache:
    """LRU кэш для извлеченных файлов."""
    
    def __init__(self, max_size_mb: int = 100):
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._max_bytes = max_size_mb * 1024 * 1024
        self._current_bytes = 0
    
    def get(self, key: str) -> Optional[bytes]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None
    
    def set(self, key: str, value: bytes):
        while self._current_bytes + len(value) > self._max_bytes:
            old_key, old_value = self._cache.popitem(last=False)
            self._current_bytes -= len(old_value)
        
        self._cache[key] = value
        self._current_bytes += len(value)
```

### 3. HBKParser (обновленный)

```python
class HBKParser:
    def __init__(self, cache_size_mb: int = 100):
        self._reader = SevenZipStreamReader()
        self._cache = HBKFileCache(max_size_mb=cache_size_mb)
        self._html_parser = HTMLParser()
    
    async def parse_file(self, file_path: Path) -> Optional[ParsedHBK]:
        # 1. Получить список файлов
        entries = await self._reader.list_archive(file_path)
        
        # 2. Классифицировать файлы
        categories = self._classify_files(entries)
        
        # 3. Параллельно прочитать и распарсить HTML
        tasks = []
        for category, files in categories.items():
            for entry in files:
                if entry.path.endswith('.html'):
                    tasks.append(self._parse_entry(file_path, entry, category))
        
        docs = await asyncio.gather(*tasks, return_exceptions=True)
        
        return ParsedHBK(files=entries, documentation=[d for d in docs if d])
    
    async def _parse_entry(self, archive: Path, entry: HBKEntry, 
                          category: str) -> Optional[Documentation]:
        # Проверка кэша
        cached = self._cache.get(entry.path)
        if cached:
            content = cached
        else:
            # Извлечение в память
            content = await self._reader.extract_file(archive, entry.path)
            self._cache.set(entry.path, content)
        
        # Парсинг HTML
        return self._html_parser.parse_html_content(content, entry.path)
```

## План реализации

### Этап 1: Базовая функциональность
- [ ] `SevenZipStreamReader` с `extract_file()` 
- [ ] `HBKFileCache` (LRU)
- [ ] Интеграция с `HTMLParser`

### Этап 2: Оптимизация
- [ ] Пакетное чтение файлов (`asyncio.gather`)
- [ ] Кэширование результатов парсинга
- [ ] Прогресс парсинга (callback)

### Этап 3: Тестирование
- [ ] Unit тесты для `SevenZipStreamReader`
- [ ] Benchmark скорости vs текущей версией
- [ ] Тесты на память (профилирование)

## Ожидаемые улучшения

| Метрика | Сейчас | Цель |
|---------|--------|------|
| Время парсинга | 10-15 мин | 3-5 мин |
| Память | 256MB | 100MB |
| Диск (temp) | 75MB | 0MB |
| Таймауты | Частые | Нет |

## Риски

1. **7zip не найден** - fallback на py7zr (опционально)
2. **Большие файлы** - лимит размера файла в кэше (max 5MB)
3. **Поврежденный архив** - обработка ошибок 7zip

## Миграция

Сохранить обратную совместимость:
- `HBKParser.parse_file()` возвращает тот же `ParsedHBK`
- Те же исключения (`HBKParserError`)
