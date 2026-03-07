# Design: Исправление проблем аудита

**Date:** 2026-03-07  
**Status:** Draft

---

## Цель

Исправить критические и средние проблемы, выявленные аудитом проекта.

> **Исключено:** Механизм аутентификации (по требованию)

---

## HIGH Priority — исправить

### 1. CORS `allow_origins=["*"]`

**Проблема:** `src/main.py:35` — разрешены любые источники

**Решение:** Заменить на конкретный список или `allow_origin_regex`

```python
# Вариант 1: Конкретный список
allow_origins = ["http://localhost:3000", "http://localhost:5173"]

# Вариант 2: Regex для динамических origins
allow_origin_regex = r"https://.*\.yourdomain\.com"
```

---

### 2. Bare `except Exception:`

**Проблема:** 6 мест с `except Exception:` без специфической обработки

**Решение:** Заменить на конкретные исключения

```python
# Было
except Exception as e:
    logger.error(f"Error: {e}")

# Стало
except (ConnectionError, TimeoutError) as e:
    logger.error(f"Connection failed: {e}")
except ValueError as e:
    logger.warning(f"Invalid input: {e}")
except Exception as e:
    logger.exception(f"Unexpected error: {e}")
```

**Файлы для проверки:**
- `src/handlers/mcp_handlers.py`
- `src/search/find_help_service.py`
- `src/parsers/hbk_parser.py`

---

### 3. Глобальное состояние сервисов

**Проблема:** Глобальные экземпляры затрудняют тестирование

**Решение:** Использовать Depends() в FastAPI

```python
# Было (глобально)
search_service = SearchService()

# Стало
def get_search_service() -> SearchService:
    return SearchService()

@app.get("/search")
async def search(q: str, service: SearchService = Depends(get_search_service)):
    return await service.search(q)
```

---

### 4. asyncio.run() в синхронном контексте

**Проблема:** `hbk_parser.py` использует `asyncio.run()` внутри асинхронного кода

**Решение:** Использовать `await` напрямую или вынести в отдельную функцию

---

## MEDIUM Priority — исправить

### 5. Неполные type hints в config.py

**Проблема:** Числовые параметры определены как `str`, требуют преобразования

**Решение:** Использовать `Field(..., validation_alias=...)` или Pydantic v2 `BeforeValidator`

---

### 6. Дублирование: hbk_parser.py + hbk_parser_optimized.py

**Проблема:** Две версии парсера

**Решение:** Объединить в один класс с оптимизированной логикой

---

### 7. Timeout константы не централизованы

**Проблема:** HBK_LIST_TIMEOUT, HBK_FILE_READ_TIMEOUT используются непоследовательно

**Решение:** Добавить в `src/core/constants.py`

---

## LOW Priority — исправить

### 8. max_line_length=127 → 100

**Проблема:** `.github/workflows/ci.yml` — не соответствует PEP8

**Решение:** Изменить в CI/CD

---

## Не включать

- ❌ Аутентификация (по требованию пользователя)

---

## План

1. Исправить CORS (allow_origins)
2. Убрать bare except — заменить на конкретные исключения
3. Рефакторинг глобальных сервисов → Depends()
4. Исправить asyncio.run() в hbk_parser.py
5. Добавить type hints в config.py
6. Объединить hbk_parser.py + hbk_parser_optimized.py
7. Централизовать timeout константы
8. Исправить max_line_length=100
9. Запустить тесты

---

## Риски

- Рефакторинг глобальных сервисов может сломать существующий код
- Тестирование зависит от ES — нужно мокирование

---

## Результат

- Повышение безопасности (CORS)
- Улучшение качества кода (type hints, exceptions)
- Соответствие PEP8
- Централизованное управление константами
