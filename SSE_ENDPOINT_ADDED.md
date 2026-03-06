# Добавление поддержки SSE эндпоинта на /sse

## Дата: 6 марта 2026 г.

## Проблема

MCP сервер `1c-syntax-helper` не подключался в Qwen Code из-за несоответствия URL:
- Конфигурация Qwen: `http://localhost:8002/sse`
- Фактический эндпоинт сервера: `http://localhost:8002/mcp` (GET для SSE)

## Решение

Добавлен новый SSE роутер для поддержки эндпоинта `/sse` для совместимости с Qwen Code MCP конфигурацией.

## Изменения

### 1. Создан новый файл: `src/routes/sse_router.py`

Новый модуль содержит:
- `GET /sse` - SSE эндпоинт для установления соединения
- `POST /sse` - Обработчик JSON-RPC сообщений для SSE сессий

Функциональность:
- Инициализация SSE сессии с отправкой `event: endpoint`
- Поддержка ping/pong для поддержания соединения
- Таймаут сессии (1 час)
- Интеграция с хранилищем сессий `app.state.sse_sessions`
- Полная поддержка MCP протокола (initialize, tools/list, tools/call)

### 2. Обновлен: `src/routes/__init__.py`

Добавлен импорт нового роутера:
```python
from src.routes.sse_router import router as sse_router

__all__ = ["health_router", "admin_router", "mcp_router", "sse_router"]
```

### 3. Обновлен: `src/main.py`

Подключен новый роутер:
```python
from src.routes import health_router, admin_router, mcp_router, sse_router

app.include_router(sse_router)
```

## Тестирование

### Проверка доступности эндпоинтов

```bash
# SSE GET endpoint (возвращает 200, держит соединение)
curl -s -o nul -w "%{http_code}" http://localhost:8002/sse

# SSE POST endpoint (JSON-RPC)
curl -s -X POST http://localhost:8002/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

### Проверка маршрутов в OpenAPI spec

```bash
curl -s http://localhost:8002/openapi.json | \
  python -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(d.get('paths',{}).keys()))"
```

Ожидаемый результат включает `/sse`.

## Конфигурация Qwen

Файл: `%USERPROFILE%\.qwen\settings.json`

```json
{
  "mcpServers": {
    "1c-syntax-helper": {
      "url": "http://localhost:8002/sse",
      "timeout": 60,
      "type": "remote",
      "enabled": true
    }
  }
}
```

## Архитектура

```
                    ┌─────────────────────────────────┐
                    │  MCP Server (port 8002)         │
                    │                                 │
┌─────────────┐     │  ┌───────────┐  ┌───────────┐  │
│  Qwen Code  │─────┼──► /sse     │  │  /mcp     │  │
│  MCP Client │     │  │ (SSE)     │  │  (SSE)    │  │
└─────────────┘     │  └─────┬─────┘  └─────┬─────┘  │
                    │        │              │        │
                    │        └──────┬───────┘        │
                    │               │                │
                    │     ┌─────────▼─────────┐      │
                    │     │  app.state.       │      │
                    │     │  sse_sessions     │      │
                    │     └───────────────────┘      │
                    └─────────────────────────────────┘
```

## Совместимость

Теперь сервер поддерживает оба URL:
- `http://localhost:8002/sse` - для Qwen Code и других клиентов, ожидающих SSE на `/sse`
- `http://localhost:8002/mcp` - для существующих клиентов

## Статус

✅ Завершено
- [x] Создан `src/routes/sse_router.py`
- [x] Обновлен `src/routes/__init__.py`
- [x] Обновлен `src/main.py`
- [x] Пересобран Docker образ
- [x] Протестирован GET /sse
- [x] Протестирован POST /sse
- [x] Проверена интеграция с Qwen Code

## Примечания

- Оба эндпоинта (`/sse` и `/mcp`) используют общее хранилище сессий
- Таймаут сессии: 3600 секунд (1 час)
- Ping интервал: 30 секунд
- Максимальный размер очереди сообщений: 100
