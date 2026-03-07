# Рефакторинг форматирования и констант

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Устранить дублирование SearchFormatter и SSE констант

**Architecture:** Объединить два класса SearchFormatter в один, вынести константы в одно место

**Tech Stack:** Python, FastAPI, MCP

---

## Task 1: Расширить SearchFormatter

**Files:**
- Modify: `src/search/formatter.py`

**Step 1: Прочитать существующий SearchFormatter**

```bash
read src/search/formatter.py
```

**Step 2: Добавить MCP-методы в конец файла**

Добавить методы:
```python
    @staticmethod
    def format_search_header(count: int, query: str) -> Dict[str, str]:
        """Форматирует заголовок результатов поиска."""
        return {
            "type": "text",
            "text": f"📋 **Найдено:** {count} элементов по запросу \"{query}\"\n"
        }
    
    @staticmethod
    def format_search_result(result: Dict[str, Any], index: int) -> Dict[str, str]:
        """Форматирует отдельный результат поиска."""
        name = result.get("name", "")
        obj = result.get("object", "")
        description = result.get("description", "")
        
        text = f"{index}. **{name}**"
        if obj:
            text += f" ({obj} → Метод)" if obj != "Global context" else " (Глобальная функция)"
        
        if description:
            desc = description[:100] + "..." if len(description) > 100 else description
            text += f"\n   └ {desc}"
        
        return {"type": "text", "text": text + "\n"}
    
    @staticmethod
    def format_context_search(
        search_results: List[Dict[str, Any]], 
        query: str, 
        context: str
    ) -> str:
        """Форматирует результаты контекстного поиска."""
        if context == "object":
            objects = {}
            for result in search_results:
                obj = result.get("object", "Неизвестно")
                if obj not in objects:
                    objects[obj] = []
                objects[obj].append(result)
            
            text = f"🎯 **ПОИСК В КОНТЕКСТЕ:** {context}\n\n"
            text += f"Найдено {len(search_results)} элементов по запросу \"{query}\"\n\n"
            
            for obj, items in list(objects.items())[:5]:
                text += f"📦 **{obj}:**\n"
                for item in items[:3]:
                    name = item.get("name", "")
                    syntax = item.get("syntax_ru", "")
                    desc = item.get("description", "")
                    
                    text += f"   • {name}"
                    if syntax:
                        text += f" - `{syntax}`"
                    if desc:
                        short_desc = desc[:50] + "..." if len(desc) > 50 else desc
                        text += f"\n     {short_desc}"
                    text += "\n"
                text += "\n"
        else:
            text = f"🔍 **ПОИСК В КОНТЕКСТЕ:** {context}\n\n"
            text += f"Найдено {len(search_results)} элементов\n\n"
            
            for i, result in enumerate(search_results[:8], 1):
                name = result.get("name", "")
                syntax = result.get("syntax_ru", "")
                text += f"{i}. **{name}**"
                if syntax:
                    text += f" - `{syntax}`"
                text += "\n"
        
        return text

    @staticmethod
    def format_syntax_info(result: Dict[str, Any]) -> str:
        """Форматирует техническую справку."""
        name = result.get("name", "")
        syntax_ru = result.get("syntax_ru", "")
        description = result.get("description", "")
        
        text = f"### {name}\n\n"
        if syntax_ru:
            text += f"**Синтаксис:** `{syntax_ru}`\n\n"
        if description:
            text += f"**Описание:** {description}\n"
        
        return text

    @staticmethod
    def format_quick_reference(result: Dict[str, Any]) -> str:
        """Форматирует краткую справку."""
        name = result.get("name", "")
        syntax_ru = result.get("syntax_ru", "")
        
        text = f"**{name}**"
        if syntax_ru:
            text += f": `{syntax_ru}`"
        
        return text

    @staticmethod
    def format_object_members_list(
        object_name: str, 
        member_type: str, 
        methods: list, 
        properties: list, 
        events: list, 
        total: int
    ) -> str:
        """Форматирует список элементов объекта."""
        text = f"📦 **{object_name}** (всего: {total})\n\n"
        
        if methods:
            text += "**Методы:**\n"
            for m in methods[:10]:
                text += f"  • {m.get('name', '')}\n"
            if len(methods) > 10:
                text += f"  ... и ещё {len(methods) - 10}\n"
            text += "\n"
        
        if properties:
            text += "**Свойства:**\n"
            for p in properties[:5]:
                text += f"  • {p.get('name', '')}\n"
            if len(properties) > 5:
                text += f"  ... и ещё {len(properties) - 5}\n"
            text += "\n"
        
        if events:
            text += "**События:**\n"
            for e in events[:5]:
                text += f"  • {e.get('name', '')}\n"
        
        return text
```

**Step 3: Commit**

```bash
git add src/search/formatter.py
git commit -m "refactor: расширить SearchFormatter MCP-методами"
```

---

## Task 2: Обновить mcp_formatter.py

**Files:**
- Modify: `src/handlers/mcp_formatter.py`

**Step 1: Прочитать файл**

```bash
read src/handlers/mcp_formatter.py
```

**Step 2: Заменить импорт**

Было:
```python
from src.handlers.formatters import SearchFormatter, SyntaxFormatter, ObjectFormatter
```

Стало:
```python
from src.search.formatter import SearchFormatter
```

**Step 3: Обновить класс**

```python
class MCPResponseFormatter:
    """Класс для стандартизированного форматирования ответов MCP."""

    def __init__(self):
        self.search = SearchFormatter()

    @staticmethod
    def create_error_response(message: str, details: str = None) -> Dict[str, Any]:
        error_text = message
        if details:
            error_text += f": {details}"
        return {"content": [], "error": error_text}

    @staticmethod
    def create_not_found_response(query: str, context: str = "") -> Dict[str, Any]:
        if context:
            text = f"По запросу '{query}' в контексте '{context}' ничего не найдено."
        else:
            text = f"По запросу '{query}' ничего не найдено."
        return {"content": [{"type": "text", "text": text}]}

    @staticmethod
    def create_success_response(content: List[Dict[str, str]]) -> Dict[str, Any]:
        return {"content": content}
    
    def format_search_header(self, count: int, query: str) -> Dict[str, str]:
        return self.search.format_search_header(count, query)
    
    def format_search_result(self, result: Dict[str, Any], index: int) -> Dict[str, str]:
        return self.search.format_search_result(result, index)
    
    def format_syntax_info(self, result: Dict[str, Any]) -> str:
        return self.search.format_syntax_info(result)
    
    def format_quick_reference(self, result: Dict[str, Any]) -> str:
        return self.search.format_quick_reference(result)
    
    def format_context_search(self, search_results: List[Dict[str, Any]], query: str, context: str) -> str:
        return self.search.format_context_search(search_results, query, context)
    
    def format_object_members_list(self, object_name: str, member_type: str, methods: list, properties: list, events: list, total: int) -> str:
        return self.search.format_object_members_list(object_name, member_type, methods, properties, events, total)
```

**Step 4: Commit**

```bash
git add src/handlers/mcp_formatter.py
git commit -m "refactor: использовать единый SearchFormatter"
```

---

## Task 3: Удалить дублирующиеся файлы

**Files:**
- Delete: `src/handlers/formatters/search_formatter.py`
- Delete: `src/handlers/formatters/syntax_formatter.py`
- Delete: `src/handlers/formatters/object_formatter.py`
- Delete: `src/handlers/formatters/__init__.py`

**Step 1: Удалить файлы**

```bash
rm src/handlers/formatters/search_formatter.py
rm src/handlers/formatters/syntax_formatter.py
rm src/handlers/formatters/object_formatter.py
rm src/handlers/formatters/__init__.py
```

**Step 2: Удалить пустую директорию**

```bash
rmdir src/handlers/formatters
```

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: удалить дублирующиеся formatters"
```

---

## Task 4: Объединить SSE константы

**Files:**
- Modify: `src/routes/sse_router.py`
- Modify: `src/core/constants.py`

**Step 1: Прочитать sse_router.py**

```bash
read src/routes/sse_router.py
```

**Step 2: Добавить импорт констант**

Добавить в начало файла:
```python
from src.core.constants import (
    SSE_QUEUE_MAX_SIZE,
    SSE_PING_INTERVAL_SECONDS,
    SSE_SESSION_TIMEOUT_SECONDS
)
```

**Step 3: Удалить локальные константы**

Удалить строки:
```python
SSE_QUEUE_MAX_SIZE = 100
SSE_PING_INTERVAL_SECONDS = 30
SSE_SESSION_TIMEOUT_SECONDS = 3600
```

**Step 4: Commit**

```bash
git add src/routes/sse_router.py
git commit -m "refactor: вынести SSE константы в constants.py"
```

---

## Task 5: Запустить тесты

**Step 1: Запустить тесты**

```bash
pytest tests/ -v --tb=short
```

**Step 2: Если есть ошибки — исправить**

**Step 3: Commit**

```bash
git add -A
git commit -m "test: запустить тесты после рефакторинга"
```

---

## Task 6: Проверить работу вручную

**Step 1: Запустить сервер**

```bash
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8002
```

**Step 2: Проверить MCP endpoint**

```bash
curl -X POST http://localhost:8002/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

**Step 3: Остановить сервер**

---

## Plan Complete

**Проверить что:**
1. Все тесты проходят
2. MCP-ответы корректно форматируются
3. Константы используются из одного места
