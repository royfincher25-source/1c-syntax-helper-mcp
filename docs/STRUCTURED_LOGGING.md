# 📝 Structured Logging с Request ID

## 🎯 Обзор

Система логирования поддерживает **structured JSON формат** с автоматическим добавлением **request_id** для трассировки запросов.

---

## 📊 Возможности

### 1. JSON формат логов

Все логи выводятся в JSON формате:

```json
{
  "timestamp": "2026-03-05T12:34:56.789Z",
  "level": "INFO",
  "logger": "src.main",
  "message": "Request completed: GET /health - 200",
  "module": "main",
  "function": "health_check",
  "line": 305,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_ip": "192.168.1.100",
  "duration_ms": 45.23,
  "status_code": 200
}
```

### 2. Request ID для трассировки

Каждый запрос получает уникальный `request_id`:
- Генерируется через `uuid.uuid4()`
- Добавляется в заголовок ответа `X-Request-ID`
- Включается во все логи запроса
- Позволяет отследить весь путь запроса

### 3. Контекст запроса

Автоматически добавляется:
- `request_id` - уникальный идентификатор
- `client_ip` - IP адрес клиента
- `duration_ms` - время выполнения запроса
- `status_code` - HTTP статус ответа

---

## 🔧 Использование

### Базовое логирование

```python
from src.core.logging import get_logger

logger = get_logger(__name__)

logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
logger.debug("Отладочное сообщение")
```

### Логирование с контекстом

```python
from src.core.logging import get_logger, LogContext

# Установка контекста
LogContext.set_request_id("my-request-123")
LogContext.set_client_ip("192.168.1.100")
LogContext.set_start_time(time.time())

# Логирование с дополнительными данными
logger.info(
    "Запрос обработан",
    extra={
        "extra_data": {
            "method": "POST",
            "path": "/api/search",
            "status_code": 200,
            "search_query": "СтрДлина",
        }
    }
)

# Очистка контекста
LogContext.clear()
```

### Логирование исключений

```python
try:
    result = await search_service.find_help_by_query(query)
except Exception as e:
    logger.error(
        "Ошибка поиска",
        extra={
            "extra_data": {
                "error": str(e),
                "error_type": type(e).__name__,
                "query": query,
            }
        },
        exc_info=True
    )
```

---

## 📁 Файлы логов

### Консоль (stdout)

- **Уровень:** INFO и выше
- **Формат:** JSON (production) или текст (debug)

### Файл app.log

- **Путь:** `data/logs/app.log`
- **Уровень:** DEBUG и выше
- **Формат:** JSON

### Файл errors.log

- **Путь:** `data/logs/errors.log`
- **Уровень:** ERROR и выше
- **Формат:** JSON

---

## 🧪 Тестирование

### Запуск тестового скрипта

```bash
python tests/test_logging.py
```

### Проверка логов

```bash
# Просмотр логов в реальном времени
tail -f data/logs/app.log | jq

# Поиск по request_id
grep "550e8400-e29b-41d4-a716-446655440000" data/logs/app.log | jq

# Поиск ошибок
grep '"level": "ERROR"' data/logs/app.log | jq
```

---

## 📊 Примеры логов

### Начало запроса

```json
{
  "timestamp": "2026-03-05T12:34:56.000Z",
  "level": "INFO",
  "logger": "src.main",
  "message": "Request started: POST /mcp",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_ip": "192.168.1.100",
  "method": "POST",
  "path": "/mcp",
  "query_params": null
}
```

### Завершение запроса

```json
{
  "timestamp": "2026-03-05T12:34:56.045Z",
  "level": "INFO",
  "logger": "src.main",
  "message": "Request completed: POST /mcp - 200",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_ip": "192.168.1.100",
  "duration_ms": 45.23,
  "status_code": 200
}
```

### Ошибка запроса

```json
{
  "timestamp": "2026-03-05T12:35:00.123Z",
  "level": "ERROR",
  "logger": "src.main",
  "message": "Request failed: GET /api/error - 500",
  "request_id": "660e8400-e29b-41d4-a716-446655440001",
  "client_ip": "192.168.1.100",
  "duration_ms": 12.45,
  "error": "Internal server error",
  "error_type": "HTTPException",
  "exception": "Traceback (most recent call last):\n  ..."
}
```

---

## 🔍 Анализ логов

### Поиск по request_id

```bash
# Найти все логи для конкретного запроса
REQUEST_ID="550e8400-e29b-41d4-a716-446655440000"
grep "$REQUEST_ID" data/logs/app.log | jq
```

### Подсчёт ошибок по типам

```bash
grep '"level": "ERROR"' data/logs/app.log | \
  jq -r '.error_type' | sort | uniq -c | sort -rn
```

### Среднее время ответа

```bash
grep '"duration_ms"' data/logs/app.log | \
  jq -s '[.[].duration_ms] | add / length'
```

### Топ медленных запросов

```bash
grep '"duration_ms"' data/logs/app.log | \
  jq -s 'sort_by(.duration_ms) | reverse | .[0:10]'
```

---

## 🛠️ Конфигурация

### Переменные окружения

```bash
# Уровень логирования
LOG_LEVEL=INFO

# Режим разработки (текстовый формат вместо JSON)
DEBUG=true
```

### Настройка в config.py

```python
class Settings(BaseSettings):
    log_level: str = "INFO"
    logs_directory: str = "data/logs"
    debug: bool = False
```

---

## 📈 Метрики

### Собираемые метрики

- `request.duration` - время выполнения запроса
- `health_check.requests` - количество проверок здоровья
- `errors.validation` - ошибки валидации
- `errors.parser` - ошибки парсера
- `errors.general` - общие ошибки

### Просмотр метрик

```bash
# Через API
curl http://localhost:8002/metrics

# Через логи
grep '"duration_ms"' data/logs/app.log | jq
```

---

## 🎓 Лучшие практики

### ✅ Делайте

- Используйте `request_id` для трассировки
- Добавляйте контекст через `extra_data`
- Логируйте исключения с `exc_info=True`
- Используйте соответствующие уровни логирования

### ❌ Не делайте

- Не логируйте чувствительные данные (пароли, токены)
- Не используйте `print()` для логирования
- Не логируйте слишком много отладочной информации в production
- Не игнорируйте исключения без логирования

---

## 🔗 Ссылки

- [logging.py](../src/core/logging.py)
- [request_logging_middleware.py](../src/core/request_logging_middleware.py)
- [test_logging.py](../tests/test_logging.py)

---

**Обновлено:** 5 марта 2026  
**Версия:** 2.0 (Structured Logging с Request ID)
