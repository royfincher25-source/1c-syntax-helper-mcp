# Анализ SSE подключения в 1C Syntax Helper MCP

## Краткое резюме

В проекте **реализована поддержка SSE (Server-Sent Events)** для MCP протокола, но имеются **критические архитектурные проблемы**, требующие исправления.

## Текущее состояние

### ✅ Реализованные компоненты

1. **SSE Endpoint** (`GET /mcp`)
   - Генерация session_id для каждого подключения
   - Отправка `event: endpoint` с URL для POST запросов
   - Поддержка ping каждые 30 секунд
   - Очистка сессий при отключении клиента

2. **POST Endpoint** (`POST /mcp`)
   - Поддержка JSON-RPC запросов
   - Обработка `session_id` query параметра
   - Отправка ответов в SSE очередь
   - Прямой ответ без SSE (если session_id не указан)

3. **WebSocket Endpoint** (`/mcp/ws`)
   - Альтернативный транспорт для MCP протокола
   - Поддержка JSON-RPC через WebSocket

4. **MCP Tools**
   - `find_1c_help` - универсальный поиск
   - `get_syntax_info` - детальная информация
   - `get_quick_reference` - краткая справка
   - `search_by_context` - контекстный поиск
   - `list_object_members` - методы объекта

### 🔴 Найденные проблемы

| # | Проблема | Критичность | Файлы |
|---|----------|-------------|-------|
| 1 | **Дублирование маршрутов** между `main.py` и `mcp_routes.py` | 🔴 Критическая | main.py, mcp_routes.py |
| 2 | **Отсутствие инициализации** `sse_sessions` при startup | 🔴 Критическая | lifespan.py |
| 3 | **Некорректный `router.app`** в mcp_routes.py | 🔴 Критическая | mcp_routes.py:161-163 |
| 4 | **Утечки памяти** - неограниченные очереди | 🔴 Критическая | main.py, mcp_routes.py |
| 5 | Нет общего таймаута сессии | 🟡 Средняя | main.py, mcp_routes.py |
| 6 | Гонка условий при создании сессии | 🟡 Средняя | main.py, mcp_routes.py |
| 7 | Несогласованное использование `app.state` | 🟡 Средняя | main.py, mcp_routes.py |
| 8 | Отсутствуют метрики SSE | 🟢 Низкая | - |

## Как это работает (сейчас)

### Схема SSE подключения

```
┌─────────────┐                          ┌──────────────┐
│   Клиент    │                          │  MCP Сервер  │
│  (VS Code)  │                          │ (FastAPI)    │
└──────┬──────┘                          └──────┬───────┘
       │                                        │
       │  1. GET /mcp (Accept: text/event-stream)
       │───────────────────────────────────────>│
       │                                        │ Создаёт session_id
       │                                        │ Создаёт asyncio.Queue
       │                                        │ Сохраняет в app.state.sse_sessions
       │                                        │
       │  2. event: endpoint
       │     data: /mcp?session_id=abc123
       │<───────────────────────────────────────│
       │                                        │
       │  3. POST /mcp?session_id=abc123
       │     {"jsonrpc": "2.0", "method": "..."}
       │───────────────────────────────────────>│
       │                                        │ Обрабатывает запрос
       │                                        │ Кладёт ответ в queue
       │                                        │
       │  4. event: message
       │     data: {"jsonrpc": "2.0", "result": ...}
       │<───────────────────────────────────────│
       │                                        │
       │  5. event: ping (каждые 30 сек)
       │     data: {"timestamp": 1234567890}
       │<───────────────────────────────────────│
```

### Пример SSE ответа

```
event: endpoint
data: /mcp?session_id=550e8400-e29b-41d4-a716-446655440000

event: message
data: {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}

event: ping
data: {"timestamp":1709823456}
```

## План исправления

### Этап 1: Устранение дублирования маршрутов

**Файл:** `src/main.py`

**Действия:**
- Удалить `@app.get("/mcp/tools")` (строки 269-376)
- Удалить `@app.get("/mcp")` (строки 380-424)
- Удалить `@app.post("/mcp")` (строки 427-467)
- Удалить `@app.websocket("/mcp/ws")` (строки 597-668)
- Удалить `process_single_jsonrpc_request` (дублируется)
- Удалить `mcp_endpoint_handler` (используется в роутере)

**Оставить:**
```python
from src.routes import health_router, admin_router, mcp_router

app.include_router(health_router)
app.include_router(admin_router)
app.include_router(mcp_router)
```

### Этап 2: Инициализация sse_sessions при startup

**Файл:** `src/core/lifespan.py`

**Добавить:**
```python
async def startup(self, app: FastAPI) -> None:
    # ... существующий код ...
    
    # Инициализация хранилища SSE сессий
    app.state.sse_sessions = {}
    logger.info("SSE sessions storage initialized")
```

### Этап 3: Исправление router.app в mcp_routes.py

**Файл:** `src/routes/mcp_routes.py`

**Заменить (строки 161-163):**
```python
# БЫЛО (неправильно):
if not hasattr(router, 'app'):
    router.app = router.router
router.app.state.sse_sessions[session_id] = message_queue

# СТАЛО (правильно):
async def sse_event_stream(request: Request):  # ← Добавить request
    session_id = str(uuid.uuid4())
    message_queue = asyncio.Queue(maxsize=SSE_QUEUE_MAX_SIZE)
    
    # Используем request.app.state
    request.app.state.sse_sessions[session_id] = message_queue
```

### Этап 4: Добавление ограничений и таймаутов

**Файл:** `src/core/constants.py`

**Добавить константы:**
```python
# SSE конфигурация
SSE_QUEUE_MAX_SIZE = 100  # Максимум 100 сообщений в очереди
SSE_PING_INTERVAL_SECONDS = 30  # Интервал ping
SSE_SESSION_TIMEOUT_SECONDS = 3600  # Максимальное время жизни сессии (1 час)
```

### Этап 5: Добавление метрик

**Файл:** `src/core/metrics/collector.py`

**Добавить метрики:**
- `sse.sessions.active` - количество активных сессий
- `sse.messages.sent` - количество отправленных сообщений
- `sse.messages.dropped` - количество потерянных сообщений
- `sse.errors.queue_full` - ошибки переполнения очереди

## Проверка работоспособности

### Тестовый скрипт

Создан файл `tests/test_sse_connection.py` для проверки SSE подключения.

**Запуск:**
```bash
# Активируйте виртуальное окружение
.\venv\Scripts\Activate.ps1

# Запустите сервер
python -m uvicorn src.main:app --host 0.0.0.0 --port 8002

# В другом окне запустите тест
python tests/test_sse_connection.py
```

### Ожидаемые результаты

```
============================================================
Тестирование SSE подключения к MCP серверу
============================================================

[1] Проверка доступности сервера...
✅ Сервер доступен: {'status': 'healthy', ...}

[2] Проверка SSE endpoint (/mcp GET)...
✅ SSE соединение установлено, статус: 200
   Событие 1: event: endpoint
   Событие 2: data: /mcp?session_id=550e8400-e29b-41d4-a716-446655440000
✅ Получен session_id: 550e8400-e29b-41d4-a716-446655440000
✅ Endpoint URL: /mcp?session_id=550e8400-e29b-41d4-a716-446655440000

[3] Отправка JSON-RPC запроса через POST /mcp?session_id=...
   Статус ответа: 200
   Ответ: {"jsonrpc": "2.0", "id": 1, "result": {...}}

[4] Проверка прямого POST запроса (без SSE)...
   Статус ответа: 200
   ✅ Прямой POST работает

[5] Проверка WebSocket endpoint (/mcp/ws)...
✅ WebSocket соединение установлено
   ✅ Получен ответ через WebSocket

============================================================
✅ Тестирование завершено
============================================================
```

## Рекомендации по использованию SSE

### Для VS Code MCP Extension

**Конфигурация в `settings.json`:**

```json
{
  "mcp.servers": {
    "1c-syntax-helper": {
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-d", "@-",
        "http://localhost:8002/mcp"
      ]
    }
  }
}
```

**Примечание:** VS Code MCP Extension использует HTTP POST напрямую, без SSE. SSE требуется для клиентов, поддерживающих streaming.

### Для кастомных MCP клиентов

**Пример подключения через JavaScript:**

```javascript
const eventSource = new EventSource('http://localhost:8002/mcp');

eventSource.addEventListener('endpoint', (event) => {
  console.log('Endpoint URL:', event.data);
  // event.data = "/mcp?session_id=abc123"
  
  // Отправляем JSON-RPC запрос
  fetch('http://localhost:8002' + event.data, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/list',
      params: {}
    })
  });
});

eventSource.addEventListener('message', (event) => {
  const response = JSON.parse(event.data);
  console.log('Получен ответ:', response);
});

eventSource.addEventListener('ping', (event) => {
  console.log('Ping received, соединение активно');
});
```

## Альтернативы SSE

### 1. Прямой HTTP POST (рекомендуется для VS Code)

**Преимущества:**
- Проще в реализации
- Нет состояния на сервере
- Лучше кэшируется

**Недостатки:**
- Нет push-уведомлений
- Клиент должен опрашивать сервер

### 2. WebSocket (рекомендуется для интерактивных клиентов)

**Преимущества:**
- Двусторонняя связь
- Низкая задержка
- Поддержка бинарных данных

**Недостатки:**
- Сложнее в реализации
- Требует постоянного соединения

### 3. SSE (текущая реализация)

**Преимущества:**
- Простой протокол
- Автоматическое переподключение
- Поддержка серверных push-уведомлений

**Недостатки:**
- Только односторонняя связь (сервер → клиент)
- Требует дополнительного POST endpoint для запросов

## Статус

- [x] SSE endpoint реализован
- [x] POST endpoint с session_id поддержкой
- [x] WebSocket endpoint
- [ ] **Требуется:** Устранение дублирования маршрутов
- [ ] **Требуется:** Инициализация sse_sessions при startup
- [ ] **Требуется:** Исправление router.app
- [ ] **Требуется:** Добавление ограничений очереди
- [ ] **Требуется:** Добавление таймаутов
- [ ] **Требуется:** Добавление метрик

## Контакты

По вопросам обращайтесь к документации:
- [MCP_CONNECTION_GUIDE.md](MCP_CONNECTION_GUIDE.md) - Настройка клиентов
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Развертывание
- [ТЕХНИЧЕСКОЕ_ЗАДАНИЕ.md](ТЕХНИЧЕСКОЕ_ЗАДАНИЕ.md) - Требования
