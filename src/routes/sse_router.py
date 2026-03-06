"""Маршрут для SSE эндпоинта на /sse для совместимости с Qwen MCP конфигурацией."""

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, Response

from src.core.logging import get_logger
from src.core.constants import SSE_QUEUE_MAX_SIZE, SSE_PING_INTERVAL_SECONDS, SSE_SESSION_TIMEOUT_SECONDS

logger = get_logger(__name__)

router = APIRouter(tags=["sse"])


@router.get("/sse")
async def sse_endpoint(request: Request):
    """
    Server-Sent Events endpoint для MCP протокола.
    
    Этот эндпоинт обеспечивает совместимость с клиентами,
    ожидающими SSE на пути /sse (например, Qwen Code MCP).
    
    Реализация использует ту же логику, что и /mcp GET endpoint.
    """
    
    async def sse_event_stream():
        """Генератор SSE событий для MCP протокола"""
        session_id = str(uuid.uuid4())
        message_queue = asyncio.Queue(maxsize=SSE_QUEUE_MAX_SIZE)

        # Используем request.app.state для доступа к хранилищу сессий
        request.app.state.sse_sessions[session_id] = message_queue
        logger.debug(f"SSE сессия создана: {session_id}")

        session_start = time.time()  # Запоминаем время начала

        try:
            # Отправляем endpoint URL для POST сообщений
            yield f"event: endpoint\n"
            yield f"data: /sse\n\n"
            
            # Отправляем ping для инициализации соединения
            yield f"event: ping\n"
            yield f"data: {{\"status\": \"connected\"}}\n\n"
            
            # Принудительный флеш буфера
            await asyncio.sleep(0)
            
            # Ждём пока клиент отправит POST запрос
            while True:
                # Проверка таймаута сессии
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
            # Очистка сессии при завершении
            try:
                del request.app.state.sse_sessions[session_id]
                logger.debug(f"SSE сессия удалена: {session_id}")
            except KeyError:
                logger.debug(f"SSE сессия {session_id} уже удалена")

    return StreamingResponse(
        sse_event_stream(),
        status_code=200,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked"
        }
    )


@router.post("/sse")
async def sse_message_handler(request: Request):
    """
    Обработчик POST сообщений для SSE сессий.

    Клиенты отправляют JSON-RPC запросы на этот эндпоинт,
    а ответы получают через SSE stream.
    """

    try:
        # Получаем session_id из заголовка MCP-Session-ID или query параметра
        session_id = request.headers.get("mcp-session-id") or request.query_params.get("session_id")
        data = await request.json()
        logger.info(f"Получен SSE запрос{' для session ' + session_id if session_id else ''}: {data.get('method', 'unknown') if isinstance(data, dict) else 'batch'}")

        if isinstance(data, list):
            results = []
            for item in data:
                result = await process_single_jsonrpc_request(item)
                results.append(result)
            response_data = results
        else:
            response_data = await process_single_jsonrpc_request(data)

        # Если это SSE запрос, отправляем ответ через очередь
        if session_id and session_id in request.app.state.sse_sessions:
            queue = request.app.state.sse_sessions[session_id]
            try:
                queue.put_nowait(response_data)
            except asyncio.QueueFull:
                logger.warning(f"Очередь переполнена для session {session_id}, сообщение потеряно")
                return Response(
                    content="event: message\ndata: {\"status\": \"error\", \"error\": \"Message queue full\"}\n\n",
                    media_type="text/event-stream"
                )
            return Response(
                content="event: message\ndata: {\"status\": \"queued\"}\n\n",
                media_type="text/event-stream"
            )
        else:
            # Обычный JSON-RPC ответ (если сессия не найдена)
            return Response(
                content=f"event: message\ndata: {json.dumps(response_data, ensure_ascii=False)}\n\n",
                media_type="text/event-stream"
            )

    except asyncio.CancelledError:
        logger.info("Запрос отменён во время обработки")
        raise
    except Exception as e:
        logger.error(f"Ошибка обработки SSE запроса: {e}")
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }


# Импортируем функцию обработки из mcp_routes для переиспользования логики
async def process_single_jsonrpc_request(data):
    """
    Обрабатывает одиночный JSON-RPC запрос.
    Дублирует логику из mcp_routes.py для независимости модуля.
    """
    from src.models.mcp_models import (
        MCPToolType, Find1CHelpRequest, GetSyntaxInfoRequest,
        GetQuickReferenceRequest, SearchByContextRequest, ListObjectMembersRequest
    )
    from src.handlers.mcp_handlers import (
        handle_find_1c_help, handle_get_syntax_info, handle_get_quick_reference,
        handle_search_by_context, handle_list_object_members
    )
    
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": data.get("id") if isinstance(data, dict) else None,
            "error": {"code": -32600, "message": "Invalid Request"}
        }

    method = data.get("method")
    params = data.get("params", {})
    request_id = data.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {},
                    "prompts": {},
                    "roots": {"listChanged": False},
                    "sampling": {}
                },
                "serverInfo": {
                    "name": "1c-syntax-helper-mcp",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "tools/list":
        # Импортируем функцию получения инструментов
        tools = [
            {
                "name": "find_1c_help",
                "description": "Универсальный поиск справки по любому элементу 1С",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "limit": {"type": "number", "description": "Максимум результатов"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_syntax_info",
                "description": "Полная техническая информация об элементе",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element_name": {"type": "string", "description": "Имя элемента"},
                        "object_name": {"type": "string", "description": "Имя объекта"},
                        "include_examples": {"type": "boolean", "description": "Включить примеры"}
                    },
                    "required": ["element_name"]
                }
            },
            {
                "name": "get_quick_reference",
                "description": "Краткая справка об элементе",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element_name": {"type": "string", "description": "Имя элемента"},
                        "object_name": {"type": "string", "description": "Имя объекта"}
                    },
                    "required": ["element_name"]
                }
            },
            {
                "name": "search_by_context",
                "description": "Поиск с фильтром по контексту",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "context": {"type": "string", "description": "Контекст: global, object, all"},
                        "object_name": {"type": "string", "description": "Имя объекта"},
                        "limit": {"type": "number", "description": "Максимум результатов"}
                    },
                    "required": ["query", "context"]
                }
            },
            {
                "name": "list_object_members",
                "description": "Список методов и свойств объекта",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "object_name": {"type": "string", "description": "Имя объекта 1С"},
                        "member_type": {"type": "string", "description": "Тип: all, methods, properties, events"},
                        "limit": {"type": "number", "description": "Максимум результатов"}
                    },
                    "required": ["object_name"]
                }
            }
        ]
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tools}
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        try:
            result = await call_mcp_tool(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
            }
        except Exception as e:
            logger.error(f"Ошибка вызова инструмента {tool_name}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)}
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


async def call_mcp_tool(tool_name: str, args: dict):
    """Вызывает соответствующий MCP инструмент."""
    from src.models.mcp_models import (
        MCPToolType, Find1CHelpRequest, GetSyntaxInfoRequest,
        GetQuickReferenceRequest, SearchByContextRequest, ListObjectMembersRequest
    )
    from src.handlers.mcp_handlers import (
        handle_find_1c_help, handle_get_syntax_info, handle_get_quick_reference,
        handle_search_by_context, handle_list_object_members
    )

    if tool_name == MCPToolType.FIND_1C_HELP:
        request = Find1CHelpRequest(**args)
        return await handle_find_1c_help(request)

    elif tool_name == MCPToolType.GET_SYNTAX_INFO:
        request = GetSyntaxInfoRequest(**args)
        return await handle_get_syntax_info(request)

    elif tool_name == MCPToolType.GET_QUICK_REFERENCE:
        request = GetQuickReferenceRequest(**args)
        return await handle_get_quick_reference(request)

    elif tool_name == MCPToolType.SEARCH_BY_CONTEXT:
        request = SearchByContextRequest(**args)
        return await handle_search_by_context(request)

    elif tool_name == MCPToolType.LIST_OBJECT_MEMBERS:
        request = ListObjectMembersRequest(**args)
        return await handle_list_object_members(request)

    else:
        raise ValueError(f"Unknown tool: {tool_name}")
