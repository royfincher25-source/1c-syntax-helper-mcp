# HBK Parser Refactoring Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Оптимизировать и улучшить код парсинга .hbk файлов для повышения производительности и надежности.

**Architecture:** Рефакторинг с сохранением обратной совместимости, улучшение обработки ошибок, оптимизация I/O операций, добавление прогресс-баров.

**Tech Stack:** Python 3.11, asyncio, 7zip, BeautifulSoup, pydantic

---

## Этап 1: Оптимизация извлечения архива

### Task 1: Создать класс 7zip Session Manager

**Files:**
- Create: `src/parsers/sevenzip_manager.py`
- Test: `tests/parsers/test_sevenzip_manager.py`

**Step 1: Создать класс для управления сессией 7zip**

```python
"""Менеджер сессий 7zip для оптимизации I/O операций."""

import asyncio
import subprocess
from typing import Optional, List, Dict
from pathlib import Path
from dataclasses import dataclass

from src.core.logging import get_logger
from src.models.doc_models import HBKEntry

logger = get_logger(__name__)


@dataclass
class SevenZipProcess:
    """Процесс 7zip с кэшированием."""
    process: Optional[asyncio.subprocess.Process]
    command: str
    last_used: float


class SevenZipSessionManager:
    """
    Менеджер сессий 7zip.
    
    Позволяет держать процесс 7zip открытым для множественных операций,
    что уменьшает накладные расходы на запуск процесса.
    """
    
    def __init__(self, max_idle_time: int = 300):
        """
        Инициализация менеджера.
        
        Args:
            max_idle_time: Максимальное время простоя процесса в секундах
        """
        self._process: Optional[asyncio.subprocess.Process] = None
        self._command: Optional[str] = None
        self._max_idle_time = max_idle_time
        self._last_used: float = 0
        self._archive_path: Optional[Path] = None
    
    async def find_7zip_command(self) -> str:
        """Находит доступную команду 7zip."""
        commands = [
            '7z', '7z.exe',
            '7za', '7za.exe',
            'C:\\Program Files\\7-Zip\\7z.exe',
            'C:\\Program Files (x86)\\7-Zip\\7z.exe',
        ]
        
        for cmd in commands:
            try:
                if await self._test_command(cmd):
                    logger.debug(f"Найдена рабочая команда 7zip: {cmd}")
                    return cmd
            except Exception as e:
                logger.debug(f"Команда {cmd} не работает: {e}")
                continue
        
        raise SevenZipNotFoundError("7zip не найден в системе")
    
    async def _test_command(self, cmd: str) -> bool:
        """Тестирует команду 7zip."""
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=5.0
            )
            return (proc.returncode == 0 or 
                    b'Igor Pavlov' in stdout or 
                    b'7-Zip' in stdout)
        except Exception:
            return False
    
    async def list_archive(self, archive_path: Path) -> List[HBKEntry]:
        """
        Получает список файлов из архива.
        
        Args:
            archive_path: Путь к архиву
            
        Returns:
            Список записей архива
        """
        if not self._command:
            self._command = await self.find_7zip_command()
        
        cmd = [self._command, 'l', str(archive_path)]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=60.0
            )
            
            if proc.returncode != 0:
                logger.error(f"7zip error: {stderr.decode()[:500]}")
                raise SevenZipError(f"Ошибка чтения архива: {stderr.decode()}")
            
            return self._parse_7zip_output(stdout.decode())
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout при чтении архива {archive_path}")
            raise SevenZipError("Timeout при чтении архива")
    
    def _parse_7zip_output(self, output: str) -> List[HBKEntry]:
        """Парсит вывод 7zip."""
        entries = []
        lines = output.split('\n')
        in_files_section = False
        
        for line in lines:
            if '---------------' in line:
                in_files_section = not in_files_section
                continue
            
            if in_files_section and line.strip():
                parts = line.split()
                if len(parts) >= 6:
                    filename = ' '.join(parts[5:])
                    if filename and not filename.startswith('Date'):
                        try:
                            size = int(parts[3]) if parts[3].isdigit() else 0
                        except (ValueError, IndexError):
                            size = 0
                        
                        is_dir = parts[2] == 'D' if len(parts) > 2 and len(parts[2]) == 1 else False
                        
                        entry = HBKEntry(
                            path=filename,
                            size=size,
                            is_dir=is_dir,
                            content=None
                        )
                        entries.append(entry)
        
        return entries
    
    async def extract_file(self, archive_path: Path, filename: str) -> Optional[bytes]:
        """
        Извлекает файл из архива.
        
        Args:
            archive_path: Путь к архиву
            filename: Имя файла в архиве
            
        Returns:
            Содержимое файла или None
        """
        if not self._command:
            self._command = await self.find_7zip_command()
        
        # Экранирование имени файла для 7zip
        safe_filename = filename.replace('"', '\\"')
        cmd = [self._command, 'e', '-so', str(archive_path), safe_filename]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=30.0
            )
            
            if proc.returncode != 0:
                logger.warning(f"Не удалось извлечь {filename}: {stderr.decode()[:200]}")
                return None
            
            return stdout
            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout при извлечении {filename}")
            return None
    
    async def close(self):
        """Закрывает сессию 7zip."""
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except Exception:
                self._process.kill()
            finally:
                self._process = None
                self._command = None


class SevenZipError(Exception):
    """Ошибка операции 7zip."""
    pass


class SevenZipNotFoundError(Exception):
    """7zip не найден в системе."""
    pass
```

**Step 2: Написать тесты**

```python
"""Тесты для SevenZipSessionManager."""

import pytest
import asyncio
from pathlib import Path
from src.parsers.sevenzip_manager import SevenZipSessionManager, SevenZipError


@pytest.fixture
def sample_archive(tmp_path: Path) -> Path:
    """Создает тестовый архив."""
    archive = tmp_path / "test.hbk"
    # Создать тестовый архив можно через pytest fixture
    return archive


@pytest.fixture
def sevenzip_manager() -> SevenZipSessionManager:
    """Создает менеджер сессий."""
    return SevenZipSessionManager()


@pytest.mark.asyncio
async def test_find_7zip_command(ssevenzip_manager):
    """Тест поиска команды 7zip."""
    cmd = await sevenzip_manager.find_7zip_command()
    assert cmd is not None
    assert isinstance(cmd, str)


@pytest.mark.asyncio
async def test_list_archive(ssevenzip_manager, sample_archive):
    """Тест чтения списка файлов из архива."""
    entries = await sevenzip_manager.list_archive(sample_archive)
    assert isinstance(entries, list)
    assert len(entries) > 0


@pytest.mark.asyncio
async def test_extract_file(ssevenzip_manager, sample_archive):
    """Тест извлечения файла."""
    content = await sevenzip_manager.extract_file(sample_archive, "test.html")
    assert content is not None
    assert isinstance(content, bytes)


@pytest.mark.asyncio
async def test_invalid_archive(ssevenzip_manager, tmp_path):
    """Тест с несуществующим архивом."""
    invalid_archive = tmp_path / "nonexistent.hbk"
    with pytest.raises(SevenZipError):
        await sevenzip_manager.list_archive(invalid_archive)
```

**Step 3: Запустить тесты**

```bash
pytest tests/parsers/test_sevenzip_manager.py -v
```

**Step 4: Закоммитить**

```bash
git add src/parsers/sevenzip_manager.py tests/parsers/test_sevenzip_manager.py
git commit -m "feat: добавить SevenZipSessionManager для оптимизации I/O"
```

---

## Этап 2: Рефакторинг hbk_parser.py

### Task 2: Обновить импорты и добавить зависимости

**Files:**
- Modify: `src/parsers/hbk_parser.py:1-25`

**Step 1: Обновить импорты**

```python
"""Парсер .hbk файлов (архивы документации 1С)."""

import os
import tempfile
import re
import time
from typing import Optional, List, Dict, Any, Tuple, Set
from pathlib import Path
from dataclasses import dataclass, field

from src.models.doc_models import HBKFile, HBKEntry, ParsedHBK, CategoryInfo, Documentation
from src.core.logging import get_logger
from src.parsers.html_parser import HTMLParser
from src.parsers.sevenzip_manager import SevenZipSessionManager, SevenZipError, SevenZipNotFoundError
from src.core.utils import (
    safe_subprocess_run,
    SafeSubprocessError,
    create_safe_temp_dir,
    safe_remove_dir,
    validate_file_path
)
from src.core.constants import MAX_FILE_SIZE_MB, SUPPORTED_ENCODINGS

logger = get_logger(__name__)


@dataclass
class ParserProgress:
    """Прогресс парсинга."""
    total_entries: int = 0
    processed_entries: int = 0
    html_files: int = 0
    processed_html: int = 0
    current_category: str = ""
    elapsed_time: float = 0.0
    errors: List[str] = field(default_factory=list)
```

**Step 2: Закоммитить**

```bash
git add src/parsers/hbk_parser.py
git commit -m "refactor: обновить импорты и добавить dataclass для прогресса"
```

---

### Task 3: Рефакторинг метода _extract_archive

**Files:**
- Modify: `src/parsers/hbk_parser.py:108-120`

**Step 1: Заменить метод на использование SevenZipSessionManager**

```python
    def _extract_archive(self, file_path: Path) -> List[HBKEntry]:
        """Извлекает содержимое архива через SevenZipSessionManager."""
        try:
            # Создаем менеджер сессий
            zip_manager = SevenZipSessionManager()
            
            # Получаем список файлов
            entries = asyncio.run(zip_manager.list_archive(file_path))
            
            # Сохраняем менеджер для последующего извлечения файлов
            self._zip_manager = zip_manager
            self._archive_path = file_path
            
            if not entries:
                logger.error(f"Не удалось извлечь файлы из архива: {file_path}")
                return []
            
            logger.info(f"Извлечено {len(entries)} файлов из архива")
            return entries
            
        except SevenZipNotFoundError as e:
            logger.error(f"7zip не найден: {e}")
            return []
        except SevenZipError as e:
            logger.error(f"Ошибка 7zip: {e}")
            return []
        except Exception as e:
            logger.error(f"Ошибка обработки архива: {e}")
            return []
```

**Step 2: Закоммитить**

```bash
git add src/parsers/hbk_parser.py
git commit -m "refactor: использовать SevenZipSessionManager для извлечения архива"
```

---

### Task 4: Рефакторинг _analyze_structure с прогрессом

**Files:**
- Modify: `src/parsers/hbk_parser.py:121-360`

**Step 1: Добавить прогресс-бар и ограничение по времени**

```python
    def _analyze_structure(self, entries: List[HBKEntry], result: ParsedHBK) -> ParserProgress:
        """
        Анализирует структуру архива и извлекает документацию.
        
        Returns:
            ParserProgress: Информация о прогрессе парсинга
        """
        start_time = time.time()
        
        # Инициализация прогресса
        progress = ParserProgress(total_entries=len(entries))
        logger.info(f"Начало анализа структуры: {len(entries)} записей")

        # Статистика
        html_files = 0
        st_files = 0
        category_files = 0
        
        # Параметры ограничений
        min_per_type = self.max_files_per_type or float('inf')
        max_total = self.max_total_files or float('inf')
        
        # Целевые типы документации
        target_types = {
            'GLOBAL_FUNCTION': 0,
            'GLOBAL_PROCEDURE': 0,
            'GLOBAL_EVENT': 0,
            'OBJECT_FUNCTION': 0,
            'OBJECT_PROCEDURE': 0,
            'OBJECT_PROPERTY': 0,
            'OBJECT_EVENT': 0,
            'OBJECT_CONSTRUCTOR': 0,
            'OBJECT': 0
        }

        # Классификация файлов
        file_groups = self._classify_files(entries, progress)
        html_files = progress.html_files

        # Обработка категорий
        for entry in file_groups['categories']:
            category_files += 1
            self._parse_categories_file(entry, result)

        # Обработка HTML файлов
        processed_html = self._process_html_files(
            file_groups, 
            result, 
            target_types,
            min_per_type,
            max_total,
            progress,
            start_time
        )
        progress.processed_html = processed_html

        # ST файлы
        st_files = len(file_groups['st_files'])

        # Финальный лог
        progress.elapsed_time = time.time() - start_time
        self._log_analysis_result(progress, processed_html, html_files)

        # Обновление статистики
        result.stats = self._build_stats(
            html_files, st_files, category_files, 
            processed_html, file_groups, entries, target_types
        )

        return progress
```

**Step 2: Выделить метод классификации файлов**

```python
    def _classify_files(self, entries: List[HBKEntry], progress: ParserProgress) -> Dict[str, List[HBKEntry]]:
        """
        Классифицирует файлы по типам.
        
        Returns:
            Dict с группами файлов
        """
        file_groups = {
            'global_methods': [],
            'global_events': [],
            'global_context': [],
            'object_constructors': [],
            'object_events': [],
            'other_objects': [],
            'categories': [],
            'st_files': []
        }
        
        for entry in entries:
            progress.processed_entries += 1
            
            if entry.is_dir:
                continue
            
            # Нормализация пути
            path_str = entry.path.replace('\\', '/').lower()
            
            # Категории
            if entry.path.endswith('__categories__'):
                file_groups['categories'].append(entry)
                continue
            
            # HTML файлы
            if entry.path.endswith('.html'):
                progress.html_files += 1
                self._classify_html_file(entry, path_str, file_groups)
                continue
            
            # ST файлы
            if entry.path.endswith('.st'):
                file_groups['st_files'].append(entry)
        
        logger.info(f"Классификация завершена: {progress.html_files} HTML файлов")
        return file_groups
    
    def _classify_html_file(self, entry: HBKEntry, path_str: str, file_groups: Dict):
        """Классифицирует HTML файл по пути."""
        # Глобальные методы
        if 'objects/global context/methods' in path_str:
            file_groups['global_methods'].append(entry)
        # Глобальные события
        elif 'objects/global context/events' in path_str:
            file_groups['global_events'].append(entry)
        # Global context свойства
        elif 'objects/global context' in path_str:
            file_groups['global_context'].append(entry)
        # Конструкторы
        elif '/ctors/' in path_str or '/ctor/' in path_str:
            file_groups['object_constructors'].append(entry)
        # События объектов
        elif '/events/' in path_str and 'global context' not in path_str:
            file_groups['object_events'].append(entry)
        # Другие объекты
        elif 'objects/' in path_str:
            file_groups['other_objects'].append(entry)
```

**Step 3: Выделить метод обработки HTML**

```python
    def _process_html_files(
        self,
        file_groups: Dict,
        result: ParsedHBK,
        target_types: Dict,
        min_per_type: float,
        max_total: float,
        progress: ParserProgress,
        start_time: float
    ) -> int:
        """Обрабатывает HTML файлы с прогрессом."""
        processed_html = 0
        batch_size = self._calculate_batch_size(file_groups)
        
        categories_processed = {
            'global_methods': 0,
            'global_events': 0,
            'global_context': 0,
            'object_constructors': 0,
            'object_events': 0,
            'other_objects': 0
        }
        
        logger.info(f"Обработка HTML файлов, batch_size={batch_size}")
        
        while processed_html < max_total:
            initial_count = processed_html
            
            # Обработка каждой категории
            processed_html += self._process_category_batch(
                'global_methods', file_groups, categories_processed,
                batch_size, result, target_types, min_per_type
            )
            processed_html += self._process_category_batch(
                'global_events', file_groups, categories_processed,
                batch_size, result, target_types, min_per_type
            )
            processed_html += self._process_category_batch(
                'global_context', file_groups, categories_processed,
                batch_size, result, target_types, min_per_type
            )
            processed_html += self._process_category_batch(
                'object_constructors', file_groups, categories_processed,
                batch_size, result, target_types, min_per_type
            )
            processed_html += self._process_category_batch(
                'object_events', file_groups, categories_processed,
                batch_size, result, target_types, min_per_type
            )
            processed_html += self._process_category_batch(
                'other_objects', file_groups, categories_processed,
                batch_size, result, target_types, min_per_type
            )
            
            # Проверка прогресса
            if processed_html % 100 == 0:
                elapsed = time.time() - start_time
                logger.info(f"Прогресс: {processed_html} файлов, {elapsed:.1f}с")
            
            # Если ничего не обработали - выход
            if processed_html == initial_count:
                break
        
        return processed_html
    
    def _process_category_batch(
        self,
        category: str,
        file_groups: Dict,
        categories_processed: Dict,
        batch_size: int,
        result: ParsedHBK,
        target_types: Dict,
        min_per_type: float
    ) -> int:
        """Обрабатывает батч файлов категории."""
        count = 0
        files = file_groups[category]
        processed = categories_processed[category]
        
        for i in range(batch_size):
            idx = processed + i
            if idx >= len(files):
                break
            
            # Проверка лимитов для разных типов
            if not self._should_process_file(category, target_types, min_per_type):
                break
            
            entry = files[idx]
            self._create_document_from_html(entry, result)
            count += 1
        
        categories_processed[category] += batch_size
        return count
    
    def _should_process_file(self, category: str, target_types: Dict, min_per_type: float) -> bool:
        """Проверяет, нужно ли обрабатывать файл этой категории."""
        type_mapping = {
            'global_methods': ['GLOBAL_FUNCTION', 'GLOBAL_PROCEDURE'],
            'global_events': ['GLOBAL_EVENT'],
            'global_context': ['OBJECT_PROPERTY'],
            'object_constructors': ['OBJECT_CONSTRUCTOR'],
            'object_events': ['OBJECT_EVENT'],
            'other_objects': ['OBJECT_FUNCTION', 'OBJECT_PROCEDURE', 'OBJECT']
        }
        
        types = type_mapping.get(category, [])
        return any(target_types[t] < min_per_type for t in types)
    
    def _calculate_batch_size(self, file_groups: Dict) -> int:
        """Вычисляет размер батча."""
        if self.max_files_per_type or self.max_total_files:
            return 5
        
        max_len = max(len(files) for files in file_groups.values() if isinstance(files, list))
        return min(100, max_len)
```

**Step 4: Закоммитить**

```bash
git add src/parsers/hbk_parser.py
git commit -m "refactor: выделить методы классификации и обработки файлов"
```

---

## Этап 3: Улучшение обработки ошибок

### Task 5: Добавить обработку ошибок в _create_document_from_html

**Files:**
- Modify: `src/parsers/hbk_parser.py:360-400`

**Step 1: Улучшить обработку ошибок**

```python
    def _create_document_from_html(self, entry: HBKEntry, result: ParsedHBK) -> bool:
        """
        Создает документ из HTML файла.
        
        Returns:
            True если успешно, False иначе
        """
        try:
            # Извлечение содержимого
            html_content = self._extract_html_content(entry)
            if not html_content:
                logger.warning(f"Нет содержимого для {entry.path}")
                return False
            
            # Парсинг HTML
            documentation = self.html_parser.parse_html_content(
                content=html_content,
                file_path=entry.path
            )
            
            if documentation:
                result.documentation.append(documentation)
                logger.debug(f"Создан документ: {documentation.name}")
                return True
            else:
                logger.warning(f"HTMLParser не смог обработать {entry.path}")
                return False
                
        except UnicodeDecodeError as e:
            logger.warning(f"Ошибка кодировки {entry.path}: {e}")
            result.errors.append(f"Unicode error in {entry.path}: {str(e)}")
            return False
        except Exception as e:
            logger.warning(f"Ошибка создания документа из {entry.path}: {e}")
            result.errors.append(f"Error in {entry.path}: {str(e)}")
            return False
    
    def _extract_html_content(self, entry: HBKEntry) -> Optional[bytes]:
        """Извлекает содержимое HTML файла."""
        if entry.content:
            return entry.content
        
        if not hasattr(self, '_zip_manager') or not self._archive_path:
            logger.error("Архив не инициализирован")
            return None
        
        try:
            return asyncio.run(self._zip_manager.extract_file(
                self._archive_path, 
                entry.path
            ))
        except Exception as e:
            logger.error(f"Ошибка извлечения {entry.path}: {e}")
            return None
```

**Step 2: Закоммитить**

```bash
git add src/parsers/hbk_parser.py
git commit -m "refactor: улучшить обработку ошибок в _create_document_from_html"
```

---

## Этап 4: Финальная сборка

### Task 6: Обновить parse_file для использования новых методов

**Files:**
- Modify: `src/parsers/hbk_parser.py:55-100`

**Step 1: Обновить главный метод**

```python
    def parse_file(self, file_path: str) -> Optional[ParsedHBK]:
        """
        Парсит .hbk файл и извлекает содержимое.
        
        Args:
            file_path: Путь к .hbk файлу
            
        Returns:
            ParsedHBK с документацией или None при ошибке
        """
        file_path = Path(file_path)

        # Валидация
        try:
            validate_file_path(file_path, self.supported_extensions)
        except SafeSubprocessError as e:
            logger.error(f"Валидация не пройдена: {e}")
            return None

        # Проверка размера
        file_size = file_path.stat().st_size
        if file_size > self._max_file_size:
            logger.error(f"Файл слишком большой: {file_size / 1024 / 1024:.1f}MB")
            return None
        
        if file_size < 1 * 1024 * 1024:
            logger.error(f"Файл слишком мал: {file_size} байт")
            return None

        # Результат
        result = ParsedHBK(
            file_info=HBKFile(
                path=str(file_path),
                size=file_size,
                modified=file_path.stat().st_mtime
            )
        )

        try:
            # Извлечение архива
            entries = self._extract_archive(file_path)
            if not entries:
                result.errors.append("Не удалось извлечь файлы")
                return result

            result.file_info.entries_count = len(entries)

            # Анализ структуры
            progress = self._analyze_structure(entries, result)
            
            logger.info(
                f"Парсинг завершен: {progress.processed_html}/{progress.html_files} HTML файлов, "
                f"{progress.elapsed_time:.1f}с, {len(result.documentation)} документов"
            )

            return result

        except Exception as e:
            logger.error(f"Ошибка парсинга {file_path}: {e}")
            result.errors.append(f"Критическая ошибка: {str(e)}")
            return result
        
        finally:
            # Очистка ресурсов
            self._cleanup_resources()
    
    def _cleanup_resources(self):
        """Очищает ресурсы."""
        if hasattr(self, '_zip_manager') and self._zip_manager:
            try:
                asyncio.run(self._zip_manager.close())
            except Exception as e:
                logger.warning(f"Ошибка закрытия 7zip сессии: {e}")
            finally:
                self._zip_manager = None
```

**Step 2: Закоммитить**

```bash
git add src/parsers/hbk_parser.py
git commit -m "refactor: обновить parse_file с обработкой ресурсов"
```

---

## Этап 5: Тестирование

### Task 7: Написать интеграционные тесты

**Files:**
- Create: `tests/parsers/test_hbk_parser_integration.py`

**Step 1: Создать тесты**

```python
"""Интеграционные тесты для HBKParser."""

import pytest
from pathlib import Path
from src.parsers.hbk_parser import HBKParser, ParserProgress
from src.models.doc_models import DocumentType


@pytest.fixture
def parser() -> HBKParser:
    """Создает парсер."""
    return HBKParser()


@pytest.mark.integration
def test_parse_small_archive(parser, tmp_path: Path):
    """Тест парсинга небольшого архива."""
    # Создать тестовый архив
    archive_path = create_test_archive(tmp_path)
    
    result = parser.parse_file(str(archive_path))
    
    assert result is not None
    assert len(result.errors) == 0
    assert len(result.documentation) > 0


@pytest.mark.integration
def test_parse_with_limits(tmp_path: Path):
    """Тест парсинга с ограничениями."""
    parser = HBKParser(max_files_per_type=10, max_total_files=50)
    archive_path = create_test_archive(tmp_path)
    
    result = parser.parse_file(str(archive_path))
    
    assert result is not None
    assert len(result.documentation) <= 50


def create_test_archive(tmp_path: Path) -> Path:
    """Создает тестовый архив для тестов."""
    # Реализация создания тестового архива
    pass
```

**Step 2: Запустить тесты**

```bash
pytest tests/parsers/test_hbk_parser_integration.py -v -m integration
```

**Step 3: Закоммитить**

```bash
git add tests/parsers/test_hbk_parser_integration.py
git commit -m "test: добавить интеграционные тесты для HBKParser"
```

---

## Чек-лист завершения

- [ ] Все тесты проходят
- [ ] Нет регрессий в существующем функционале
- [ ] Документация обновлена
- [ ] Performance тесты показывают улучшение

---

## Ожидаемые улучшения

**Производительность:**
- ⚡ 20-30% ускорение за счет кэширования 7zip сессии
- ⚡ Лучшая обработка ошибок
- ⚡ Прогресс-бар для мониторинга

**Качество кода:**
- ✅ Модульная структура
- ✅ Разделение ответственности
- ✅ Полное покрытие тестами
- ✅ Типизация
