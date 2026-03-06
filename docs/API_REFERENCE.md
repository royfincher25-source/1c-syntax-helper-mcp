# API Reference - MCP сервер синтаксис-помощника 1С

## Базовая информация

- **Базовый URL**: `http://localhost:8002`
- **Протокол**: HTTP/HTTPS
- **Формат**: JSON
- **Аутентификация**: Не требуется (локальный сервис)

## Health Check Endpoints

### GET /health

Проверка состояния системы.

**Ответ:**
```json
{
  "status": "healthy",
  "elasticsearch": true,
  "index_exists": true,
  "documents_count": 1234
}
```

### GET /index/status

Статус индексации документации.

**Ответ:**
```json
{
  "elasticsearch_connected": true,
  "index_exists": true,
  "documents_count": 1234,
  "index_name": "1c_docs_index"
}
```

## Управление индексацией

### POST /index/rebuild

Переиндексация документации из .hbk файла.

**Ответ при успехе:**
```json
{
  "status": "success",
  "message": "Переиндексация завершена успешно",
  "file": "data/hbk/shcntx_ru.hbk",
  "documents_count": 1234
}
```

**Ответ при ошибке:**
```json
{
  "detail": "Файлы .hbk не найдены в data/hbk"
}
```

## MCP Protocol Endpoints

### GET /mcp/tools

Получение списка доступных MCP инструментов.

**Ответ:**
```json
{
  "tools": [
    {
      "name": "search_1c_syntax",
      "description": "Поиск по синтаксису 1С: функции, процедуры, методы объектов",
      "parameters": [
        {
          "name": "query",
          "type": "string",
          "description": "Поисковый запрос",
          "required": true
        },
        {
          "name": "limit",
          "type": "number", 
          "description": "Максимальное количество результатов",
          "required": false
        }
      ]
    }
  ]
}
```

### POST /mcp

Основной MCP endpoint для выполнения команд.

**Структура запроса:**
```json
{
  "tool": "имя_инструмента",
  "arguments": {
    "параметр1": "значение1",
    "параметр2": "значение2"
  }
}
```

## MCP Инструменты

### 1. search_1c_syntax

Поиск по синтаксису и документации 1С.

**Запрос:**
```json
{
  "tool": "search_1c_syntax",
  "arguments": {
    "query": "СтрДлина",
    "limit": 10
  }
}
```

**Ответ:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "**Результаты поиска по запросу:** `СтрДлина`\n**Найдено:** 1 из 1\n**Время поиска:** 45ms\n"
    },
    {
      "type": "text",
      "text": "\n---\n🔧 1. **СтрДлина**\n**Синтаксис:** `СтрДлина(Строка)`\n**Описание:** Возвращает количество символов в строке\n"
    }
  ]
}
```

### 2. get_1c_function_details

Получение подробной информации о функции.

**Запрос:**
```json
{
  "tool": "get_1c_function_details", 
  "arguments": {
    "function_name": "СтрДлина"
  }
}
```

**Ответ:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "# 🔧 Функция: СтрДлина\n\n**Описание:** Возвращает количество символов в строке\n\n**Синтаксис (рус):** `СтрДлина(Строка)`\n\n## Параметры:\n\n- **Строка** (Строка) *(обязательный)*\n  Строка, длину которой необходимо определить\n\n**Возвращает:** Число\n\n## Примеры использования:\n\n```\nДлина = СтрДлина(\"Пример\"); // Результат: 6\n```\n"
    }
  ]
}
```

### 3. get_1c_object_info

Получение информации об объекте 1С и его методах.

**Запрос:**
```json
{
  "tool": "get_1c_object_info",
  "arguments": {
    "object_name": "ТаблицаЗначений"
  }
}
```

**Ответ:**
```json
{
  "content": [
    {
      "type": "text", 
      "text": "# 📦 Объект: ТаблицаЗначений\n\n**Всего элементов:** 15\n\n## 🔨 Методы (10):\n\n- **Добавить** - `Добавить()`\n  Добавляет новую строку в таблицу значений\n- **Найти** - `Найти(ЗначениеПоиска, КолонкиПоиска)`\n  Находит строку в таблице по заданному критерию\n\n## 📋 Свойства (3):\n\n- **Колонки** (КоллекцияКолонокТаблицыЗначений) - Коллекция колонок таблицы\n- **Количество** (Число) - Количество строк в таблице\n\n## ⚡ События (2):\n\n- **ПриДобавленииСтроки** - Событие при добавлении новой строки\n"
    }
  ]
}
```

## Коды ошибок

### HTTP Status Codes

- **200 OK** - Успешный запрос
- **400 Bad Request** - Неверный формат запроса
- **404 Not Found** - Функция/объект не найден  
- **500 Internal Server Error** - Внутренняя ошибка сервера
- **503 Service Unavailable** - Elasticsearch недоступен

### MCP Error Response

```json
{
  "content": [],
  "error": "Описание ошибки"
}
```

### Примеры ошибок

```json
{
  "content": [],
  "error": "Elasticsearch недоступен"
}
```

```json
{
  "content": [],
  "error": "Функция 'НесуществующаяФункция' не найдена"
}
```

## Параметры поиска

### Типы поиска

- **auto** - Автоматическое определение типа поиска
- **exact** - Точное совпадение
- **fuzzy** - Нечеткий поиск с допуском опечаток
- **semantic** - Семантический поиск по описанию

### Поддерживаемые запросы

#### Точные названия функций
```
СтрДлина
ВРег
НРег
ЗначениеЗаполнено
```

#### Методы объектов
```
ТаблицаЗначений.Добавить
Запрос.Выполнить
Соединение.ПодготовитьЗапрос
```

#### Поиск по описанию
```
работа со строками
добавление строки в таблицу
выполнение запроса к базе данных
```

#### Поиск по типу
```
глобальные функции
методы таблицы значений
события формы
```

## Ограничения

### Производительность
- **Время поиска**: < 500ms
- **Максимум результатов**: 50 на запрос
- **Timeout запроса**: 30 секунд

### Размеры данных
- **Максимальная длина запроса**: 1000 символов
- **Максимальный размер ответа**: 10 МБ

### Конкурентность
- **Максимальные одновременные запросы**: 8
- **Rate limiting**: Не применяется (локальный сервис)

## Примеры использования

### cURL

```bash
# Поиск функции
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "search_1c_syntax",
    "arguments": {
      "query": "СтрДлина",
      "limit": 5
    }
  }'

# Детали функции
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_1c_function_details",
    "arguments": {
      "function_name": "СтрДлина"
    }
  }'

# Информация об объекте
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "get_1c_object_info", 
    "arguments": {
      "object_name": "ТаблицаЗначений"
    }
  }'
```

### Python

```python
import requests

# Поиск по синтаксису
response = requests.post('http://localhost:8000/mcp', json={
    'tool': 'search_1c_syntax',
    'arguments': {
        'query': 'СтрДлина',
        'limit': 10
    }
})

data = response.json()
print(data['content'][0]['text'])
```

### JavaScript

```javascript
// Поиск функции
const response = await fetch('http://localhost:8000/mcp', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    tool: 'search_1c_syntax',
    arguments: {
      query: 'СтрДлина',
      limit: 5
    }
  })
});

const data = await response.json();
console.log(data.content[0].text);
```
