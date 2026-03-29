"""Обработчики MCP запросов."""

from src.models.mcp_models import (
    MCPResponse, Find1CHelpRequest, GetSyntaxInfoRequest, GetQuickReferenceRequest,
    SearchByContextRequest, ListObjectMembersRequest,
    GetExamplesRequest, GetMethodsRequest, GetPropertiesRequest, GetEventsRequest
)
from src.search.search_service import search_service
from src.handlers.mcp_formatter import mcp_formatter
from src.core.logging import get_logger

logger = get_logger(__name__)


def _log_mcp_request(tool_name: str, **context):
    """Логирует MCP запрос с контекстом."""
    logger.debug(f"MCP запрос: {tool_name}", extra={"extra_data": {"tool": tool_name, **context}})


def _log_mcp_success(tool_name: str, count: int = None, **context):
    """Логирует успешный MCP ответ."""
    extra = {"tool": tool_name, "status": "success", **context}
    if count is not None:
        extra["results_count"] = count
    logger.debug(f"MCP успех: {tool_name}", extra={"extra_data": extra})


def _log_mcp_error(tool_name: str, error: str, **context):
    """Логирует ошибку MCP запроса."""
    logger.error(f"MCP ошибка: {tool_name} - {error}", 
                extra={"extra_data": {"tool": tool_name, "status": "error", "error": error, **context}})


def _clean_string(value):
    """Clean any value to ensure valid UTF-8 encoding."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    if isinstance(value, str):
        try:
            return value.encode('utf-8', errors='replace').decode('utf-8')
        except Exception:
            return str(value)
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


async def handle_find_1c_help(request: Find1CHelpRequest) -> dict:
    """Универсальный поиск справки по любому элементу 1С."""
    _log_mcp_request("find_1c_help", query=request.query, limit=request.limit)

    try:
        results = await search_service.find_help_by_query(request.query, request.limit)

        if results.get("error"):
            _log_mcp_error("find_1c_help", results["error"])
            return {"content": [], "error": results["error"]}

        search_results = results.get("results", [])

        if not search_results:
            _log_mcp_success("find_1c_help", count=0)
            return {"content": [{"type": "text", "text": f"Ничего не найдено по запросу: {request.query}"}], "error": None}

        content = [mcp_formatter.format_search_header(len(search_results), request.query)]

        # Результаты
        for i, result in enumerate(search_results, 1):
            formatted = mcp_formatter.format_search_result(result, i)
            # Clean all string values
            if "text" in formatted:
                formatted["text"] = _clean_string(formatted["text"])
            content.append(formatted)

        _log_mcp_success("find_1c_help", count=len(search_results))
        return {"content": content, "error": None}

    except Exception as e:
        _log_mcp_error("find_1c_help", str(e))
        return {"content": [], "error": str(e)}


async def handle_get_syntax_info(request: GetSyntaxInfoRequest) -> dict:
    """Получить полную техническую информацию об элементе."""
    _log_mcp_request("get_syntax_info", element_name=request.element_name, 
                    object_name=request.object_name, include_examples=request.include_examples)
    
    try:
        result = await search_service.get_detailed_syntax_info(
            request.element_name, 
            request.object_name, 
            request.include_examples
        )
        
        if not result:
            element_context = f" объекта '{request.object_name}'" if request.object_name else ""
            _log_mcp_success("get_syntax_info", count=0)
            return {"content": [{"type": "text", "text": f"Элемент '{request.element_name}'{element_context} не найден"}]}

        # Форматируем детальную информацию
        text = mcp_formatter.format_syntax_info(result)

        # Добавляем примеры если нужно
        if request.include_examples and result.get('examples'):
            examples = result['examples']
            if isinstance(examples, list) and examples:
                text += "💡 **Примеры:**\n"
                for example in examples[:2]:  # Максимум 2 примера
                    text += f"   ```\n   {example}\n   ```\n"

        _log_mcp_success("get_syntax_info", count=1, has_examples=bool(result.get('examples')))
        return {"content": [{"type": "text", "text": text}]}
        
    except Exception as e:
        _log_mcp_error("get_syntax_info", str(e))
        return {"content": [], "error": str(e)}


async def handle_get_quick_reference(request: GetQuickReferenceRequest) -> dict:
    """Получить краткую справку."""
    _log_mcp_request("get_quick_reference", element_name=request.element_name, object_name=request.object_name)

    try:
        result = await search_service.get_detailed_syntax_info(
            request.element_name,
            request.object_name,
            include_examples=False
        )

        if not result:
            _log_mcp_success("get_quick_reference", count=0)
            return {"content": [{"type": "text", "text": f"⚡ Элемент '{request.element_name}' не найден"}]}

        text = mcp_formatter.format_quick_reference(result)

        _log_mcp_success("get_quick_reference", count=1)
        return {"content": [{"type": "text", "text": text}]}

    except Exception as e:
        _log_mcp_error("get_quick_reference", str(e))
        return {"content": [], "error": str(e)}


async def handle_search_by_context(request: SearchByContextRequest) -> dict:
    """Поиск с фильтром по контексту."""
    _log_mcp_request("search_by_context", query=request.query, context=request.context,
                    object_name=request.object_name, limit=request.limit)

    try:
        results = await search_service.search_with_context_filter(
            request.query,
            request.context,
            request.object_name,
            request.limit
        )

        if results.get("error"):
            _log_mcp_error("search_by_context", results["error"])
            return {"content": [], "error": f"Ошибка поиска: {results['error']}"}

        search_results = results.get("results", [])

        if not search_results:
            context_name = {"global": "глобальном", "object": "объектном", "all": "любом"}
            context_text = context_name.get(request.context, request.context)
            _log_mcp_success("search_by_context", count=0, context=request.context)
            return {"content": [{"type": "text", "text": f"По запросу '{request.query}' в {context_text} контексте ничего не найдено"}]}

        text = mcp_formatter.format_context_search(search_results, request.query, request.context)

        _log_mcp_success("search_by_context", count=len(search_results), context=request.context)
        return {"content": [{"type": "text", "text": text}]}

    except Exception as e:
        _log_mcp_error("search_by_context", str(e))
        return {"content": [], "error": str(e)}


async def handle_list_object_members(request: ListObjectMembersRequest) -> dict:
    """Получить список элементов объекта."""
    _log_mcp_request("list_object_members", object_name=request.object_name, member_type=request.member_type, limit=request.limit)
    try:
        result = await search_service.get_object_members_list(
            request.object_name,
            request.member_type,
            request.limit
        )

        if result.get("error"):
            _log_mcp_error("list_object_members", result["error"])
            return {"content": [], "error": f"Ошибка: {result['error']}"}

        methods = result.get("methods", [])
        properties = result.get("properties", [])
        events = result.get("events", [])
        total = result.get("total", 0)

        if total == 0:
            _log_mcp_success("list_object_members", count=0)
            return {"content": [{"type": "text", "text": f"Объект '{request.object_name}' не найден или не содержит элементов"}]}

        text = mcp_formatter.format_object_members_list(
            request.object_name,
            request.member_type,
            methods,
            properties,
            events,
            total
        )

        _log_mcp_success("list_object_members", count=total)
        return {"content": [{"type": "text", "text": text}]}

    except Exception as e:
        _log_mcp_error("list_object_members", str(e))
        return {"content": [], "error": str(e)}


async def handle_get_examples(request: GetExamplesRequest) -> dict:
    """Получить примеры использования кода для элемента."""
    _log_mcp_request("get_examples", element_name=request.element_name, 
                    object_name=request.object_name, limit=request.limit)

    try:
        result = await search_service.get_examples_for_element(
            request.element_name,
            request.object_name,
            request.limit
        )

        if result.get("error"):
            _log_mcp_error("get_examples", result["error"])
            return {"content": [], "error": result["error"]}

        examples = result.get("examples", [])

        if not examples:
            _log_mcp_success("get_examples", count=0)
            return {"content": [{"type": "text", "text": f"Примеры для '{request.element_name}' не найдены"}]}

        text = f"📋 **Примеры для '{request.element_name}':**\n\n"
        for i, example in enumerate(examples, 1):
            text += f"**Пример {i}:**\n"
            text += f"```\n{example}\n```\n\n"

        _log_mcp_success("get_examples", count=len(examples))
        return {"content": [{"type": "text", "text": text}]}

    except Exception as e:
        _log_mcp_error("get_examples", str(e))
        return {"content": [], "error": str(e)}


async def handle_get_methods(request: GetMethodsRequest) -> dict:
    """Получить список методов объекта."""
    _log_mcp_request("get_methods", object_name=request.object_name, limit=request.limit)

    try:
        methods = await search_service.get_methods(request.object_name, request.limit)

        if not methods:
            _log_mcp_success("get_methods", count=0)
            return {"content": [{"type": "text", "text": f"Методы для '{request.object_name}' не найдены"}]}

        text = f"🔧 **Методы объекта '{request.object_name}':**\n\n"
        for i, method in enumerate(methods, 1):
            name = method.get("name", "Unknown")
            syntax = method.get("syntax_ru", "")
            desc = method.get("description", "")[:100]
            text += f"**{i}. {name}**\n"
            if syntax:
                text += f"   {syntax}\n"
            if desc:
                text += f"   {desc}...\n"
            text += "\n"

        _log_mcp_success("get_methods", count=len(methods))
        return {"content": [{"type": "text", "text": text}]}

    except Exception as e:
        _log_mcp_error("get_methods", str(e))
        return {"content": [], "error": str(e)}


async def handle_get_properties(request: GetPropertiesRequest) -> dict:
    """Получить список свойств объекта."""
    _log_mcp_request("get_properties", object_name=request.object_name, limit=request.limit)

    try:
        properties = await search_service.get_properties(request.object_name, request.limit)

        if not properties:
            _log_mcp_success("get_properties", count=0)
            return {"content": [{"type": "text", "text": f"Свойства для '{request.object_name}' не найдены"}]}

        text = f"📦 **Свойства объекта '{request.object_name}':**\n\n"
        for i, prop in enumerate(properties, 1):
            name = prop.get("name", "Unknown")
            prop_type = prop.get("type", "")
            desc = prop.get("description", "")[:100]
            text += f"**{i}. {name}**"
            if prop_type:
                text += f" ({prop_type})"
            text += "\n"
            if desc:
                text += f"   {desc}...\n"
            text += "\n"

        _log_mcp_success("get_properties", count=len(properties))
        return {"content": [{"type": "text", "text": text}]}

    except Exception as e:
        _log_mcp_error("get_properties", str(e))
        return {"content": [], "error": str(e)}


async def handle_get_events(request: GetEventsRequest) -> dict:
    """Получить список событий объекта."""
    _log_mcp_request("get_events", object_name=request.object_name, limit=request.limit)

    try:
        events = await search_service.get_events(request.object_name, request.limit)

        if not events:
            _log_mcp_success("get_events", count=0)
            return {"content": [{"type": "text", "text": f"События для '{request.object_name}' не найдены"}]}

        text = f"⚡ **События объекта '{request.object_name}':**\n\n"
        for i, event in enumerate(events, 1):
            name = event.get("name", "Unknown")
            desc = event.get("description", "")[:100]
            text += f"**{i}. {name}**\n"
            if desc:
                text += f"   {desc}...\n"
            text += "\n"

        _log_mcp_success("get_events", count=len(events))
        return {"content": [{"type": "text", "text": text}]}

    except Exception as e:
        _log_mcp_error("get_events", str(e))
        return {"content": [], "error": str(e)}