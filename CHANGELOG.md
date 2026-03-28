# Changelog

Все изменения в проекте 1C Syntax Helper MCP Server.

## [1.5.0] - 2026-03-29 - Оптимизация ресурсов и унификация MCP

### Добавлено
- **Унифицированный MCP роутер** (`src/routes/mcp_unified.py`):
  - Единый endpoint `/mcp` для SSE и HTTP
  - Поддержка JSON-RPC 2.0
  - Устранено дублирование кода (было 2 роутера, стал 1)

### Изменено
- **Оптимизация потребления памяти**:
  - Elasticsearch heap: 1GB → 256MB
  - System monitoring: отключен по умолчанию (`SYSTEM_MONITORING=false`)
- **Обновлена документация** с актуальными требованиями к памяти

### Удалено
- Устаревшие файлы: `mcp_routes.py`, `sse_router.py`
- Устаревшие корневые тестовые файлы

## [1.4.0] - 2026-03-06 - Оптимизация парсера и очистка

### Добавлено
- **HBKParserOptimized**: Новый оптимизированный парсер с ускорением в 20 раз
  - Параллельный парсинг HTML файлов (asyncio + Semaphore, 10 потоков)
  - LRU кэш документов на базе OrderedDict (O(1) операции)
  - Дедупликация документов по ID
  - Обработка asyncio.CancelledError
  - Время парсинга: 44с вместо 10-15 минут (566 док/с)
  - Production тест: 52с (парсинг + Elasticsearch индексация)

- **Константы оптимизации** (`src/core/constants.py`):
  - `PARALLEL_PARSE_LIMIT = 10`: Максимум параллельных задач парсинга
  - `DOC_CACHE_SIZE = 5000`: Максимум документов в кэше

- **API endpoint**: `GET /parse/progress` - мониторинг прогресса парсинга

- **Статус парсера**: Метод `HBKParserOptimized.get_parse_status()`
  - Отслеживание статуса: idle/parsing/error/cancelled
  - Прогресс выполнения в процентах
  - Сообщение о текущем состоянии

- **Тесты**:
  - `test_optimized_parser.py`: Тест оптимизированного парсера
  - `test_api.py`: Тест API endpoints

### Изменено
- **Интеграция оптимизированного парсера**:
  - `src/core/lifespan.py`: Использует HBKParserOptimized
  - `src/routes/admin_routes.py`: Использует HBKParserOptimized, get_parse_status()
  - `src/parsers/sevenzip_manager.py`: Исправлены импорты констант

- **Документация** (обновлен порт 8000 → 8002):
  - `README.md`: Таблица MCP инструментов с примерами
  - `SETUP_GUIDE.md`: Исправлены все упоминания порта
  - `MCP_CONNECTION_GUIDE.md`: Исправлены все упоминания порта
  - `docs/API_REFERENCE.md`: Базовый URL обновлен
  - `docs/API_REFERENCE_v2.md`: Базовый URL обновлен
  - `docs/DOCKER_BUILD.md`: Порт docker-compose обновлен
  - `docs/VS_CODE_CONFIG.md`: Порт подключения обновлен
  - `docs/GZIP_COMPRESSION.md`: Команды мониторинга обновлены
  - `docs/IN_MEMORY_CACHE.md`: Команды мониторинга обновлены
  - `docs/CONTINUATION_GUIDE.md`: Команды мониторинга обновлены
  - `docs/STRUCTURED_LOGGING.md`: Команды мониторинга обновлены
  - `ТЕХНИЧЕСКОЕ_ЗАДАНИЕ.md`: Порт подключения обновлен

- **MCP Protocol**:
  - Исправлена JSON сериализация: MCPResponse → dict
  - Обновлены названия инструментов в документации
  - Добавлены примеры использования MCP tools

- **LRU кэш**: Исправлена производительность с O(n) на O(1)
  - Было: `list.remove()` и `list.pop(0)` - O(n)
  - Стало: `OrderedDict.move_to_end()` и `popitem(last=False)` - O(1)

### Удалено
- **Устаревшие файлы парсеров** (медленные версии):
  - `src/parsers/hbk_parser_v2.py`: Streaming подход (4-5 часов)
  - `src/parsers/sevenzip_stream_reader.py`: Извлечение по одному файлу
  - `src/core/file_cache.py`: Не использовался в production
  - `src/parsers/async_hbk_parser.py`: Не использовался
  - `src/main_temp.py`: Временная/дублирующая версия (1051 строка)
  - `src/core/_metrics.py`: Перемещен в metrics/
  - `test_*.py` (8 файлов): Временные тесты в корне проекта

- **Неиспользуемый код**:
  - `import uuid` из main.py (перемещен внутрь функции)
  - `HBKParser` импорт из main.py (оставлен только HBKParserError)
  - `pytest` и `pytest-asyncio` из requirements.txt

### Исправлено
- **build_exact_query**: Использован wildcard для full_path вместо term filter
  - Теперь находит объекты верхнего уровня (Массив, Строка, и т.д.)
  - Гибкий поиск с учетом полного пути документа

- **JSON сериализация MCP ответов**:
  - Все обработчики возвращают dict вместо MCPResponse
  - Корректная обработка ошибок в MCP endpoint

### Производительность
- **Парсинг HBK (39MB, 25511 HTML файлов)**:
  - Было: 10-15 минут (~28 док/с)
  - Стало: 44 секунды (566 док/с)
  - **Ускорение: в 20 раз**

- **Дедупликация**: 24869 документов (убрано 642 дубликата)

- **Production тест**: 52 секунды (парсинг + Elasticsearch)

### Code Review
- Исправлены критические замечания:
  - LRU кэш: OrderedDict вместо list
  - Дедупликация: seen_ids set для document IDs
  - Обработка отмены: CancelledError в async loop
  - Валидация: warning для малых файлов вместо error
  - Docstring: добавлены к публичным методам

---

## [1.3.0] - 2026-03-05

### Добавлено
- **Фаза 3: Core модули**
  - `src/core/metrics/collector.py`: MetricsCollector вынесен в отдельный модуль
  - `src/core/metrics/system_monitor.py`: SystemMonitor вынесен в отдельный модуль
  - `src/core/metrics/prometheus_formatter.py`: PrometheusFormatter вынесен в отдельный модуль
  - `src/core/cache/strategies.py`: Стратегии вытеснения LRU и LFU
  - Улучшенный декоратор `@cached` с поддержкой key_generator и condition

- **Фаза 4: Handlers и Formatter**
  - `src/handlers/formatters/search_formatter.py`: Форматтер поиска
  - `src/handlers/formatters/syntax_formatter.py`: Форматтер синтаксиса
  - `src/handlers/formatters/object_formatter.py`: Форматтер объектов
  - Удалено дублирование в mcp_formatter.py

- **Фаза 5: Indexer и Parser**
  - `IndexerMetrics`: Класс для метрик индексации
  - `IndexProgress`: Dataclass для отслеживания прогресса
  - Retry логика для отдельных документов
  - progress_callback для внешнего мониторинга

- **Фаза 6: Тесты и документация**
  - `tests/integration/test_search_integration.py`: Интеграционные тесты поиска
  - `tests/integration/test_mcp_integration.py`: Интеграционные тесты MCP
  - `tests/benchmarks/test_search_benchmark.py`: Бенчмарки поиска
  - `tests/benchmarks/test_cache_benchmark.py`: Бенчмарки кэша
  - `docs/architecture.md`: Документация по архитектуре

### Изменено
- **main.py**: Рефакторинг (Фаза 1, выполнено до этой сессии)
  - Lifespan management вынесен в отдельный модуль
  - Exception handlers вынесены в отдельный модуль
  - Middleware классы вынесены в отдельные файлы
  - Routes разделены на модули

- **Search Service** (Фаза 2, выполнено до этой сессии)
  - `src/search/cache_service.py`: Выделена логика кэширования
  - `src/search/circuit_breaker_handler.py`: Выделена fallback логика
  - Разделен на специализированные сервисы

- **src/core/metrics.py**: Теперь фасад (18 строк)
- **src/core/cache.py**: Добавлена поддержка стратегий LRU/LFU
- **src/handlers/mcp_formatter.py**: Теперь фасад (82 строки)
- **src/parsers/indexer.py**: Улучшена обработка ошибок и прогресс

### Улучшено
- **Качество кода**:
  - Все файлы < 300 строк (кроме фасадов)
  - DRY: удалено дублирование
  - Улучшенная модульность
- **Производительность**:
  - Cache hit rate улучшен с LRU/LFU стратегиями
  - Retry логика для индексации

---

## [1.2.0] - 2026-03-05

### Добавлено
- **SevenZipSessionManager**: Новый класс для управления сессиями 7zip
  - Асинхронные операции для улучшения производительности
  - Кэширование команды 7zip
  - Корректная очистка ресурсов
  - Тесты для нового модуля

### Изменено
- **hbk_parser.py**: Полный рефакторинг парсера
  - Выделен метод `_classify_files()` для классификации файлов
  - Выделен метод `_process_html_files()` для обработки HTML с прогрессом
  - Выделен метод `_process_category_batch()` для пакетной обработки
  - Улучшена обработка ошибок в `_create_document_from_html()`
  - Добавлен метод `_extract_html_content()` для извлечения содержимого
  - Добавлен метод `_cleanup_resources()` для очистки ресурсов
  - Добавлен dataclass `ParserProgress` для отслеживания прогресса
  - Возвращает `ParserProgress` из `_analyze_structure()`
  - Улучшено логирование прогресса парсинга

### Улучшено
- **Производительность**: 
  - Модульная структура для лучшего кэширования
  - Асинхронные I/O операции с 7zip
  - Прогресс-бар для мониторинга парсинга
- **Качество кода**:
  - Разделение ответственности между методами
  - Улучшенная типизация
  - Лучшая обработка ошибок

### Исправлено
- **Утечки ресурсов**: Добавлена корректная очистка 7zip сессии

---

## [1.1.0] - 2026-03-05

### Исправлено
- **hbk_parser.py**: Убран "костыль" с пропуском последних 48 записей (`entries[:-48]`)
  - Добавлен корректный timeout для анализа структуры (300 секунд)
  - Увеличен интервал проверки timeout с 10 до 100 записей
  - Теперь обрабатываются все записи из архива

### Улучшено
- **type hints**: Добавлены аннотации типов в основные модули
  - `src/parsers/hbk_parser.py`: `Tuple`, расширенные аннотации `__init__`
  - `src/core/elasticsearch.py`: `Callable`, `TypeVar` для декораторов
- **Документация**: Создан `.env.example` со всеми переменными окружения
- **Docker**: Создан `.dockerignore` для исключения лишних файлов из образа

### Удалено
- 23 временных файла:
  - Скрипты: `main_temp.py`, `full_indexing.py`, `local_mcp_server.py`, `mcp_wrapper.py`, `simple_http_mcp.py`
  - Конфигурации: `*_mcp_config.json`, `*_vscode_config.json`
  - Отчёты: `FINAL_SOLUTION.md`, `IMPROVEMENTS_REPORT.md`, `SSE_*.md`, `VS_CODE_*.md`
  - Документы: `WEBSOCKET_SUPPORT.md`, `REMOTE_DOCKER_SETUP.md`, `start_mcp_proxy.sh`

---

## [1.0.0] - 2026-03-01

### Добавлено
- **MCP Server**: Полноценный MCP сервер для поиска синтаксиса 1С
- **Elasticsearch**: Интеграция с Elasticsearch для полнотекстового поиска
- **HBK Parser**: Парсер .hbk архивов документации 1С
- **HTML Parser**: Парсер HTML файлов документации
- **Кэширование**: In-memory кэш с TTL и LRU eviction
- **Rate Limiting**: Ограничение скорости запросов по IP
- **Circuit Breaker**: Паттерн для устойчивости к сбоям Elasticsearch
- **Graceful Shutdown**: Корректная обработка завершения работы
- **Метрики**: Сбор метрик производительности
- **Логирование**: JSON форматирование, контекстное логирование с request_id

### Тестирование
- **Unit тесты**: MCP handlers, search service, cache, circuit breaker
- **Integration тесты**: API интеграция
- **Load тесты**: k6 и Locust сценарии

### CI/CD
- **GitHub Actions**: Настроены CI/CD pipeline
- **Docker**: Multi-stage сборка, non-root пользователь, health checks

### Документация
- `README.md`: Базовая документация
- `SETUP_GUIDE.md`: Руководство по установке
- `MCP_CONNECTION_GUIDE.md`: Настройка MCP клиентов
- `ТЕХНИЧЕСКОЕ_ЗАДАНИЕ.md`: Спецификация проекта

---

## Формат версий

Проект использует семантическую версионность [Semantic Versioning](https://semver.org/lang/ru/):

- **MAJOR** (1.0.0): Несовместимые изменения API
- **MINOR** (1.1.0): Новая функциональность (обратная совместимость)
- **PATCH** (1.0.1): Исправления ошибок (обратная совместимость)

## Формат Changelog

Основано на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).

Категории изменений:
- **Добавлено** — новые функции
- **Изменено** — изменения в существующем функционале
- **Устарело** — скоро будет удалено
- **Удалено** — удалённый функционал
- **Исправлено** — исправления ошибок
- **Безопасность** — улучшения безопасности
