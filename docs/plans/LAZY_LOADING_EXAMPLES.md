# 📦 Lazy Loading Примеров

**Дата:** 5 марта 2026  
**Задача:** 2.4 из плана оптимизации  
**Статус:** ✅ Выполнено

---

## 📋 Резюме

Оптимизация размера ответов через lazy loading примеров кода. Примеры не возвращаются по умолчанию, а загружаются отдельным запросом только когда нужны.

---

## ✅ Выполненные оптимизации

### 1. Параметр include_examples

**Проблема:** Примеры кода возвращались всегда, увеличивая размер ответа на 30-50%.

**Решение:**
```python
async def find_help_by_query(
    self,
    query: str,
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    include_examples: bool = False  # По умолчанию False
) -> Dict[str, Any]:
```

**Использование:**
```python
# Без примеров (быстро, мало трафика)
result = await search_service.find_help_by_query("СтрДлина")

# С примерами (по запросу)
result = await search_service.find_help_by_query(
    "СтрДлина",
    include_examples=True
)
```

---

### 2. Отдельный Endpoint для Примеров

**Новый метод:**
```python
async def get_examples_for_element(
    self,
    element_name: str,
    object_name: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """Получить примеры кода для элемента (lazy loading)."""
```

**Использование:**
```python
# Сначала получаем базовую информацию
info = await search_service.find_help_by_query("СтрДлина")

# Затем, если нужны, получаем примеры
examples = await search_service.get_examples_for_element("СтрДлина")
```

---

### 3. Кэширование Примеров

**Оптимизация:**
- Примеры кэшируются отдельно (TTL: 1 час)
- Ключ кэша: `examples:{object}:{element}`
- При повторном запросе возвращаются из кэша

---

## 📁 Измененные файлы

### 1. `src/search/search_service.py`

**Изменения:**
- Добавлен параметр `include_examples: bool = False` в `find_help_by_query()`
- Создан новый метод `get_examples_for_element()`
- Улучшенный cache key с учетом `include_examples`

**Код:**
```python
# Поиск без примеров по умолчанию
async def find_help_by_query(
    self,
    query: str,
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    include_examples: bool = False
) -> Dict[str, Any]:
    # ...
    cache_key = f"search:{query}:{limit}:{hash(str(filters))}:{include_examples}"
    
    # Форматирование с учетом include_examples
    formatted_results = self.formatter.format_search_results(
        ranked_results,
        include_examples=include_examples
    )
    
    result = {
        # ...
        "examples_included": include_examples
    }
```

**Новый метод:**
```python
async def get_examples_for_element(
    self,
    element_name: str,
    object_name: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """Получить примеры кода для элемента."""
    # Кэширование
    cache_key = f"examples:{object_name or 'global'}:{element_name}"
    
    # Поиск с фильтрацией полей
    elasticsearch_query = {
        # ...
        "_source": ["name", "object", "full_path", "examples", "syntax_ru"]
    }
```

---

### 2. `src/search/formatter.py`

**Изменения:**
- Обновлен `_format_document()` с параметром `include_examples`
- Обновлен `format_search_results()` с параметром `include_examples`

**Код:**
```python
def format_search_results(
    self,
    ranked_results: List[Dict[str, Any]],
    include_examples: bool = False
) -> List[Dict[str, Any]]:
    # ...
    formatted_doc = self._format_document(doc, include_examples=include_examples)
```

```python
def _format_document(
    self,
    doc: Dict[str, Any],
    include_examples: bool = False
) -> Dict[str, Any]:
    formatted = {
        "type": doc.get("type", ""),
        "name": doc.get("name", ""),
        # ... другие поля
        # Примеры добавляются только если запрошены
    }
    
    if include_examples:
        formatted["examples"] = doc.get("examples", [])
    
    return formatted
```

---

## 📊 Ожидаемые улучшения

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| **Размер ответа (без примеров)** | 100% | 60-70% | **↓30-40%** 📉 |
| **Размер ответа (с примерами)** | 100% | 100% | - |
| **Трафик (typical use)** | 100% | 60% | **↓40%** 📉 |
| **Время ответа (без примеров)** | 100ms | 70ms | **↓30%** ⚡ |
| **Кэширование примеров** | 0% | 90% hit rate | **90%** 📈 |

---

## 🧪 Тестирование

### Тест 1: Поиск без примеров

```python
from src.search.search_service import search_service

# Поиск без примеров (по умолчанию)
result = await search_service.find_help_by_query("СтрДлина")

print(f"Примеры включены: {result['examples_included']}")
print(f"Размер результата: {len(str(result))} байт")

# Проверяем что примеры не включены
assert result['examples_included'] is False
for r in result['results']:
    assert 'examples' not in r or len(r.get('examples', [])) == 0
```

---

### Тест 2: Поиск с примерами

```python
# Поиск с примерами
result = await search_service.find_help_by_query(
    "СтрДлина",
    include_examples=True
)

print(f"Примеры включены: {result['examples_included']}")

# Проверяем что примеры включены
assert result['examples_included'] is True
for r in result['results']:
    assert 'examples' in r
    assert len(r.get('examples', [])) > 0
```

---

### Тест 3: Отдельное получение примеров

```python
# Сначала базовая информация
info = await search_service.find_help_by_query("СтрДлина")
print(f"Базовый размер: {len(str(info))} байт")

# Затем примеры (lazy loading)
examples = await search_service.get_examples_for_element("СтрДлина")
print(f"Примеры: {examples['total']} найдено")
print(f"Размер примеров: {len(str(examples))} байт")
```

---

### Тест 4: Кэширование примеров

```python
import time

# Первый запрос (из ES)
start = time.time()
examples1 = await search_service.get_examples_for_element("СтрДлина")
time1 = time.time() - start
print(f"Первый запрос: {time1*1000:.2f}ms")

# Второй запрос (из кэша)
start = time.time()
examples2 = await search_service.get_examples_for_element("СтрДлина")
time2 = time.time() - start
print(f"Второй запрос: {time2*1000:.2f}ms")

# Проверяем что кэш работает
assert time2 < time1  # Из кэша быстрее
assert examples1 == examples2  # Результаты одинаковые
```

---

## 🔍 Как это работает

### Lazy Loading Процесс

```
┌─────────────────────────────────────────────────────────┐
│                  Поиск "СтрДлина"                       │
├─────────────────────────────────────────────────────────┤
│  1. find_help_by_query("СтрДлина")                     │
│     ├─ include_examples: False (по умолчанию)          │
│     ├─ Возвращает: name, syntax, description           │
│     └─ Размер: ~500 байт                               │
│                                                         │
│  2. get_examples_for_element("СтрДлина") [если нужно] │
│     ├─ Отдельный запрос к ES                           │
│     ├─ Кэширование (TTL: 1 час)                        │
│     └─ Размер: ~200 байт                               │
└─────────────────────────────────────────────────────────┘

Итого: 500 + 200 = 700 байт (только если примеры запрошены)
vs
Обычный поиск: 700 байт (всегда)
```

---

### Кэширование Примеров

```
┌─────────────────────────────────────────────────────────┐
│              Cache: examples:global:СтрДлина           │
├─────────────────────────────────────────────────────────┤
│  Запрос 1:                                              │
│  ├─ Cache miss                                          │
│  ├─ Запрос к Elasticsearch                              │
│  ├─ Сохранение в кэш (TTL: 3600s)                      │
│  └─ Время: 50ms                                         │
│                                                         │
│  Запрос 2 (через 5 мин):                               │
│  ├─ Cache hit                                           │
│  ├─ Возврат из кэша                                     │
│  └─ Время: 1ms                                          │
│                                                         │
│  Запрос 3 (через 2 часа):                              │
│  ├─ Cache expired (TTL истёк)                          │
│  ├─ Cache miss → запрос к ES                            │
│  └─ Время: 50ms                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 Сценарии Использования

### Сценарий 1: Быстрый поиск (80% случаев)

```python
# Пользователь хочет быстро найти функцию
result = await search_service.find_help_by_query("СтрДлина")

# Возвращает:
# - name: "СтрДлина"
# - syntax_ru: "СтрДлина(Строка)"
# - description: "Возвращает количество символов..."
# - parameters: [...]
# - return_type: "Число"
# ❌ Без examples (экономия трафика)
```

---

### Сценарий 2: Подробное изучение (20% случаев)

```python
# Пользователь хочет изучить примеры использования
result = await search_service.find_help_by_query("СтрДлина")

# Если нужны примеры:
examples = await search_service.get_examples_for_element("СтрДлина")

# Возвращает:
# - element: "СтрДлина"
# - examples: [
#     "Длина = СтрДлина(\"Пример\"); // Результат: 6",
#     "Если СтрДлина(Текст) > 10 Тогда ..."
#   ]
```

---

### Сценарий 3: MCP Protocol Integration

```json
// MCP запрос 1: Поиск
{
  "tool": "search_1c_syntax",
  "arguments": {
    "query": "СтрДлина",
    "include_examples": false
  }
}

// MCP ответ 1: ~500 байт
{
  "results": [
    {
      "name": "СтрДлина",
      "syntax": {"russian": "СтрДлина(Строка)"},
      "description": "Возвращает количество символов..."
    }
  ],
  "examples_included": false
}

// MCP запрос 2: Примеры (если нужны)
{
  "tool": "get_1c_examples",
  "arguments": {
    "element_name": "СтрДлина"
  }
}

// MCP ответ 2: ~200 байт
{
  "element": "СтрДлина",
  "examples": [
    "Длина = СтрДлина(\"Пример\"); // Результат: 6"
  ],
  "total": 1
}
```

---

## 🎯 Критерии готовности

- [x] Параметр `include_examples` добавлен в `find_help_by_query()`
- [x] Примеры не возвращаются по умолчанию (`include_examples=False`)
- [x] Создан отдельный метод `get_examples_for_element()`
- [x] Примеры кэшируются (TTL: 1 час)
- [x] Formatter поддерживает `include_examples`
- [x] Тесты проходят

---

## 📝 Следующие шаги

**Фаза 2 завершена!** (4/4 задач выполнено)

**Следующая фаза:** Фаза 3: Надёжность (2-3 дня)

**Задачи Фазы 3:**
- 3.1 Circuit Breaker для Elasticsearch
- 3.2 Retry с экспоненциальной задержкой (✅ уже выполнено в 2.3)
- 3.3 Health Checks зависимостей
- 3.4 Graceful Shutdown

---

## 🔗 Связанные документы

- [План оптимизации](./2026-03-05-optimization-roadmap.md)
- [Connection Pooling](./CONNECTION_POOLING.md)
- [Elasticsearch Optimization](./ELASTICSEARCH_OPTIMIZATION.md)
- [In-memory Кэширование](./IN_MEMORY_CACHE.md)

---

**Статус:** ✅ **Задача 2.4 завершена!**  
**Прогресс Фазы 2:** 100% (4/4 задач выполнено)  
**Следующая фаза:** Фаза 3: Надёжность
