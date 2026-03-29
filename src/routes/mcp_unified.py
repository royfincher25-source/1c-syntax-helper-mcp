"""Унифицированный MCP роутер с поддержкой SSE и HTTP."""

import asyncio
import json
import time
import uuid
import traceback
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.core.logging import get_logger
from src.core.constants import (
    SSE_QUEUE_MAX_SIZE,
    SSE_PING_INTERVAL_SECONDS,
    SSE_SESSION_TIMEOUT_SECONDS
)
from src.models.mcp_models import (
    Find1CHelpRequest, GetSyntaxInfoRequest,
    GetQuickReferenceRequest, SearchByContextRequest,
    ListObjectMembersRequest, MCPToolType,
    GetExamplesRequest, GetMethodsRequest, GetPropertiesRequest, GetEventsRequest
)
from src.handlers.mcp_handlers import (
    handle_find_1c_help, handle_get_syntax_info, handle_get_quick_reference,
    handle_search_by_context, handle_list_object_members,
    handle_get_examples, handle_get_methods, handle_get_properties, handle_get_events
)

logger = get_logger(__name__)

router = APIRouter(prefix="", tags=["mcp"])




TOOLS_SCHEMA = [
    {
        "name": MCPToolType.FIND_1C_HELP,
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
        "name": MCPToolType.GET_SYNTAX_INFO,
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
        "name": MCPToolType.GET_QUICK_REFERENCE,
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
        "name": MCPToolType.SEARCH_BY_CONTEXT,
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
        "name": MCPToolType.LIST_OBJECT_MEMBERS,
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
    },
    {
        "name": MCPToolType.GET_EXAMPLES,
        "description": "Получить примеры использования кода для элемента",
        "inputSchema": {
            "type": "object",
            "properties": {
                "element_name": {"type": "string", "description": "Имя элемента"},
                "object_name": {"type": "string", "description": "Имя объекта"},
                "limit": {"type": "number", "description": "Максимум результатов"}
            },
            "required": ["element_name"]
        }
    },
    {
        "name": MCPToolType.GET_METHODS,
        "description": "Получить список методов объекта",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Имя объекта 1С"},
                "limit": {"type": "number", "description": "Максимум результатов"}
            },
            "required": ["object_name"]
        }
    },
    {
        "name": MCPToolType.GET_PROPERTIES,
        "description": "Получить список свойств объекта",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Имя объекта 1С"},
                "limit": {"type": "number", "description": "Максимум результатов"}
            },
            "required": ["object_name"]
        }
    },
    {
        "name": MCPToolType.GET_EVENTS,
        "description": "Получить список событий объекта",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Имя объекта 1С"},
                "limit": {"type": "number", "description": "Максимум результатов"}
            },
            "required": ["object_name"]
        }
    }
]


@router.get("/mcp")
@router.get("/sse")
async def mcp_sse_endpoint(request: Request):
    """SSE endpoint для MCP протокола (/mcp или /sse)."""
    session_id = str(uuid.uuid4())
    message_queue = asyncio.Queue(maxsize=SSE_QUEUE_MAX_SIZE)

    _ensure_sessions(request)
    request.app.state.sse_sessions[session_id] = message_queue
    logger.debug(f"SSE сессия создана: {session_id}")

    async def sse_event_stream():
        session_start = time.time()
        try:
            yield f"event: endpoint\n"
            yield f"data: /mcp?session_id={session_id}\n\n"
            await asyncio.sleep(0)

            while True:
                if time.time() - session_start > SSE_SESSION_TIMEOUT_SECONDS:
                    logger.debug(f"SSE timeout: {session_id}")
                    break

                try:
                    message = await asyncio.wait_for(
                        message_queue.get(),
                        timeout=SSE_PING_INTERVAL_SECONDS
                    )
                    yield f"event: message\n"
                    yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: ping\n"
                    yield f"data: {json.dumps({'timestamp': int(time.time())})}\n\n"

        except asyncio.CancelledError:
            logger.debug(f"SSE cancelled: {session_id}")
            raise
        finally:
            _cleanup_session(request, session_id)

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/mcp")
@router.post("/sse")
async def mcp_jsonrpc_endpoint(request: Request):
    """JSON-RPC endpoint для MCP - поддерживает SSE и HTTP режимы."""
    session_id = None
    try:
        session_id = request.query_params.get("session_id")
        
        body = await request.body()
        
        try:
            data = json.loads(body)
            logger.debug(f"MCP parsed JSON: {data}")
        except (json.JSONDecodeError, UnicodeDecodeError) as je:
            logger.error(f"JSON/Unicode decode failed: {je}, body bytes: {body[:200] if body else b''}")
            raise

        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            return _make_error(-32600, "Invalid Request", session_id, request)

        response_data = await _process_jsonrpc(data)
        return _send_response(request, session_id, response_data)

    except json.JSONDecodeError as e:
        logger.error(f"MCP JSON decode error: {e}")
        return _make_error(-32700, f"Parse error: {e}", session_id, request)
    except UnicodeDecodeError as e:
        logger.error(f"MCP Unicode decode error: {e}\n{traceback.format_exc()}")
        return _make_error(-32700, f"Unicode decode error: {e}", session_id, request)
    except Exception as e:
        logger.error(f"MCP error: {e}\n{traceback.format_exc()}")
        return _make_error(-32603, str(e), session_id, request)


@router.get("/mcp/tools")
async def list_tools():
    """Список доступных инструментов."""
    return {"tools": TOOLS_SCHEMA}


def _ensure_sessions(request: Request):
    if not hasattr(request.app.state, 'sse_sessions'):
        request.app.state.sse_sessions = {}


def _cleanup_session(request: Request, session_id: str):
    try:
        if hasattr(request.app.state, 'sse_sessions'):
            request.app.state.sse_sessions.pop(session_id, None)
    except Exception:
        pass


def _make_error(code: int, message: str, session_id: Optional[str], request: Request):
    error_response = {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": code, "message": message}
    }
    return _send_response(request, session_id, error_response)


def _send_response(request: Request, session_id: Optional[str], response_data: dict):
    if session_id and hasattr(request.app.state, 'sse_sessions') and session_id in request.app.state.sse_sessions:
        queue = request.app.state.sse_sessions[session_id]
        try:
            queue.put_nowait(response_data)
            return JSONResponse(content={"status": "queued"})
        except asyncio.QueueFull:
            return JSONResponse(
                status_code=503,
                content={"error": "Queue full"}
            )
    return JSONResponse(content=response_data)


async def _process_jsonrpc(data: dict) -> dict:
    method = data.get("method")
    request_id = data.get("id")
    params = data.get("params", {})

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
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS_SCHEMA}
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        try:
            result = await _call_tool(tool_name, tool_args)
            result = _clean_response_data(result)
        except UnicodeDecodeError as e:
            logger.error(f"Unicode decode error in tool call: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": "Data encoding error"}
            }
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)}
            }
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"status": "ok"}}

    elif method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}}

    elif method == "prompts/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"prompts": []}}

    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


def _clean_response_data(data):
    """Recursively clean all values in response data to ensure valid UTF-8."""
    if data is None:
        return None
    elif isinstance(data, dict):
        return {str(k): _clean_response_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_clean_response_data(item) for item in data]
    elif isinstance(data, bytes):
        try:
            return data.decode('utf-8', errors='replace')
        except Exception:
            return str(data)
    elif isinstance(data, str):
        try:
            return data.encode('utf-8', errors='replace').decode('utf-8')
        except Exception:
            return str(data)
    elif isinstance(data, (int, float, bool)):
        return data
    else:
        try:
            return str(data)
        except Exception:
            return None


async def _call_tool(tool_name: str, args: dict) -> dict:
    if tool_name == MCPToolType.FIND_1C_HELP:
        return await handle_find_1c_help(Find1CHelpRequest(**args))
    elif tool_name == MCPToolType.GET_SYNTAX_INFO:
        return await handle_get_syntax_info(GetSyntaxInfoRequest(**args))
    elif tool_name == MCPToolType.GET_QUICK_REFERENCE:
        return await handle_get_quick_reference(GetQuickReferenceRequest(**args))
    elif tool_name == MCPToolType.SEARCH_BY_CONTEXT:
        return await handle_search_by_context(SearchByContextRequest(**args))
    elif tool_name == MCPToolType.LIST_OBJECT_MEMBERS:
        return await handle_list_object_members(ListObjectMembersRequest(**args))
    elif tool_name == MCPToolType.GET_EXAMPLES:
        return await handle_get_examples(GetExamplesRequest(**args))
    elif tool_name == MCPToolType.GET_METHODS:
        return await handle_get_methods(GetMethodsRequest(**args))
    elif tool_name == MCPToolType.GET_PROPERTIES:
        return await handle_get_properties(GetPropertiesRequest(**args))
    elif tool_name == MCPToolType.GET_EVENTS:
        return await handle_get_events(GetEventsRequest(**args))
    else:
        raise ValueError(f"Unknown tool: {tool_name}")
