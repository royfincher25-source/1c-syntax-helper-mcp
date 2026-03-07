# Audit Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Исправить критические и средние проблемы из аудита проекта

**Architecture:** Поэтапное исправление: HIGH → MEDIUM → LOW приоритеты

**Tech Stack:** Python, FastAPI, Pytest

---

## Task 1: Исправить CORS

**Files:**
- Modify: `src/main.py`

**Step 1: Найти текущую конфигурацию CORS**

```bash
grep -n "allow_origins" src/main.py
```

**Step 2: Заменить на безопасную конфигурацию**

Было:
```python
allow_origins=["*"]
```

Стало:
```python
allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8002"],
allow_origin_regex=r"https://.*\.yourdomain\.com",
```

**Step 3: Commit**

```bash
git add src/main.py
git commit -m "fix: ограничить CORS origins"
```

---

## Task 2: Убрать bare except

**Files:**
- Modify: `src/handlers/mcp_handlers.py`
- Modify: `src/search/find_help_service.py`
- Modify: `src/parsers/hbk_parser.py`

**Step 1: Найти все bare except**

```bash
grep -rn "except Exception:" src/
```

**Step 2: Для каждого места заменить на конкретные исключения**

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

**Step 3: Commit**

```bash
git add src/
git commit -m "fix: заменить bare except на конкретные исключения"
```

---

## Task 3: Рефакторинг глобальных сервисов

**Files:**
- Modify: `src/main.py`
- Modify: `src/routes/mcp_routes.py`

**Step 1: Прочитать текущую инициализацию сервисов**

```bash
grep -n "search_service\|es_client" src/main.py | head -20
```

**Step 2: Добавить Depends() фабрики**

```python
from fastapi import Depends

def get_search_service() -> SearchService:
    return search_service

@app.get("/search")
async def search(q: str, service: SearchService = Depends(get_search_service)):
    return await service.search(q)
```

**Step 3: Commit**

```bash
git add src/main.py src/routes/mcp_routes.py
git commit -m "refactor: добавить Depends() для сервисов"
```

---

## Task 4: Исправить asyncio.run()

**Files:**
- Modify: `src/parsers/hbk_parser.py`

**Step 1: Найти asyncio.run()**

```bash
grep -n "asyncio.run" src/parsers/hbk_parser.py
```

**Step 2: Заменить на await**

Было:
```python
def sync_function():
    asyncio.run(async_func())
```

Стало:
```python
async def wrapper():
    await async_func()
```

**Step 3: Commit**

```bash
git add src/parsers/hbk_parser.py
git commit -m "fix: убрать asyncio.run() из синхронного контекста"
```

---

## Task 5: Type hints в config.py

**Files:**
- Modify: `src/core/config.py`

**Step 1: Прочитать config.py**

```bash
read src/core/config.py
```

**Step 2: Добавить правильные type hints**

```python
class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8002, ge=1, le=65535)
    workers: int = Field(default=1, ge=1, le=32)
    log_level: str = "INFO"
```

**Step 3: Commit**

```bash
git add src/core/config.py
git commit -m "fix: добавить type hints в config.py"
```

---

## Task 6: Объединить hbk_parser

**Files:**
- Modify: `src/parsers/hbk_parser.py`
- Delete: `src/parsers/hbk_parser_optimized.py`

**Step 1: Прочитать оба файла**

```bash
read src/parsers/hbk_parser.py
read src/parsers/hbk_parser_optimized.py
```

**Step 2: Объединить логику в один класс**

Оставить лучшие методы из обоих файлов

**Step 3: Commit**

```bash
git add src/parsers/hbk_parser.py
git rm src/parsers/hbk_parser_optimized.py
git commit -m "refactor: объединить hbk_parser и hbk_parser_optimized"
```

---

## Task 7: Централизовать timeout константы

**Files:**
- Modify: `src/core/constants.py`
- Modify: `src/parsers/hbk_parser.py`

**Step 1: Прочитать constants.py**

```bash
read src/core/constants.py
```

**Step 2: Добавить timeout константы**

```python
# HBK Timeouts
HBK_LIST_TIMEOUT = 30
HBK_FILE_READ_TIMEOUT = 60
```

**Step 3: Импортировать в hbk_parser.py**

```python
from src.core.constants import HBK_LIST_TIMEOUT, HBK_FILE_READ_TIMEOUT
```

**Step 4: Commit**

```bash
git add src/core/constants.py src/parsers/hbk_parser.py
git commit -m "refactor: централизовать timeout константы"
```

---

## Task 8: Исправить max_line_length

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Найти max_line_length**

```bash
grep -n "max-line-length" .github/workflows/ci.yml
```

**Step 2: Заменить на 100**

```yaml
args: ["--max-line-length=100", "--extend-ignore=E203"]
```

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "fix: исправить max_line_length на 100"
```

---

## Task 9: Запустить тесты

**Step 1: Запустить все тесты**

```bash
pytest tests/ -v --tb=short
```

**Step 2: Если есть ошибки — исправить**

**Step 3: Commit**

```bash
git add -A
git commit -m "test: финальный запуск тестов после аудита"
```

---

## Plan Complete

**Проверить что:**
1. CORS ограничен
2. Нет bare except
3. Сервисы используют Depends()
4. Нет asyncio.run() в синхронном контексте
5. Type hints в config.py
6. Один hbk_parser.py
7. Timeout константы централизованы
8. max_line_length=100
9. Все тесты проходят
