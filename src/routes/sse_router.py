"""SSE endpoint для MCP протокола - совместимость с Qwen Code."""

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.core.logging import get_logger
from src.core.constants import (
    SSE_QUEUE_MAX_SIZE,
    SSE_PING_INTERVAL_SECONDS,
    SSE_SESSION_TIMEOUT_SECONDS
)
from src.handlers.mcp_handlers import (
    handle_find_1c_help, handle_get_syntax_info, handle_get_quick_reference,
    handle_search_by_context, handle_list_object_members
)
from src.models.mcp_models import MCPToolType

logger = get_logger(__name__)

router = APIRouter(tags=["sse"])


@router.get("/sse")
async def sse_endpoint(request: Request):
    """
    SSE handshake endpoint для MCP протокола.

    Поддерживает постоянное соединение для получения сообщений.
    """
    session_id = str(uuid.uuid4())
    message_queue = asyncio.Queue(maxsize=SSE_QUEUE_MAX_SIZE)

    # Сохраняем сессию в хранилище
    if not hasattr(request.app.state, 'sse_sessions'):
        request.app.state.sse_sessions = {}
    request.app.state.sse_sessions[session_id] = message_queue
    
    logger.info(f"SSE сессия создана: {session_id}")

    async def sse_event_stream():
        """Генератор SSE событий."""
        session_start = time.time()

        try:
            # Отправляем endpoint URL
            yield f"event: endpoint\n"
            yield f"data: /sse?session_id={session_id}\n\n"
            await asyncio.sleep(0)  # Флеш буфера

            while True:
                # Проверка таймаута сессии
                if time.time() - session_start > SSE_SESSION_TIMEOUT_SECONDS:
                    logger.info(f"SSE session timeout for {session_id}")
                    break

                try:
                    # Ждём сообщение из очереди
                    message = await asyncio.wait_for(
                        message_queue.get(),
                        timeout=SSE_PING_INTERVAL_SECONDS
                    )
                    yield f"event: message\n"
                    yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # Отправляем ping для поддержания соединения
                    yield f"event: ping\n"
                    yield f"data: {json.dumps({'timestamp': int(time.time())})}\n\n"

        except asyncio.CancelledError:
            logger.info(f"SSE соединение закрыто для session {session_id}")
            raise
        finally:
            # Очистка сессии
            try:
                del request.app.state.sse_sessions[session_id]
                logger.debug(f"SSE сессия удалена: {session_id}")
            except KeyError:
                pass

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
            "Content-Type": "text/event-stream",
            "Transfer-Encoding": "chunked"
        }
    )


@router.post("/sse")
async def sse_post_endpoint(request: Request):
    """
    Обработчик POST запросов от MCP клиентов.

    Принимает JSON-RPC запросы и отправляет ответы в SSE очередь.
    """
    try:
        # Получаем session_id из query параметров
        session_id = request.query_params.get("session_id")
        data = await request.json()

        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}
            }
            return await send_to_sse_or_respond(request, session_id, error_response)

        method = data.get("method")
        request_id = data.get("id")

        # Обрабатываем initialize
        if method == "initialize":
            response = {
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
            return await send_to_sse_or_respond(request, session_id, response)

        # Обрабатываем tools/list
        elif method == "tools/list":
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
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": tools}
            }
            return await send_to_sse_or_respond(request, session_id, response)

        # Обрабатываем tools/call
        elif method == "tools/call":
            params = data.get("params", {})
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})

            try:
                result = await call_mcp_tool(tool_name, tool_args)
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
                }
            except Exception as e:
                logger.error(f"Ошибка вызова инструмента {tool_name}: {e}")
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32603, "message": str(e)}
                }
            return await send_to_sse_or_respond(request, session_id, response)

        # Обрабатываем ping
        elif method == "ping":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"status": "ok"}
            }
            return await send_to_sse_or_respond(request, session_id, response)

        # Обрабатываем resources/list
        elif method == "resources/list":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"resources": []}
            }
            return await send_to_sse_or_respond(request, session_id, response)

        # Обрабатываем prompts/list
        elif method == "prompts/list":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"prompts": []}
            }
            return await send_to_sse_or_respond(request, session_id, response)

        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }
            return await send_to_sse_or_respond(request, session_id, response)

    except json.JSONDecodeError:
        response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error"}
        }
        return await send_to_sse_or_respond(request, session_id, response)
    except Exception as e:
        logger.error(f"Ошибка обработки SSE запроса: {e}")
        response = {
            "jsonrpc": "2.0",
            "id": data.get("id") if 'data' in locals() else None,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }
        return await send_to_sse_or_respond(request, session_id, response)


async def send_to_sse_or_respond(request: Request, session_id: str, response: dict):
    """Отправляет ответ в SSE очередь или возвращает напрямую."""
    if session_id and hasattr(request.app.state, 'sse_sessions') and session_id in request.app.state.sse_sessions:
        queue = request.app.state.sse_sessions[session_id]
        try:
            queue.put_nowait(response)
            return {"status": "queued"}
        except asyncio.QueueFull:
            logger.warning(f"Очередь переполнена для session {session_id}")
            return {"status": "error", "reason": "Queue full"}
    else:
        # Возвращаем ответ напрямую (для клиентов без SSE)
        return response


async def call_mcp_tool(tool_name: str, args: dict):
    """Вызывает соответствующий MCP инструмент."""
    from src.models.mcp_models import (
        Find1CHelpRequest, GetSyntaxInfoRequest,
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
