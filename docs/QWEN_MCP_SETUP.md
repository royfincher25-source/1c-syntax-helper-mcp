# Настройка подключения Qwen Code к 1c-syntax-helper MCP

## Проблема

При запуске Qwen Code с конфигурацией `1c-syntax-helper` сервер "зависал" и не подключался.

## Причина

**Конфигурация MCP сервера отсутствовала в файле `%USERPROFILE%\.qwen\settings.json`**

## Решение

### Шаг 1: Проверка работы сервера

Запустите скрипт проверки:

```bash
.\check_mcp_connection.bat
```

Или выполните команды вручную:

```bash
# Проверка Docker контейнеров
docker-compose ps

# Проверка health endpoint
curl http://localhost:8002/health

# Проверка SSE endpoint
curl http://localhost:8002/sse --max-time 3

# Проверка MCP initialize
curl -X POST "http://localhost:8002/sse" ^
  -H "Content-Type: application/json" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}"
```

**Ожидаемый результат:** Все команды возвращают успешные ответы.

### Шаг 2: Добавление конфигурации в Qwen Code

1. Откройте файл конфигурации Qwen:
   - Нажмите `Win+R`
   - Введите: `%USERPROFILE%\.qwen\settings.json`
   - Нажмите Enter

2. Добавьте сервер `1c-syntax-helper` в секцию `mcpServers`:

```json
{
  "$version": 3,
  "mcpServers": {
    "1c-syntax-helper": {
      "url": "http://localhost:8002/sse",
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
      "url": "http://localhost:8012/sse",
      "headers": {
        "x-collection-name": "1c_bk"
      },
      "type": "remote",
      "enabled": true
    },
    "1c-standarti": {
      "url": "http://localhost:8012/sse",
      "headers": {
        "x-collection-name": "1c_ssmr"
      },
      "type": "remote",
      "enabled": true
    },
    "1c-syntax-helper": {
      "url": "http://localhost:8002/sse",
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

### Проблема: Qwen Code всё ещё "зависает"

**Возможные причины:**

1. **Сервер не запущен**
   ```bash
   docker-compose ps
   ```
   
   Решение:
   ```bash
   docker-compose up -d
   ```

2. **Неверный порт в конфигурации**
   - Проверьте, что в settings.json указан порт `8002`
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

### Проблема: SSE endpoint не работает

**Проверка SSE:**

```bash
# Тест GET запроса (должен держать соединение)
curl -N "http://localhost:8002/sse" --max-time 5

# Тест POST запроса
curl -X POST "http://localhost:8002/sse" ^
  -H "Content-Type: application/json" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}"
```

**Ожидаемый результат:**
- GET: curl таймаутит через 5 секунд (соединение держится)
- POST: Возвращает JSON-RPC ответ с `protocolVersion`

---

## Архитектура подключения

```
┌─────────────┐      ┌─────────────────────────────────┐
│  Qwen Code  │      │  MCP Server (port 8002)         │
│  MCP Client │      │                                 │
└──────┬──────┘      │  ┌───────────┐                  │
       │             │  │ /sse      │                  │
       │ 1. GET /sse │  │ (SSE)     │                  │
       ├─────────────┼──►           │                  │
       │             │  └─────┬─────┘                  │
       │ 2. endpoint │        │                        │
       │    /sse?sid │        │                        │
       │◄────────────┼────────┘                        │
       │             │                                 │
       │ 3. POST     │                                 │
       │    {init}   │                                 │
       ├─────────────┼────────────────────────────────►│
       │             │                                 │
       │ 4. queued   │                                 │
       │◄────────────┼─────────────────────────────────┤
       │             │                                 │
       │ 5. SSE msg  │                                 │
       │◄────────────┼─────────────────────────────────┤
       │             │                                 │
└──────┴──────┘      └─────────────────────────────────┘
```

**Этапы подключения:**

1. **GET /sse** - Qwen подключается к SSE endpoint
2. **endpoint event** - Сервер отправляет URL для POST запросов с session_id
3. **POST /sse?session_id=xxx** - Qwen отправляет JSON-RPC запросы
4. **queued response** - Сервер подтверждает получение
5. **SSE message event** - Сервер отправляет ответ через SSE stream

---

## Дополнительные ресурсы

- [MCP Protocol Specification](https://modelcontextprotocol.io/specification/2025-06-18/index)
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Руководство по развертыванию
- [README.md](README.md) - Основная документация проекта

---

**Дата обновления:** 6 марта 2026 г.
**Версия документа:** 1.0
