# Настройка подключения Qwen Code к 1c-syntax-helper MCP

## Проблема

При запуске Qwen Code с конфигурацией `1c-syntax-helper` сервер "зависал" и не подключался.

## Причина

**Конфигурация MCP сервера отсутствовала в файле `%USERPROFILE%\.qwen\settings.json`**

**Важное уточнение:** Qwen Code использует **JSON-RPC поверх HTTP POST**, а не SSE (Server-Sent Events). Поэтому в конфигурации необходимо указывать `/mcp` endpoint, а не `/sse`.

## Решение

### Шаг 1: Проверка работы сервера

Выполните команды вручную:

```bash
# Проверка Docker контейнеров
docker-compose ps

# Проверка health endpoint
curl http://localhost:8002/health

# Проверка MCP endpoint (JSON-RPC)
curl -X POST "http://localhost:8002/mcp" ^
  -H "Content-Type: application/json" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}"
```

**Ожидаемый результат:**
- `docker-compose ps` показывает контейнеры `es-1c-helper` и `mcp-1c-helper` в статусе "Up"
- `curl http://localhost:8002/health` возвращает `{"status":"healthy",...}`
- `curl -X POST "http://localhost:8002/mcp"...` возвращает JSON-RPC ответ с `protocolVersion`

### Шаг 2: Добавление конфигурации в Qwen Code

1. Откройте файл конфигурации Qwen:
   - Нажмите `Win+R`
   - Введите: `%USERPROFILE%\.qwen\settings.json`
   - Нажмите Enter

2. Добавьте сервер `1c-syntax-helper` в секцию `mcpServers`:

**Критически важно:** Используйте `/mcp` endpoint (JSON-RPC), а не `/sse` (SSE)!

```json
{
  "$version": 3,
  "mcpServers": {
    "1c-syntax-helper": {
      "url": "http://localhost:8002/mcp",
      "type": "remote",
      "enabled": true
    }
  }
}
```

**Полный пример с другими серверами:**

```json
{
  "$version": 3,
  "ide": {
    "hasSeenNudge": true
  },
  "security": {
    "auth": {
      "selectedType": "qwen-oauth"
    }
  },
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
  },
  "tools": {
    "approvalMode": "default"
  },
  "model": {
    "name": "coder-model"
  }
}
```

3. **Сохраните файл**

### Шаг 3: Перезапуск Qwen Code

1. **Полностью закройте Qwen Code**
   - Файл → Выход
   - Или `Alt+F4`

2. **Запустите Qwen Code снова**

### Шаг 4: Тестирование подключения

Задайте Qwen Code вопрос для проверки:

```
Найди информацию о функции СтрДлина
```

или

```
Как использовать Массив в 1С?
```

**Ожидаемый результат:** Qwen Code отправляет запрос к MCP серверу и получает ответ.

---

## Диагностика проблем

### Проблема: Qwen Code "зависает" при запуске

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
   - Проверьте правила брандмауэра Windows
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
│  Qwen Code  │      │  MCP Server (port 8002)         │
│  MCP Client │      │                                 │
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

1. **POST /mcp** - Qwen отправляет JSON-RPC запрос
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

**Qwen Code использует упрощённый подход:**
- Только HTTP POST запросы к `/mcp`
- Каждый запрос - отдельный HTTP вызов
- Нет необходимости в SSE stream

**Если вы видите `/sse` в документации MCP:**
- Это для других MCP клиентов (Claude Desktop, VS Code MCP Extension)
- Qwen Code работает через прямой JSON-RPC поверх HTTP

---

## Дополнительные ресурсы

- [MCP Protocol Specification](https://modelcontextprotocol.io/specification/2025-06-18/index)
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Руководство по развертыванию
- [README.md](README.md) - Основная документация проекта

---

**Дата обновления:** 6 марта 2026 г.
**Версия документа:** 1.1 (исправлен URL с `/sse` на `/mcp`)
