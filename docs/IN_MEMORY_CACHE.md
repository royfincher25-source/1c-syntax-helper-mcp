# 🚀 In-memory Кэширование

## 📊 Обзор

In-memory кэш с TTL для оптимизации запросов к Elasticsearch и снижения нагрузки на базу данных.

---

## 🎯 Возможности

### 1. TTL (Time To Live)
- Автоматическое истечение срока действия записей
- Настраиваемый TTL для разных типов данных
- Фоновая очистка устаревших записей

### 2. LRU Eviction
- Least Recently Used eviction при переполнении
- Защита от переполнения памяти
- Максимальный размер кэша настраивается

### 3. Статистика
- Подсчёт hits/misses
- Расчёт hit rate %
- Отслеживание evictions и expirations

### 4. Асинхронность
- Полностью асинхронная реализация
- Потокобезопасность через asyncio.Lock
- Не блокирует event loop

---

## 📁 Архитектура

```
src/core/cache.py
├── CacheEntry       # Запись кэша с метаданными
├── CacheStats       # Статистика кэша
├── InMemoryCache    # Основной класс кэша
├── cache            # Глобальный экземпляр
└── @cached          # Декоратор для кэширования
```

---

## 🔧 Использование

### Базовое использование

```python
from src.core.cache import cache

# Установка значения
await cache.set("key", "value", ttl=300)  # TTL: 5 минут

# Получение значения
value = await cache.get("key")

# Удаление значения
deleted = await cache.delete("key")

# Очистка всего кэша
await cache.clear()
```

### Проверка существования

```python
exists = await cache.exists("key")
if exists:
    value = await cache.get("key")
```

### Получение статистики

```python
stats = await cache.get_stats()
print(stats)
# {
#   "hits": 150,
#   "misses": 50,
#   "evictions": 10,
#   "expirations": 5,
#   "hit_rate_percent": 75.0,
#   "total_requests": 200,
#   "size": 45,
#   "max_size": 1000,
#   "utilization_percent": 4.5
# }
```

---

## 📊 Конфигурация

### Глобальный кэш (по умолчанию)

```python
cache = InMemoryCache(
    max_size=1000,           # Максимум 1000 записей
    default_ttl=300,         # TTL по умолчанию: 5 минут
    cleanup_interval=60      # Очистка каждые 60 секунд
)
```

### Создание своего кэша

```python
my_cache = InMemoryCache(
    max_size=500,            # Максимум 500 записей
    default_ttl=600,         # TTL: 10 минут
    cleanup_interval=120     # Очистка каждые 2 минуты
)

await my_cache.start()       # Запуск фоновой очистки
# ... использование ...
await my_cache.stop()        # Остановка
```

---

## 🎯 Сценарии использования

### 1. Кэширование поисковых запросов

```python
# В search_service.py
async def find_help_by_query(self, query: str, limit: int = 5):
    cache_key = f"search:{query}:{limit}"
    
    # Пытаемся получить из кэша
    cached_result = await cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    # Выполняем поиск в ES
    result = await elasticsearch_search(query, limit)
    
    # Кэшируем результат (TTL: 5 минут)
    await cache.set(cache_key, result, ttl=300)
    
    return result
```

**Преимущества:**
- Снижение нагрузки на Elasticsearch
- Ускорение ответов для частых запросов
- Hit rate: ~60-80% для типичных сценариев

### 2. Кэширование детальной информации

```python
# В search_service.py
async def get_detailed_syntax_info(self, element_name: str, ...):
    cache_key = f"syntax:{element_name}"
    
    # Пытаемся получить из кэша
    cached_result = await cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    # Получаем из ES
    result = await elasticsearch_get(element_name)
    
    # Кэшируем результат (TTL: 1 час)
    await cache.set(cache_key, result, ttl=3600)
    
    return result
```

**Преимущества:**
- Детальная информация редко меняется
- Длительный TTL (1 час) уменьшает нагрузку
- Hit rate: ~90% для популярных элементов

### 3. Инвалидация при переиндексации

```python
# В indexer.py
async def reindex_all(self, parsed_hbk: ParsedHBK):
    # ... переиндексация ...
    
    # Инвалидируем кэш
    await cache.clear()
    logger.info("Кэш инвалидирован после переиндексации")
```

---

## 📈 API Endpoints

### GET /cache/stats

Возвращает статистику кэша.

**Ответ:**
```json
{
  "hits": 150,
  "misses": 50,
  "evictions": 10,
  "expirations": 5,
  "hit_rate_percent": 75.0,
  "total_requests": 200,
  "size": 45,
  "max_size": 1000,
  "utilization_percent": 4.5
}
```

### POST /cache/clear

Очищает весь кэш.

**Ответ:**
```json
{
  "status": "success",
  "message": "Кэш очищен"
}
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
python tests/test_cache.py
```

### Тесты включают:

- ✅ Базовая установка и получение
- ✅ TTL expiration
- ✅ LRU eviction
- ✅ Статистика
- ✅ Удаление и очистка
- ✅ Конкурентный доступ
- ✅ Проверка существования

---

## 🎓 Лучшие практики

### ✅ Делайте

- Используйте осмысленные ключи: `search:{query}:{limit}`
- Настраивайте TTL в зависимости от типа данных
- Мониторьте hit rate через /cache/stats
- Инвалидируйте кэш при обновлении данных

### ❌ Не делайте

- Не кэшируйте очень большие объекты (>1MB)
- Не используйте очень короткий TTL (<10 секунд)
- Не полагайтесь на кэш как на основное хранилище
- Не забывайте очищать кэш при переиндексации

---

## 📊 Метрики и мониторинг

### Ключевые метрики

| Метрика | Описание | Target |
|---------|----------|--------|
| **Hit Rate** | % попаданий в кэш | > 60% |
| **Size** | Текущий размер кэша | < 80% от max |
| **Evictions** | Количество вытеснений | Минимум |
| **Expirations** | Количество истечений | Зависит от TTL |

### Команды для мониторинга

```bash
# Проверка статистики
curl http://localhost:8002/cache/stats | jq

# Очистка кэша
curl -X POST http://localhost:8002/cache/clear

# Мониторинг в реальном времени
watch -n 5 'curl -s http://localhost:8002/cache/stats | jq'
```

---

## 🔍 Примеры логов

### Cache Hit

```json
{
  "timestamp": "2026-03-05T14:00:00.000Z",
  "level": "DEBUG",
  "message": "Cache hit: search:СтрДлина:5",
  "request_id": "...",
  "access_count": 5,
  "age_seconds": 120.5
}
```

### Cache Miss

```json
{
  "timestamp": "2026-03-05T14:00:01.000Z",
  "level": "INFO",
  "message": "Поиск 'СтрДлина' завершен за 45ms. Найдено: 1",
  "request_id": "..."
}
```

### Cache Set

```json
{
  "timestamp": "2026-03-05T14:00:01.050Z",
  "level": "DEBUG",
  "message": "Cache set: search:СтрДлина:5 (TTL: 300s)",
  "request_id": "...",
  "ttl": 300
}
```

### Cache Invalidation

```json
{
  "timestamp": "2026-03-05T15:00:00.000Z",
  "level": "INFO",
  "message": "Кэш инвалидирован после переиндексации",
  "request_id": "..."
}
```

---

## 🛠️ Расширенные возможности

### Декоратор @cached

```python
from src.core.cache import cached

@cached(ttl=600, key_prefix="search")
async def search_function(query: str, limit: int = 5):
    # Эта функция будет автоматически кэшироваться
    return await elasticsearch_search(query, limit)

# Ключ кэша: "search:search_function:query:5"
```

### Кастомные ключи кэша

```python
# Для сложных запросов
cache_key = f"complex:{hash(frozenset(params.items()))}"
result = await cache.get(cache_key)
```

---

## 📊 Ожидаемые улучшения

| Метрика | До кэша | После кэша | Улучшение |
|---------|---------|------------|-----------|
| **Среднее время поиска** | 50ms | 5ms | 10x |
| **Нагрузка на ES** | 100% | 30-40% | 60-70% ↓ |
| **Hit Rate** | 0% | 60-80% | - |
| **P95 время ответа** | 200ms | 50ms | 4x |

---

## 🔗 Ссылки

- [cache.py](../src/core/cache.py)
- [search_service.py](../src/search/search_service.py)
- [indexer.py](../src/parsers/indexer.py)
- [test_cache.py](../tests/test_cache.py)

---

**Обновлено:** 5 марта 2026  
**Версия:** 1.0 (In-memory Кэширование)
