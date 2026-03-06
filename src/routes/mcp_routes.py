"""Модуль маршрутов для MCP протокола."""

import asyncio
import json
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from src.core.logging import get_logger
from src.models.mcp_models import (
    MCPToolsResponse, MCPTool, MCPToolParameter, MCPToolType,
    Find1CHelpRequest, GetSyntaxInfoRequest, GetQuickReferenceRequest,
    SearchByContextRequest, ListObjectMembersRequest
)
from src.handlers.mcp_handlers import (
    handle_find_1c_help, handle_get_syntax_info, handle_get_quick_reference,
    handle_search_by_context, handle_list_object_members
)

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/tools", response_model=MCPToolsResponse)
async def get_mcp_tools():
    """Возвращает список доступных MCP инструментов."""
    tools = [
        MCPTool(
            name=MCPToolType.FIND_1C_HELP,
            description="Универсальный поиск справки по любому элементу 1С",
            parameters=[
                MCPToolParameter(
                    name="query",
                    type="string",
                    description="Поисковый запрос (имя элемента, описание, ключевые слова)",
                    required=True
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="Максимальное количество результатов (по умолчанию: 10)",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.GET_SYNTAX_INFO,
            description="Получить полную техническую информацию об элементе с синтаксисом и параметрами",
            parameters=[
                MCPToolParameter(
                    name="element_name",
                    type="string",
                    description="Имя элемента (функции, метода, свойства)",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Имя объекта (для методов объектов)",
                    required=False
                ),
                MCPToolParameter(
                    name="include_examples",
                    type="boolean",
                    description="Включить примеры использования",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.GET_QUICK_REFERENCE,
            description="Получить краткую справку об элементе (только синтаксис и описание)",
            parameters=[
                MCPToolParameter(
                    name="element_name",
                    type="string",
                    description="Имя элемента",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Имя объекта (необязательно)",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.SEARCH_BY_CONTEXT,
            description="Поиск элементов с фильтром по контексту (глобальные функции или методы объектов)",
            parameters=[
                MCPToolParameter(
                    name="query",
                    type="string",
                    description="Поисковый запрос",
                    required=True
                ),
                MCPToolParameter(
                    name="context",
                    type="string",
                    description="Контекст поиска: global, object, all",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Имя объекта (для context=object)",
                    required=False
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="Максимальное количество результатов",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.LIST_OBJECT_MEMBERS,
            description="Получить список всех элементов объекта (методы, свойства, события)",
            parameters=[
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Имя объекта 1С",
                    required=True
                ),
                MCPToolParameter(
                    name="member_type",
                    type="string",
                    description="Тип элементов: all, methods, properties, events",
                    required=False
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="Максимальное количество результатов",
                    required=False
                )
            ]
        )
    ]
    
    return MCPToolsResponse(tools=tools)


@router.get("")
async def mcp_sse_endpoint():
    """MCP Server-Sent Events endpoint - поддержка SSE для MCP протокола."""
    
    async def sse_event_stream():
        """Генератор SSE событий для MCP протокола"""
        session_id = str(uuid.uuid4())
        message_queue = asyncio.Queue()
        
        if not hasattr(router, 'app'):
            router.app = router.router
        router.app.state.sse_sessions[session_id] = message_queue
        
        try:
            yield f"event: endpoint\n"
            yield f"data: /mcp?session_id={session_id}\n\n"
            
            while True:
                try:
                    message = await asyncio.wait_for(message_queue.get(), timeout=30.0)
                    yield f"event: message\n"
                    yield f"data: {json.dumps(message)}\n\n"
                    
                except asyncio.TimeoutError:
                    yield f"event: ping\n"
                    yield f"data: {json.dumps({'timestamp': int(time.time())})}\n\n"
                    
        except asyncio.CancelledError:
            logger.info(f"SSE соединение закрыто для session {session_id}")
            if hasattr(router, 'app') and session_id in router.app.state.sse_sessions:
                del router.app.state.sse_sessions[session_id]
            raise
    
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


@router.post("")
async def mcp_sse_or_jsonrpc_endpoint(request: Request):
    """Endpoint для обработки сообщений - поддерживает SSE и обычный JSON-RPC."""
    
    try:
        session_id = request.query_params.get("session_id")
        data = await request.json()
        logger.info(f"Получен запрос{' для session ' + session_id if session_id else ''}: {data.get('method', 'unknown') if isinstance(data, dict) else 'batch'}")
        
        if isinstance(data, list):
            results = []
            for item in data:
                result = await process_single_jsonrpc_request(item)
                results.append(result)
            response_data = results
        else:
            response_data = await process_single_jsonrpc_request(data)
        
        if session_id and hasattr(request.app.state, 'sse_sessions') and session_id in request.app.state.sse_sessions:
            queue = request.app.state.sse_sessions[session_id]
            await queue.put(response_data)
            return JSONResponse(content={"status": "queued"})
        else:
            return JSONResponse(content=response_data)
            
    except Exception as e:
        logger.error(f"Ошибка обработки запроса: {e}")
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }
        return JSONResponse(status_code=500, content=error_response)


async def process_single_jsonrpc_request(data):
    """Обрабатывает одиночный JSON-RPC запрос."""
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
        tools_response = await get_mcp_tools()
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                param.name: {
                                    "type": param.type,
                                    "description": param.description
                                }
                                for param in tool.parameters
                            },
                            "required": [param.name for param in tool.parameters if param.required]
                        }
                    }
                    for tool in tools_response.tools
                ]
            }
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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для MCP протокола."""
    await websocket.accept()
    
    session_id = str(uuid.uuid4())
    message_queue = asyncio.Queue()
    websocket.app.state.sse_sessions[session_id] = message_queue
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                request_data = json.loads(data)
                response = await process_single_jsonrpc_request(request_data)
                await websocket.send_text(json.dumps(response))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid JSON"}
                }))
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
        if session_id in websocket.app.state.sse_sessions:
            del websocket.app.state.sse_sessions[session_id]
