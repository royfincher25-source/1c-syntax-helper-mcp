# План исправления SSE реализации

## Обзор

Этот документ содержит пошаговый план исправления критических проблем в реализации SSE (Server-Sent Events) для MCP протокола.

## Приоритеты

| Приоритет | Задачи |
|-----------|--------|
| **P0** | Критические проблемы (блокируют работу) |
| **P1** | Важные проблемы (утечки, гонки) |
| **P2** | Улучшения (метрики, таймауты) |

---

## P0: Критические исправления

### Задача 1: Удаление дублирования маршрутов

**Файл:** `src/main.py`

**Проблема:** Маршруты `/mcp` определены дважды - в `main.py` и `mcp_routes.py`

**Действия:**

1. Открыть `src/main.py`
2. Удалить следующие секции:
   - `@app.get("/mcp/tools")` (строки ~269-376)
   - `@app.get("/mcp")` (строки ~380-424)
   - `@@app.post("/mcp")` (строки ~427-467)
   - `@app.websocket("/mcp/ws")` (строки ~597-668)
   - `process_single_jsonrpc_request()` (дублирующаяся функция)
   - `mcp_endpoint_handler()` (дублирующаяся функция)

3. Убедиться, что подключён роутер:
```python
from src.routes import mcp_router
app.include_router(mcp_router)
```

**Критерии готовности:**
- [ ] FastAPI запускается без ошибок о дублировании маршрутов
- [ ] `GET /mcp` работает через роутер
- [ ] `POST /mcp` работает через роутер
- [ ] `GET /mcp/tools` работает через роутер
- [ ] `WebSocket /mcp/ws` работает через роутер

---

### Задача 2: Инициализация sse_sessions при startup

**Файл:** `src/core/lifespan.py`

**Проблема:** `app.state.sse_sessions` не инициализируется при запуске

**Действия:**

1. Открыть `src/core/lifespan.py`
2. Найти метод `startup()`
3. Добавить инициализацию после подключения к Elasticsearch:

```python
async def startup(self, app: FastAPI) -> None:
    logger.info("Starting application...")
    
    # ... существующий код (подключение к ES, кэш, и т.д.) ...
    
    # Инициализация хранилища SSE сессий
    app.state.sse_sessions = {}
    logger.info("SSE sessions storage initialized")
    
    logger.info("Application started successfully")
```

**Критерии готовности:**
- [ ] `app.state.sse_sessions` существует до первого запроса
- [ ] В логах появляется сообщение "SSE sessions storage initialized"
- [ ] POST запросы с session_id работают корректно

---

### Задача 3: Исправление router.app в mcp_routes.py

**Файл:** `src/routes/mcp_routes.py`

**Проблема:** Некорректное использование `router.app = router.router`

**Действия:**

1. Открыть `src/routes/mcp_routes.py`
2. Найти SSE endpoint (строка ~151)
3. Изменить сигнатуру функции:

```python
# БЫЛО:
@router.get("")
async def mcp_sse_endpoint():
    async def sse_event_stream():
        # ...
        if not hasattr(router, 'app'):
            router.app = router.router  # ← ОШИБКА
        router.app.state.sse_sessions[session_id] = message_queue

# СТАЛО:
@router.get("")
async def mcp_sse_endpoint(request: Request):
    async def sse_event_stream():
        # ...
        request.app.state.sse_sessions[session_id] = message_queue
```

4. Аналогично исправить WebSocket endpoint (строка ~347):

```python
# БЫЛО:
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # ...
    websocket.app.state.sse_sessions[session_id] = message_queue

# СТАЛО:
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # ...
    # Используем websocket.application или передаём request
    # Для WebSocket лучше использовать глобальный app из main.py
```

**Для WebSocket правильное решение:**

```python
from src.main import app  # Импортировать глобальный app

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = str(uuid.uuid4())
    message_queue = asyncio.Queue(maxsize=SSE_QUEUE_MAX_SIZE)
    app.state.sse_sessions[session_id] = message_queue  # ← Используем глобальный app
```

**Критерии готовности:**
- [ ] Нет ошибки `AttributeError` при доступе к `sse_sessions`
- [ ] SSE сессии создаются корректно
- [ ] WebSocket сессии создаются корректно

---

## P1: Важные исправления

### Задача 4: Добавление ограничений очереди

**Файл:** `src/core/constants.py`

**Действия:**

1. Добавить константы:

```python
# SSE конфигурация
SSE_QUEUE_MAX_SIZE = 100  # Максимум 100 сообщений в очереди
SSE_PING_INTERVAL_SECONDS = 30  # Интервал ping
SSE_SESSION_TIMEOUT_SECONDS = 3600  # Максимальное время жизни сессии (1 час)
```

2. Обновить `src/routes/mcp_routes.py`:

```python
from src.core.constants import SSE_QUEUE_MAX_SIZE

@router.get("")
async def mcp_sse_endpoint(request: Request):
    async def sse_event_stream():
        session_id = str(uuid.uuid4())
        message_queue = asyncio.Queue(maxsize=SSE_QUEUE_MAX_SIZE)  # ← Ограничение
        request.app.state.sse_sessions[session_id] = message_queue
```

3. Обработать переполнение очереди в POST endpoint:

```python
@router.post("")
async def mcp_sse_or_jsonrpc_endpoint(request: Request):
    # ... обработка запроса ...
    
    if session_id and session_id in request.app.state.sse_sessions:
        queue = request.app.state.sse_sessions[session_id]
        try:
            queue.put_nowait(response_data)  # ← Неблокирующая вставка
        except asyncio.QueueFull:
            logger.warning(f"Queue full for session {session_id}, dropping message")
            # Можно вернуть ошибку клиенту
            return JSONResponse(
                status_code=503,
                content={"error": "Message queue full, try again later"}
            )
        return JSONResponse(content={"status": "queued"})
```

**Критерии готовности:**
- [ ] Очередь не растёт бесконечно
- [ ] При переполнении возвращается ошибка 503
- [ ] В логах появляются предупреждения о переполнении

---

### Задача 5: Добавление таймаута сессии

**Файл:** `src/routes/mcp_routes.py`

**Действия:**

```python
from src.core.constants import SSE_SESSION_TIMEOUT_SECONDS

@router.get("")
async def mcp_sse_endpoint(request: Request):
    async def sse_event_stream():
        session_id = str(uuid.uuid4())
        message_queue = asyncio.Queue(maxsize=SSE_QUEUE_MAX_SIZE)
        request.app.state.sse_sessions[session_id] = message_queue
        
        session_start = time.time()  # ← Запоминаем время начала
        
        try:
            yield f"event: endpoint\n"
            yield f"data: /mcp?session_id={session_id}\n\n"
            
            while True:
                # Проверка общего таймаута
                if time.time() - session_start > SSE_SESSION_TIMEOUT_SECONDS:
                    logger.info(f"Session timeout for {session_id}")
                    break
                
                try:
                    message = await asyncio.wait_for(
                        message_queue.get(),
                        timeout=SSE_PING_INTERVAL_SECONDS
                    )
                    yield f"event: message\n"
                    yield f"data: {json.dumps(message)}\n\n"
                    
                except asyncio.TimeoutError:
                    yield f"event: ping\n"
                    yield f"data: {json.dumps({'timestamp': int(time.time())})}\n\n"
                    
        except asyncio.CancelledError:
            logger.info(f"SSE соединение закрыто для session {session_id}")
            raise
        finally:
            # Очистка сессии
            if session_id in request.app.state.sse_sessions:
                del request.app.state.sse_sessions[session_id]

    return StreamingResponse(...)
```

**Критерии готовности:**
- [ ] Сессии закрываются через 1 час
- [ ] В логах появляется сообщение "Session timeout"
- [ ] Ресурсы освобождаются корректно

---

### Задача 6: Обработка CancelledError

**Файл:** `src/routes/mcp_routes.py`

**Действия:**

Добавить обработку `CancelledError` во все endpoint'ы:

```python
@router.post("")
async def mcp_sse_or_jsonrpc_endpoint(request: Request):
    try:
        # ... обработка ...
    except asyncio.CancelledError:
        logger.info(f"Request cancelled for session {session_id}")
        raise  # Re-raise для корректной отмены
    except Exception as e:
        logger.error(f"Ошибка обработки запроса: {e}")
        # ... обработка ошибок ...
```

**Критерии готовности:**
- [ ] При shutdown сервера задачи отменяются корректно
- [ ] В логах появляются сообщения об отмене
- [ ] Нет утечек памяти при отмене

---

## P2: Улучшения

### Задача 7: Добавление метрик SSE

**Файл:** `src/core/metrics/collector.py`

**Действия:**

1. Добавить метрики в collector:

```python
class MetricsCollector:
    # ... существующий код ...
    
    async def sse_session_created(self, session_id: str):
        """Записывает метрику создания SSE сессии."""
        await self.increment("sse.sessions.active")
        logger.debug(f"SSE session created: {session_id}")
    
    async def sse_session_closed(self, session_id: str):
        """Записывает метрику закрытия SSE сессии."""
        await self.decrement("sse.sessions.active")
        logger.debug(f"SSE session closed: {session_id}")
    
    async def sse_message_sent(self, session_id: str):
        """Записывает метрику отправленного сообщения."""
        await self.increment("sse.messages.sent")
    
    async def sse_message_dropped(self, session_id: str):
        """Записывает метрику потерянного сообщения."""
        await self.increment("sse.messages.dropped")
        logger.warning(f"Message dropped for session {session_id}")
```

2. Вызвать метрики в endpoint'ах:

```python
from src.core.metrics import get_metrics_collector

metrics = get_metrics_collector()

@router.get("")
async def mcp_sse_endpoint(request: Request):
    async def sse_event_stream():
        session_id = str(uuid.uuid4())
        # ...
        
        await metrics.sse_session_created(session_id)
        
        try:
            # ...
            await metrics.sse_message_sent(session_id)
        finally:
            await metrics.sse_session_closed(session_id)
```

**Критерии готовности:**
- [ ] Метрики записываются в Prometheus/логи
- [ ] Можно отследить количество активных сессий
- [ ] Можно отследить количество сообщений

---

### Задача 8: Cleanup при shutdown

**Файл:** `src/core/lifespan.py`

**Действия:**

Добавить очистку в метод `shutdown()`:

```python
async def shutdown(self, app: FastAPI) -> None:
    logger.info("Stopping application...")
    
    # ... существующий код (отключение от ES, кэш, и т.д.) ...
    
    # Очистка SSE сессий
    if hasattr(app.state, 'sse_sessions'):
        logger.info(f"Cleaning up {len(app.state.sse_sessions)} SSE sessions")
        
        for session_id, queue in list(app.state.sse_sessions.items()):
            try:
                # Отправляем уведомление о закрытии
                await queue.put({
                    "jsonrpc": "2.0",
                    "id": None,
                    "result": {"shutdown": True}
                })
            except Exception as e:
                logger.debug(f"Error sending shutdown notification: {e}")
        
        app.state.sse_sessions.clear()
        logger.info("SSE sessions cleaned up")
    
    logger.info("Application stopped")
```

**Критерии готовности:**
- [ ] При shutdown все сессии закрываются
- [ ] Клиенты получают уведомление о закрытии
- [ ] В логах появляется сообщение о очистке

---

## Проверка после исправлений

### Интеграционные тесты

**Запуск тестов:**

```bash
# Запустить сервер
python -m uvicorn src.main:app --host 0.0.0.0 --port 8002

# В другом окне запустить тесты
python tests/test_sse_connection.py
```

### Ожидаемые результаты

Все тесты должны проходить:

```
✅ Сервер доступен
✅ SSE соединение установлено
✅ Получен session_id
✅ POST запрос работает
✅ Прямой POST работает
✅ WebSocket соединение установлено
```

### Проверка метрик

```bash
# Проверить метрики (если подключен Prometheus)
curl http://localhost:8002/metrics

# Ожидаемые метрики:
# sse_sessions_active 0
# sse_messages_sent 10
# sse_messages_dropped 0
```

---

## Хронология выполнения

| Этап | Задачи | Время |
|------|--------|-------|
| **P0** | Задачи 1-3 | 2-3 часа |
| **P1** | Задачи 4-6 | 2-3 часа |
| **P2** | Задачи 7-8 | 1-2 часа |
| **Тесты** | Интеграционные тесты | 1 час |
| **Итого** | | **6-9 часов** |

---

## Ответственные

- [ ] Задача 1: Удаление дублирования
- [ ] Задача 2: Инициализация sse_sessions
- [ ] Задача 3: Исправление router.app
- [ ] Задача 4: Ограничения очереди
- [ ] Задача 5: Таймаут сессии
- [ ] Задача 6: CancelledError
- [ ] Задача 7: Метрики
- [ ] Задача 8: Cleanup

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Поломка существующих клиентов | Средняя | Высокое | Тестирование на staging |
| Утечки памяти | Низкая | Среднее | Code review, тесты |
| Проблемы с производительностью | Низкая | Среднее | Load тестирование |

---

## Communication Plan

После завершения исправлений:

1. Обновить `CHANGELOG.md`
2. Обновить `docs/SSE_ANALYSIS.md`
3. Создать PR с описанием изменений
4. Уведомить пользователей об обновлениях

---

## Приложения

### A. Список файлов для изменения

1. `src/main.py` - удаление дублирования
2. `src/routes/mcp_routes.py` - исправление router.app, таймауты, ограничения
3. `src/core/lifespan.py` - инициализация, cleanup
4. `src/core/constants.py` - новые константы
5. `src/core/metrics/collector.py` - новые метрики

### B. Тестовые сценарии

1. **SSE подключение:** `GET /mcp` → получение session_id
2. **POST запрос:** `POST /mcp?session_id=xxx` → ответ в SSE
3. **Прямой POST:** `POST /mcp` → прямой ответ
4. **WebSocket:** Подключение → обмен сообщениями
5. **Таймаут:** Подключение → ожидание 1 часа → закрытие
6. **Переполнение:** 100+ сообщений → ошибка 503
7. **Shutdown:** Запуск → shutdown → очистка сессий

### C. Мониторинг

После деплоя отслеживать:

- Количество активных SSE сессий
- Количество ошибок 503 (переполнение очереди)
- Среднее время жизни сессии
- Потребление памяти сервером
