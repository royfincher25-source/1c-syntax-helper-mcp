# Design: Рефакторинг форматирования и констант

**Date:** 2026-03-07  
**Status:** Draft

---

## Цель

Устранить дублирование кода в системе форматирования и константах.

---

## Проблемы

### 1. Дублирование SearchFormatter

Два разных класса с одинаковым именем в разных местах:
- `src/search/formatter.py` — форматтер для Elasticsearch
- `src/handlers/formatters/search_formatter.py` — дубликат для MCP

### 2. Дублирование констант

SSE константы определены в двух местах:
- `src/core/constants.py`
- `src/routes/sse_router.py`

---

## Решение

### 1. Объединить SearchFormatter

**Удалить:**
- `src/handlers/formatters/search_formatter.py`
- `src/handlers/formatters/syntax_formatter.py`
- `src/handlers/formatters/object_formatter.py`
- `src/handlers/formatters/__init__.py`

**Расширить** `src/search/formatter.py`:
- Добавить методы MCP-форматирования
- Сохранить существующие методы

**Обновить** `src/handlers/mcp_formatter.py`:
- Использовать единый `SearchFormatter` из `src.search.formatter`

### 2. Объединить константы

**Удалить** из `src/routes/sse_router.py`:
- `SSE_QUEUE_MAX_SIZE`
- `SSE_PING_INTERVAL_SECONDS`
- `SSE_SESSION_TIMEOUT_SECONDS`

**Импортировать** из `src.core.constants` в `sse_router.py`

---

## План

1. Добавить методы в `src/search/formatter.py`:
   - `format_search_header(count, query)`
   - `format_search_result(result, index)`
   - `format_context_search(results, query, context)`
   - `format_syntax_info(result)`
   - `format_quick_reference(result)`
   - `format_object_members_list(...)`

2. Обновить `src/handlers/mcp_formatter.py` — использовать расширенный SearchFormatter

3. Удалить директорию `src/handlers/formatters/`

4. Удалить локальные константы из `src/routes/sse_router.py`, добавить импорт из `constants.py`

5. Запустить тесты — проверить что ничего не сломалось

---

## Риски

- Изменение формата вывода может сломать существующих клиентов
- Минимальный риск — методы имеют тот же интерфейс

---

## Результат

- Единый источник истины для форматирования
- Устранено дублирование констант
- Проще поддержка кода
