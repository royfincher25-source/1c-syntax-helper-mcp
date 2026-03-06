# MCP Server Full Refactoring Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Полный рефакторинг MCP сервера с улучшением архитектуры, устранением дублирования кода и оптимизацией производительности.

**Architecture:** Модульная архитектура с четким разделением ответственности: Core (инфраструктура), Parsers (парсинг данных), Search (поиск), Handlers (обработка запросов), Models (данные).

**Tech Stack:** Python 3.11, FastAPI, Elasticsearch 9.1, asyncio, 7zip, pytest.

---

## Анализ текущего состояния

### ✅ Уже отрефакторено (v1.2.0)
- `src/parsers/hbk_parser.py` - полный рефакторинг HBK парсера
- `src/parsers/sevenzip_manager.py` - новый асинхронный менеджер 7zip сессий
- `src/core/elasticsearch.py` - удален параметр max_size, улучшена структура

### ⚠️ Требует рефакторинга

#### 1. **src/main.py** (1161 строка) - КРИТИЧЕСКИЙ
**Проблемы:**
- Огромный файл с множеством ответственностей
- Смешаны: lifespan, middleware, exception handlers, route handlers
- Дублирование логики health checks
- Сложная навигация и тестирование

**Решение:**
- Выделить lifespan management в отдельный модуль
- Выделить middleware в отдельные классы
- Выделить exception handlers в отдельный модуль
- Выделить routes в отдельные файлы (health_routes, mcp_routes, admin_routes)

#### 2. **src/search/search_service.py** (468 строк) - ВЫСОКИЙ ПРИОРИТЕТ
**Проблемы:**
- Большие методы с множественной ответственностью
- Смешана бизнес-логика и кэширование
- Сложная обработка circuit breaker внутри методов

**Решение:**
- Выделить кэширование в декоратор/отдельный сервис
- Выделить обработку circuit breaker в middleware
- Разбить методы на меньшие приватные методы

#### 3. **src/core/metrics.py** (392 строки) - СРЕДНИЙ ПРИОРИТЕТ
**Проблемы:**
- Дублирование кода в методах сбора метрик
- Сложная логика Prometheus формата
- Смешаны collector и system monitor

**Решение:**
- Разделить MetricsCollector и SystemMonitor на разные файлы
- Вынести Prometheus formatter в отдельный класс
- Упростить API через dataclass

#### 4. **src/core/cache.py** (289 строк) - СРЕДНИЙ ПРИОРИТЕТ
**Проблемы:**
- Хорошая структура, но можно улучшить
- Декоратор `cached` не используется
- Можно добавить больше типов кэша (LRU, LFU)

**Решение:**
- Добавить LFU стратегию eviction
- Улучшить декоратор кэширования
- Добавить типизацию

#### 5. **src/core/graceful_shutdown.py** (215 строк) - НИЗКИЙ ПРИОРИТЕТ
**Проблемы:**
- В целом хорошая структура
- Можно улучшить обработку background tasks

**Решение:**
- Добавить graceful timeout для разных типов задач
- Улучшить логирование

#### 6. **src/handlers/mcp_formatter.py** (252 строки) - СРЕДНИЙ ПРИОРИТЕТ
**Проблемы:**
- Дублирование метода `format_quick_reference` (определен дважды!)
- Большие строковые литералы в методах
- Смешана логика форматирования разных типов

**Решение:**
- Удалить дублирование
- Вынести шаблоны в константы
- Разделить на подклассы для разных типов форматирования

#### 7. **src/search/query_builder.py** (289 строк) - НИЗКИЙ ПРИОРИТЕТ
**Проблемы:**
- Хорошая структура
- Можно улучшить через strategy pattern

**Решение:**
- Выделить стратегии поиска в отдельные классы

#### 8. **src/search/formatter.py** (198 строк) - НИЗКИЙ ПРИОРИТЕТ
**Проблемы:**
- Хорошая структура
- Можно добавить типизацию

**Решение:**
- Добавить TypedDict для результатов

#### 9. **src/parsers/indexer.py** (201 строка) - СРЕДНИЙ ПРИОРИТЕТ
**Проблемы:**
- Bulk индексация может быть улучшена
- Нет обработки partial failures

**Решение:**
- Добавить retry для отдельных документов
- Улучшить обработку ошибок

#### 10. **src/core/circuit_breaker.py** (234 строки) - НИЗКИЙ ПРИОРИТЕТ
**Проблемы:**
- Хорошая структура
- Можно добавить больше состояний

**Решение:**
- Добавить forced open state
- Добавить metrics

---

## План рефакторинга

### Фаза 1: Критический рефакторинг main.py

### Task 1: Выделить lifespan management
**Files:**
- Create: `src/core/lifespan.py`
- Modify: `src/main.py`
- Test: `tests/core/test_lifespan.py`

**Steps:**
1. Создать класс `LifespanManager` с методами startup/shutdown
2. Вынести логику подключения к ES
3. Вынести логику автоиндексации
4. Вынести логику кэша и мониторинга
5. Обновить main.py для использования менеджера

### Task 2: Выделить exception handlers
**Files:**
- Create: `src/core/exception_handlers.py`
- Modify: `src/main.py`
- Test: `tests/core/test_exception_handlers.py`

**Steps:**
1. Создать регистр обработчиков исключений
2. Вынести все exception handler функции
3. Добавить типизацию
4. Обновить main.py

### Task 3: Выделить middleware классы
**Files:**
- Create: `src/core/middleware/rate_limiter_middleware.py`
- Create: `src/core/middleware/__init__.py`
- Modify: `src/main.py`

**Steps:**
1. Вынести rate limiting middleware в отдельный класс
2. Создать базовый класс middleware
3. Обновить main.py

### Task 4: Разделить routes на модули
**Files:**
- Create: `src/routes/health_routes.py`
- Create: `src/routes/mcp_routes.py`
- Create: `src/routes/admin_routes.py`
- Create: `src/routes/__init__.py`
- Modify: `src/main.py`

**Steps:**
1. Вынести health check routes
2. Вынести MCP routes
3. Вынести admin routes (cache, shutdown, index)
4. Создать роутер для каждого модуля
5. Обновить main.py

### Task 5: Создать dependency injection для routes
**Files:**
- Modify: `src/core/dependency_injection.py`
- Create: `src/core/container.py`

**Steps:**
1. Создать контейнер зависимостей
2. Зарегистрировать сервисы
3. Обновить routes для использования DI

---

### Фаза 2: Рефакторинг Search Service

### Task 6: Выделить кэширование в отдельный сервис
**Files:**
- Create: `src/search/cache_service.py`
- Modify: `src/search/search_service.py`
- Test: `tests/search/test_cache_service.py`

**Steps:**
1. Создать `SearchCacheService` класс
2. Вынести логику кэширования из методов
3. Использовать декоратор для кэширования
4. Обновить search_service.py

### Task 7: Выделить circuit breaker middleware
**Files:**
- Create: `src/search/circuit_breaker_middleware.py`
- Modify: `src/search/search_service.py`

**Steps:**
1. Создать middleware для обработки circuit breaker
2. Вынести fallback логику
3. Обновить search_service.py

### Task 8: Разбить search_service на меньшие классы
**Files:**
- Modify: `src/search/search_service.py`
- Create: `src/search/syntax_info_service.py`
- Create: `src/search/context_search_service.py`
- Create: `src/search/object_members_service.py`

**Steps:**
1. Выделить `get_detailed_syntax_info` в отдельный сервис
2. Выделить `search_with_context_filter` в отдельный сервис
3. Выделить `get_object_members_list` в отдельный сервис
4. Создать фасад `SearchService`

---

### Фаза 3: Рефакторинг Core модулей

### Task 9: Разделить metrics модуль
**Files:**
- Create: `src/core/metrics/collector.py`
- Create: `src/core/metrics/system_monitor.py`
- Create: `src/core/metrics/prometheus_formatter.py`
- Create: `src/core/metrics/__init__.py`
- Modify: `src/core/metrics.py` (удалить или оставить как facade)

**Steps:**
1. Вынести `MetricsCollector` в отдельный файл
2. Вынести `SystemMonitor` в отдельный файл
3. Вынести Prometheus formatter
4. Создать facade в metrics.py

### Task 10: Улучшить cache модуль
**Files:**
- Modify: `src/core/cache.py`
- Create: `src/core/cache/strategies.py`
- Test: `tests/core/test_cache_strategies.py`

**Steps:**
1. Создать абстрактный класс `EvictionStrategy`
2. Реализовать `LRUStrategy`
3. Реализовать `LFUStrategy`
4. Обновить `InMemoryCache` для использования стратегий

### Task 11: Улучшить декоратор кэширования
**Files:**
- Modify: `src/core/cache.py`

**Steps:**
1. Добавить поддержку key generator функций
2. Добавить поддержку condition кэширования
3. Добавить метрики для декоратора

---

### Фаза 4: Рефакторинг Handlers и Formatter

### Task 12: Удалить дублирование в mcp_formatter
**Files:**
- Modify: `src/handlers/mcp_formatter.py`
- Test: `tests/handlers/test_mcp_formatter.py`

**Steps:**
1. Удалить дублирование `format_quick_reference`
2. Вынести шаблоны в константы
3. Покрыть тестами

### Task 13: Разделить formatter на подклассы
**Files:**
- Create: `src/handlers/formatters/search_formatter.py`
- Create: `src/handlers/formatters/syntax_formatter.py`
- Create: `src/handlers/formatters/object_formatter.py`
- Create: `src/handlers/formatters/__init__.py`
- Modify: `src/handlers/mcp_formatter.py`

**Steps:**
1. Вынести форматирование поиска
2. Вынести форматирование синтаксиса
3. Вынести форматирование объектов
4. Обновить главный formatter

---

### Фаза 5: Улучшение Indexer и Parser

### Task 14: Улучшить обработку ошибок в indexer
**Files:**
- Modify: `src/parsers/indexer.py`
- Test: `tests/parsers/test_indexer.py`

**Steps:**
1. Добавить retry для отдельных документов
2. Улучшить логирование partial failures
3. Добавить метрики индексации

### Task 15: Добавить прогресс индексации
**Files:**
- Modify: `src/parsers/indexer.py`
- Modify: `src/parsers/hbk_parser.py`

**Steps:**
1. Создать `IndexProgress` dataclass
2. Добавить callback для обновления прогресса
3. Интегрировать с existing `ParserProgress`

---

### Фаза 6: Тесты и документация

### Task 16: Написать integration тесты
**Files:**
- Create: `tests/integration/test_search_integration.py`
- Create: `tests/integration/test_mcp_integration.py`

**Steps:**
1. Создать тесты для search service
2. Создать тесты для MCP handlers
3. Создать тесты для lifecycle

### Task 17: Написать benchmarks
**Files:**
- Create: `tests/benchmarks/test_search_benchmark.py`
- Create: `tests/benchmarks/test_cache_benchmark.py`

**Steps:**
1. Benchmark поиска
2. Benchmark кэша
3. Benchmark индексации

### Task 18: Обновить документацию
**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/architecture.md`

**Steps:**
1. Описать новую архитектуру
2. Обновить changelog
3. Добавить диаграммы

---

## Критерии завершения

### Code Quality:
- [ ] Все файлы < 300 строк (кроме main.py фасада)
- [ ] Все публичные функции < 50 строк
- [ ] 100% type hints
- [ ] No code duplication (DRY)

### Testing:
- [ ] 90%+ code coverage
- [ ] Все integration тесты проходят
- [ ] Benchmarks задокументированы

### Documentation:
- [ ] Architecture документ создан
- [ ] Все публичные API задокументированы
- [ ] Changelog обновлен

### Performance:
- [ ] Поиск < 100ms (p95)
- [ ] Кэш hit rate > 80%
- [ ] Индексация > 100 docs/sec

---

## Приоритизация

**Phase 1 (Критическая):** Tasks 1-5
- main.py рефакторинг - highest priority
- Время: 2-3 часа

**Phase 2 (Высокий приоритет):** Tasks 6-8
- Search service рефакторинг
- Время: 2 часа

**Phase 3 (Средний приоритет):** Tasks 9-13
- Core модули и formatter
- Время: 2-3 часа

**Phase 4 (Низкий приоритет):** Tasks 14-18
- Улучшения и тесты
- Время: 2-3 часа

**Общее время:** 8-11 часов
