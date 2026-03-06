# Настройка MCP клиентов для работы с 1c-syntax-helper

## Проблема

MCP клиенты могут "зависать" при подключении к серверу, если указан неверный endpoint.

## Причина

**Некоторые MCP клиенты используют JSON-RPC поверх HTTP POST, а не SSE (Server-Sent Events).**

В конфигурации необходимо указывать `/mcp` endpoint для JSON-RPC клиентов.

## Решение

### Шаг 1: Проверка работы сервера

Выполните команды для проверки работоспособности сервера:

```bash
# Проверка Docker контейнеров
docker-compose ps

# Проверка health endpoint
curl http://localhost:8002/health

# Проверка MCP endpoint (JSON-RPC)
curl -X POST "http://localhost:8002/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

**Ожидаемый результат:**
- `docker-compose ps` показывает контейнеры в статусе "Up"
- `curl http://localhost:8002/health` возвращает `{"status":"healthy",...}`
- `curl -X POST "http://localhost:8002/mcp"...` возвращает JSON-RPC ответ с `protocolVersion`

### Шаг 2: Добавление конфигурации в MCP клиент

1. Откройте файл конфигурации вашего MCP клиента

2. Добавьте сервер `1c-syntax-helper` в секцию `mcpServers`:

**Критически важно:** Используйте `/mcp` endpoint (JSON-RPC), а не `/sse` (SSE)!

```json
{
  "mcpServers": {
    "1c-syntax-helper": {
      "url": "http://localhost:8002/mcp",
      "type": "remote",
      "enabled": true
    }
  }
}
```

**Полный пример с несколькими серверами:**

```json
{
  "mcpServers": {
    "1c_bk": {
      "url": "http://localhost:8012/mcp",
      "headers": {
        "x-collection-name": "1c_bk"
      },
      "type": "remote",
      "enabled": true
    },
    "1c-standarti": {
      "url": "http://localhost:8012/mcp",
      "headers": {
        "x-collection-name": "1c_ssmr"
      },
      "type": "remote",
      "enabled": true
    },
    "1c-syntax-helper": {
      "url": "http://localhost:8002/mcp",
      "type": "remote",
      "enabled": true
    }
  }
}
```

3. **Сохраните файл**

### Шаг 3: Перезапуск клиента

1. **Полностью закройте клиент** (IDE, редактор кода, и т.д.)

2. **Запустите клиент снова**

### Шаг 4: Тестирование подключения

Отправьте тестовый запрос через MCP клиент:

```
Найди информацию о функции СтрДлина
```

или

```
Как использовать Массив в 1С?
```

**Ожидаемый результат:** Клиент отправляет запрос к MCP серверу и получает ответ.

---

## Диагностика проблем

### Проблема: Клиент "зависает" при запуске

**Возможные причины:**

1. **Сервер не запущен**
   ```bash
   docker-compose ps
   ```

   Решение:
   ```bash
   docker-compose up -d
   ```

2. **Неверный URL в конфигурации**
   - Проверьте, что указан URL `http://localhost:8002/mcp` (НЕ `/sse`!)
   - Проверьте, что docker-compose.yml мапит порт `8002:8000`

3. **Брандмауэр блокирует подключение**
   - Проверьте правила брандмауэра
   - Разрешите подключение к порту 8002

4. **Конфликт с другим сервером**
   ```bash
   netstat -ano | findstr :8002
   ```

   Решение: Остановите конфликтующее приложение или измените порт

### Проблема: MCP server не отвечает

**Проверьте логи:**

```bash
docker-compose logs mcp-server
```

**Ищите ошибки:**
- `Connection refused` - Elasticsearch недоступен
- `Timeout` - Проблемы с сетью
- `Index not found` - Требуется индексация

**Переиндексация:**

```bash
curl -X POST http://localhost:8002/index/rebuild
```

---

## Архитектура подключения

```
┌─────────────┐      ┌─────────────────────────────────┐
│  MCP Client │      │  MCP Server (port 8002)         │
│             │      │                                 │
└──────┬──────┘      │  ┌───────────┐                  │
       │             │  │ /mcp      │                  │
       │ POST        │  │ (JSON-RPC)│                  │
       │ JSON-RPC    │  └─────┬─────┘                  │
       ├─────────────┼────────┘                        │
       │             │                                 │
       │ Response    │                                 │
       │◄────────────┼─────────────────────────────────┤
       │             │                                 │
└──────┴──────┘      └─────────────────────────────────┘
```

**Протокол работы:**

1. **POST /mcp** - Клиент отправляет JSON-RPC запрос
2. **Обработка** - Сервер обрабатывает запрос
3. **JSON Response** - Сервер возвращает ответ

**Пример JSON-RPC запроса:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

**Пример ответа:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {"listChanged": false}
    },
    "serverInfo": {
      "name": "1c-syntax-helper-mcp",
      "version": "1.0.0"
    }
  }
}
```

---

## Почему НЕ `/sse`?

**SSE (Server-Sent Events)** используется в MCP протоколе для:
- Двусторонней связи через один endpoint
- Push-уведомлений от сервера к клиенту
- Поддержки старых MCP клиентов

**Большинство современных MCP клиентов используют упрощённый подход:**
- Только HTTP POST запросы к `/mcp`
- Каждый запрос - отдельный HTTP вызов
- Нет необходимости в SSE stream

**Если вы видите `/sse` в документации MCP:**
- Это для клиентов, поддерживающих SSE (Claude Desktop, некоторые VS Code расширения)
- Для JSON-RPC клиентов используйте `/mcp`

---

## Поддерживаемые клиенты

| Клиент | Рекомендуемый endpoint | Примечание |
|--------|----------------------|------------|
| Claude Desktop | `/sse` | Требует SSE для двусторонней связи |
| VS Code MCP Extension | `/mcp` | Поддерживает JSON-RPC поверх HTTP |
| Кастомные MCP клиенты | `/mcp` | JSON-RPC поверх HTTP POST |
| CLI инструменты | `/mcp` | Прямые HTTP запросы |

---

## Дополнительные ресурсы

- [MCP Protocol Specification](https://modelcontextprotocol.io/specification/2025-06-18/index)
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Руководство по развертыванию
- [README.md](README.md) - Основная документация проекта

---

**Дата обновления:** 6 марта 2026 г.
**Версия документа:** 2.0 (универсальная документация для всех MCP клиентов)
