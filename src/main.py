"""Р“Р»Р°РІРЅРѕРµ РїСЂРёР»РѕР¶РµРЅРёРµ MCP СЃРµСЂРІРµСЂР° СЃРёРЅС‚Р°РєСЃРёСЃ-РїРѕРјРѕС‰РЅРёРєР° 1РЎ."""

import json
import asyncio
import time
import uuid
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from src.core.config import settings
from src.core.logging import get_logger, LogContext
from src.core.elasticsearch import es_client
from src.core.health import get_health_report, get_basic_health
from src.core.graceful_shutdown import graceful_shutdown, request_context, get_graceful_shutdown
from src.core.validation import ValidationError
from src.core.rate_limiter import get_rate_limiter
from src.core._metrics import get_metrics_collector, get_system_monitor
from src.core.dependency_injection import setup_dependencies
from src.core.lifespan import get_lifespan_manager
from src.core.exception_handlers import setup_exception_handlers
from src.parsers.hbk_parser import HBKParserError
from src.models.mcp_models import (
    MCPRequest, MCPResponse, HealthResponse, 
    MCPToolsResponse, MCPTool, MCPToolParameter, MCPToolType,
    Find1CHelpRequest, GetSyntaxInfoRequest, GetQuickReferenceRequest,
    SearchByContextRequest, ListObjectMembersRequest
)
from src.handlers.mcp_handlers import (
    handle_find_1c_help, handle_get_syntax_info, handle_get_quick_reference,
    handle_search_by_context, handle_list_object_members
)

logger = get_logger(__name__)

# Инициализация LifespanManager
lifespan_manager = get_lifespan_manager(
    hbk_directory=settings.data.hbk_directory,
    auto_index=False  # Отключено для ручного тестирования через API
)


# Создаём приложение FastAPI
app = FastAPI(
    title="1C Syntax Helper MCP Server",
    description="MCP сервер для поиска по синтаксису 1С",
    version="1.0.0",
    lifespan=lifespan_manager.lifespan
)

# Р”РѕР±Р°РІР»СЏРµРј CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Р”РѕР±Р°РІР»СЏРµРј middleware РґР»СЏ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ СЃ request_id
from src.core.request_logging_middleware import RequestLoggingMiddleware
app.add_middleware(RequestLoggingMiddleware)

# Р”РѕР±Р°РІР»СЏРµРј Gzip middleware РґР»СЏ РєРѕРјРїСЂРµСЃСЃРёРё РѕС‚РІРµС‚РѕРІ
from src.core.gzip_middleware import GzipMiddleware
app.add_middleware(GzipMiddleware, min_size=1024, compress_level=6)


# Добавляем middleware для rate limiting
from src.core.rate_limiter import RateLimiterMiddleware
app.add_middleware(RateLimiterMiddleware)


# Настраиваем exception handlers
setup_exception_handlers()


# Подключаем маршруты
from src.routes import health_router, admin_router, mcp_router

app.include_router(health_router)
app.include_router(admin_router)
app.include_router(mcp_router)


# Устаревшие inline маршруты (для совместимости)
async def health_check():
    logger.info("health_check")
    """Базовая проверка состояния системы (для совместимости)."""
    return await get_basic_health()

@app.get("/health/detailed")
async def health_check_detailed():
    """
    Детальная проверка состояния системы.
    
    Проверяет:
    - Elasticsearch (подключение, индекс, cluster health)
    - Кэш (статус, hit rate)
    - Circuit Breaker (состояние)
    - Дисковое пространство
    - Использование памяти
    """
    logger.info("health_check_detailed")
    
    try:
        report = await get_health_report()
        return report
    except Exception as e:
        logger.error(f"Ошибка при проверке health: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }
@app.get("/")
async def root(request: Request) -> JSONResponse:
    return JSONResponse({"message": "MCP 1C Metadata Server Р·Р°РїСѓС‰РµРЅ"})

@app.get("/index/status")
async def index_status():
    """РЎС‚Р°С‚СѓСЃ РёРЅРґРµРєСЃР°С†РёРё."""
    es_connected = await es_client.is_connected()
    index_exists_response = await es_client.index_exists() if es_connected else False
    index_exists = bool(index_exists_response) if index_exists_response else False
    docs_count = await es_client.get_documents_count() if index_exists else 0

    return {
        "elasticsearch_connected": es_connected,
        "index_exists": index_exists,
        "documents_count": docs_count,
        "index_name": settings.elasticsearch.index_name
    }


@app.get("/cache/stats")
async def cache_statistics():
    """РЎС‚Р°С‚РёСЃС‚РёРєР° РєСЌС€Р°."""
    from src.core.cache import cache

    stats = await cache.get_stats()
    return stats


@app.get("/shutdown/status")
async def shutdown_status():
    """РЎС‚Р°С‚СѓСЃ graceful shutdown."""
    return {
        "is_shutting_down": graceful_shutdown.is_shutting_down,
        "active_requests": graceful_shutdown.active_requests,
        "shutdown_timeout": graceful_shutdown.shutdown_timeout
    }


@app.post("/shutdown/initiate")
async def initiate_shutdown():
    """
    РЈРїСЂР°РІР»СЏРµРјРѕРµ Р·Р°РїСѓСЃРє Graceful Shutdown (РґР»СЏ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂРѕРІ).
    
    Р’РЅРёРјР°РЅРёРµ: Р­С‚Рѕ РѕС‚РєР»СЋС‡РёС‚ СЃРµСЂРІРµСЂ РїРѕСЃР»Рµ Р·Р°РІРµСЂС€РµРЅРёСЏ С‚РµРєСѓС‰РёС… Р·Р°РїСЂРѕСЃРѕРІ.
    """
    if graceful_shutdown.is_shutting_down:
        return {
            "status": "already_shutting_down",
            "active_requests": graceful_shutdown.active_requests
        }
    
    # Р—Р°РїСѓСЃРєР°РµРј shutdown РІ С„РѕРЅРµ
    asyncio.create_task(graceful_shutdown.shutdown("admin_request"))
    
    return {
        "status": "shutdown_initiated",
        "message": f"Graceful shutdown started. Active requests: {graceful_shutdown.active_requests}"
    }


@app.post("/cache/clear")
async def clear_cache():
    """РћС‡РёСЃС‚РєР° РєСЌС€Р°."""
    from src.core.cache import cache
    
    await cache.clear()
    return {"status": "success", "message": "РљСЌС€ РѕС‡РёС‰РµРЅ"}


@app.post("/index/rebuild")
async def rebuild_index():
    """РџРµСЂРµРёРЅРґРµРєСЃР°С†РёСЏ РґРѕРєСѓРјРµРЅС‚Р°С†РёРё РёР· .hbk С„Р°Р№Р»Р°."""
    try:
        from pathlib import Path
        
        # РџСЂРѕРІРµСЂСЏРµРј РїРѕРґРєР»СЋС‡РµРЅРёРµ Рє Elasticsearch
        if not await es_client.is_connected():
            raise HTTPException(
                status_code=503,
                detail="Elasticsearch РЅРµРґРѕСЃС‚СѓРїРµРЅ"
            )
        
        # РС‰РµРј .hbk С„Р°Р№Р»С‹
        hbk_dir = Path(settings.data.hbk_directory)
        if not hbk_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Р”РёСЂРµРєС‚РѕСЂРёСЏ .hbk С„Р°Р№Р»РѕРІ РЅРµ РЅР°Р№РґРµРЅР°: {hbk_dir}"
            )
        
        hbk_files = list(hbk_dir.glob("*.hbk"))
        if not hbk_files:
            raise HTTPException(
                status_code=400,
                detail=f"Р¤Р°Р№Р»С‹ .hbk РЅРµ РЅР°Р№РґРµРЅС‹ РІ {hbk_dir}"
            )
        
        # РРЅРґРµРєСЃРёСЂСѓРµРј РїРµСЂРІС‹Р№ РЅР°Р№РґРµРЅРЅС‹Р№ С„Р°Р№Р»
        hbk_file = hbk_files[0]
        logger.info(f"РќР°С‡РёРЅР°РµРј РїРµСЂРµРёРЅРґРµРєСЃР°С†РёСЋ С„Р°Р№Р»Р°: {hbk_file}")
        
        success = await index_hbk_file(str(hbk_file))
        
        if success:
            docs_count = await es_client.get_documents_count()
            return {
                "status": "success",
                "message": "РџРµСЂРµРёРЅРґРµРєСЃР°С†РёСЏ Р·Р°РІРµСЂС€РµРЅР° СѓСЃРїРµС€РЅРѕ",
                "file": str(hbk_file),
                "documents_count": docs_count
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="РћС€РёР±РєР° РїРµСЂРµРёРЅРґРµРєСЃР°С†РёРё"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РїРµСЂРµРёРЅРґРµРєСЃР°С†РёРё: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Р’РЅСѓС‚СЂРµРЅРЅСЏСЏ РѕС€РёР±РєР°: {str(e)}"
        )


@app.get("/mcp/tools", response_model=MCPToolsResponse)
async def get_mcp_tools():
    logger.info("get_mcp_tools")
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРїРёСЃРѕРє РґРѕСЃС‚СѓРїРЅС‹С… MCP РёРЅСЃС‚СЂСѓРјРµРЅС‚РѕРІ."""
    tools = [
        MCPTool(
            name=MCPToolType.FIND_1C_HELP,
            description="РЈРЅРёРІРµСЂСЃР°Р»СЊРЅС‹Р№ РїРѕРёСЃРє СЃРїСЂР°РІРєРё РїРѕ Р»СЋР±РѕРјСѓ СЌР»РµРјРµРЅС‚Сѓ 1РЎ",
            parameters=[
                MCPToolParameter(
                    name="query",
                    type="string",
                    description="РџРѕРёСЃРєРѕРІС‹Р№ Р·Р°РїСЂРѕСЃ (РёРјСЏ СЌР»РµРјРµРЅС‚Р°, РѕРїРёСЃР°РЅРёРµ, РєР»СЋС‡РµРІС‹Рµ СЃР»РѕРІР°)",
                    required=True
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="РњР°РєСЃРёРјР°Р»СЊРЅРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ: 10)",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.GET_SYNTAX_INFO,
            description="РџРѕР»СѓС‡РёС‚СЊ РїРѕР»РЅСѓСЋ С‚РµС…РЅРёС‡РµСЃРєСѓСЋ РёРЅС„РѕСЂРјР°С†РёСЋ РѕР± СЌР»РµРјРµРЅС‚Рµ СЃ СЃРёРЅС‚Р°РєСЃРёСЃРѕРј Рё РїР°СЂР°РјРµС‚СЂР°РјРё",
            parameters=[
                MCPToolParameter(
                    name="element_name",
                    type="string",
                    description="РРјСЏ СЌР»РµРјРµРЅС‚Р° (С„СѓРЅРєС†РёРё, РјРµС‚РѕРґР°, СЃРІРѕР№СЃС‚РІР°)",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="РРјСЏ РѕР±СЉРµРєС‚Р° (РґР»СЏ РјРµС‚РѕРґРѕРІ РѕР±СЉРµРєС‚РѕРІ)",
                    required=False
                ),
                MCPToolParameter(
                    name="include_examples",
                    type="boolean",
                    description="Р’РєР»СЋС‡РёС‚СЊ РїСЂРёРјРµСЂС‹ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.GET_QUICK_REFERENCE,
            description="РџРѕР»СѓС‡РёС‚СЊ РєСЂР°С‚РєСѓСЋ СЃРїСЂР°РІРєСѓ РѕР± СЌР»РµРјРµРЅС‚Рµ (С‚РѕР»СЊРєРѕ СЃРёРЅС‚Р°РєСЃРёСЃ Рё РѕРїРёСЃР°РЅРёРµ)",
            parameters=[
                MCPToolParameter(
                    name="element_name",
                    type="string",
                    description="РРјСЏ СЌР»РµРјРµРЅС‚Р°",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="РРјСЏ РѕР±СЉРµРєС‚Р° (РЅРµРѕР±СЏР·Р°С‚РµР»СЊРЅРѕ)",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.SEARCH_BY_CONTEXT,
            description="РџРѕРёСЃРє СЌР»РµРјРµРЅС‚РѕРІ СЃ С„РёР»СЊС‚СЂРѕРј РїРѕ РєРѕРЅС‚РµРєСЃС‚Сѓ (РіР»РѕР±Р°Р»СЊРЅС‹Рµ С„СѓРЅРєС†РёРё РёР»Рё РјРµС‚РѕРґС‹ РѕР±СЉРµРєС‚РѕРІ)",
            parameters=[
                MCPToolParameter(
                    name="query",
                    type="string",
                    description="РџРѕРёСЃРєРѕРІС‹Р№ Р·Р°РїСЂРѕСЃ",
                    required=True
                ),
                MCPToolParameter(
                    name="context",
                    type="string",
                    description="РљРѕРЅС‚РµРєСЃС‚ РїРѕРёСЃРєР°: global, object, all",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Р¤РёР»СЊС‚СЂ РїРѕ РєРѕРЅРєСЂРµС‚РЅРѕРјСѓ РѕР±СЉРµРєС‚Сѓ (РґР»СЏ context=object)",
                    required=False
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="РњР°РєСЃРёРјР°Р»СЊРЅРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.LIST_OBJECT_MEMBERS,
            description="РџРѕР»СѓС‡РёС‚СЊ СЃРїРёСЃРѕРє РІСЃРµС… СЌР»РµРјРµРЅС‚РѕРІ РѕР±СЉРµРєС‚Р° (РјРµС‚РѕРґС‹, СЃРІРѕР№СЃС‚РІР°, СЃРѕР±С‹С‚РёСЏ)",
            parameters=[
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="РРјСЏ РѕР±СЉРµРєС‚Р° 1РЎ",
                    required=True
                ),
                MCPToolParameter(
                    name="member_type",
                    type="string",
                    description="РўРёРї СЌР»РµРјРµРЅС‚РѕРІ: all, methods, properties, events",
                    required=False
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="РњР°РєСЃРёРјР°Р»СЊРЅРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ",
                    required=False
                )
            ]
        )
    ]
    
    return MCPToolsResponse(tools=tools)


@app.get("/mcp")
async def mcp_sse_endpoint():
    """MCP Server-Sent Events endpoint - РїРѕРґРґРµСЂР¶РєР° SSE РґР»СЏ MCP РїСЂРѕС‚РѕРєРѕР»Р°."""
    from fastapi.responses import StreamingResponse
    
    logger.info("mcp_sse_endpoint - Р·Р°РїСѓСЃРє SSE СЃРѕРµРґРёРЅРµРЅРёСЏ")
    
    async def sse_event_stream():
        """Р“РµРЅРµСЂР°С‚РѕСЂ SSE СЃРѕР±С‹С‚РёР№ РґР»СЏ MCP РїСЂРѕС‚РѕРєРѕР»Р°"""
        import uuid
        import queue
        import threading
        
        # Р“РµРЅРµСЂРёСЂСѓРµРј СѓРЅРёРєР°Р»СЊРЅС‹Р№ session_id
        session_id = str(uuid.uuid4())
        
        # РЎРѕР·РґР°РµРј РѕС‡РµСЂРµРґСЊ РґР»СЏ СЃРѕРѕР±С‰РµРЅРёР№
        message_queue = asyncio.Queue()
        
        # РЎРѕС…СЂР°РЅСЏРµРј РѕС‡РµСЂРµРґСЊ РІ РіР»РѕР±Р°Р»СЊРЅРѕРј С…СЂР°РЅРёР»РёС‰Рµ СЃРµСЃСЃРёР№
        if not hasattr(app.state, 'sse_sessions'):
            app.state.sse_sessions = {}
        app.state.sse_sessions[session_id] = message_queue
        
        try:
            # РћС‚РїСЂР°РІР»СЏРµРј endpoint РґР»СЏ СЃРѕРѕР±С‰РµРЅРёР№ (РєР°Рє РїРµСЂРІС‹Р№ СЃРµСЂРІРµСЂ)
            yield f"event: endpoint\n"
            yield f"data: /mcp?session_id={session_id}\n\n"
            
            # Р”РµСЂР¶РёРј СЃРѕРµРґРёРЅРµРЅРёРµ РѕС‚РєСЂС‹С‚С‹Рј Рё РѕС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёСЏ РёР· РѕС‡РµСЂРµРґРё
            while True:
                try:
                    # Р–РґРµРј СЃРѕРѕР±С‰РµРЅРёРµ РёР· РѕС‡РµСЂРµРґРё СЃ С‚Р°Р№РјР°СѓС‚РѕРј
                    message = await asyncio.wait_for(message_queue.get(), timeout=30.0)
                    
                    # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ С‡РµСЂРµР· SSE
                    yield f"event: message\n"
                    yield f"data: {json.dumps(message)}\n\n"
                    
                except asyncio.TimeoutError:
                    # РћС‚РїСЂР°РІР»СЏРµРј ping РєР°Р¶РґС‹Рµ 30 СЃРµРєСѓРЅРґ РїСЂРё РѕС‚СЃСѓС‚СЃС‚РІРёРё СЃРѕРѕР±С‰РµРЅРёР№
                    yield f"event: ping\n"
                    yield f"data: {json.dumps({'timestamp': int(time.time())})}\n\n"
                    
        except asyncio.CancelledError:
            logger.info(f"SSE СЃРѕРµРґРёРЅРµРЅРёРµ Р·Р°РєСЂС‹С‚Рѕ РґР»СЏ session {session_id}")
            # РЈРґР°Р»СЏРµРј СЃРµСЃСЃРёСЋ РёР· С…СЂР°РЅРёР»РёС‰Р°
            if hasattr(app.state, 'sse_sessions') and session_id in app.state.sse_sessions:
                del app.state.sse_sessions[session_id]
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


@app.post("/mcp")
async def mcp_sse_or_jsonrpc_endpoint(request: Request):
    """Endpoint РґР»СЏ РѕР±СЂР°Р±РѕС‚РєРё СЃРѕРѕР±С‰РµРЅРёР№ - РїРѕРґРґРµСЂР¶РёРІР°РµС‚ SSE Рё РѕР±С‹С‡РЅС‹Р№ JSON-RPC."""
    import json
    from fastapi.responses import JSONResponse
    
    try:
        # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё session_id (SSE СЂРµР¶РёРј)
        session_id = request.query_params.get("session_id")
        
        # Р§РёС‚Р°РµРј JSON-RPC Р·Р°РїСЂРѕСЃ
        data = await request.json()
        logger.info(f"РџРѕР»СѓС‡РµРЅ Р·Р°РїСЂРѕСЃ{' РґР»СЏ session ' + session_id if session_id else ''}: {data.get('method', 'unknown') if isinstance(data, dict) else 'batch'}")
        
        # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј Р·Р°РїСЂРѕСЃ
        if isinstance(data, list):
            results = []
            for item in data:
                result = await process_single_jsonrpc_request(item)
                results.append(result)
            response_data = results
        else:
            response_data = await process_single_jsonrpc_request(data)
        
        # Р•СЃР»Рё СЌС‚Рѕ SSE Р·Р°РїСЂРѕСЃ, РѕС‚РїСЂР°РІР»СЏРµРј РѕС‚РІРµС‚ С‡РµСЂРµР· РѕС‡РµСЂРµРґСЊ
        if session_id and hasattr(app.state, 'sse_sessions') and session_id in app.state.sse_sessions:
            queue = app.state.sse_sessions[session_id]
            await queue.put(response_data)
            # Р’РѕР·РІСЂР°С‰Р°РµРј РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ РїСЂРёРµРјР°
            return JSONResponse(content={"status": "queued"})
        else:
            # РћР±С‹С‡РЅС‹Р№ JSON-RPC РѕС‚РІРµС‚
            return JSONResponse(content=response_data)
            
    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё Р·Р°РїСЂРѕСЃР°: {e}")
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
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РѕРґРёРЅРѕС‡РЅС‹Р№ JSON-RPC Р·Р°РїСЂРѕСЃ (РїРµСЂРµРёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РґР»СЏ SSE Рё POST)."""
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": data.get("id") if isinstance(data, dict) else None,
            "error": {"code": -32600, "message": "Invalid Request"}
        }

    method = data.get("method")
    params = data.get("params", {})
    request_id = data.get("id")
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј initialize Р·Р°РїСЂРѕСЃ
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {
                        "listChanged": False
                    },
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
    
    # Обрабатываем tools/list запрос
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
    
    # Обрабатываем tools/call запрос
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        from src.models.mcp_models import MCPRequest
        mcp_request = MCPRequest(tool=tool_name, arguments=arguments)
        result = await mcp_endpoint_handler(mcp_request)

        # Преобразуем MCPResponse в JSON-сериализуемый формат
        if hasattr(result, 'model_dump'):
            # Pydantic v2
            result_dict = result.model_dump()
        elif hasattr(result, 'dict'):
            # Pydantic v1
            result_dict = result.dict()
        else:
            result_dict = result if isinstance(result, dict) else {"content": [], "error": str(result)}

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": result_dict.get("content", []),
                "isError": bool(result_dict.get("error"))
            }
        }
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј РґСЂСѓРіРёРµ СЃС‚Р°РЅРґР°СЂС‚РЅС‹Рµ РјРµС‚РѕРґС‹ MCP
    elif method in ["prompts/list", "prompts/get", "resources/list", "resources/read", "roots/list"]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {} if method == "prompts/list" else {"error": "Not implemented"}
        }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


async def mcp_endpoint_handler(request: MCPRequest):
    """Р’РЅСѓС‚СЂРµРЅРЅРёР№ РѕР±СЂР°Р±РѕС‚С‡РёРє MCP Р·Р°РїСЂРѕСЃРѕРІ."""
    logger.info(f"РџРѕР»СѓС‡РµРЅ MCP Р·Р°РїСЂРѕСЃ: {request.tool}")
    
    try:
        # РџСЂРѕРІРµСЂСЏРµРј РїРѕРґРєР»СЋС‡РµРЅРёРµ Рє Elasticsearch
        if not await es_client.is_connected():
            raise HTTPException(
                status_code=503, 
                detail="Elasticsearch РЅРµРґРѕСЃС‚СѓРїРµРЅ"
            )
        
        # РњР°СЂС€СЂСѓС‚РёР·РёСЂСѓРµРј Р·Р°РїСЂРѕСЃ Рє РЅРѕРІС‹Рј РѕР±СЂР°Р±РѕС‚С‡РёРєР°Рј
        if request.tool == MCPToolType.FIND_1C_HELP:
            return await handle_find_1c_help(Find1CHelpRequest(**request.arguments))
        elif request.tool == MCPToolType.GET_SYNTAX_INFO:
            return await handle_get_syntax_info(GetSyntaxInfoRequest(**request.arguments))
        elif request.tool == MCPToolType.GET_QUICK_REFERENCE:
            return await handle_get_quick_reference(GetQuickReferenceRequest(**request.arguments))
        elif request.tool == MCPToolType.SEARCH_BY_CONTEXT:
            return await handle_search_by_context(SearchByContextRequest(**request.arguments))
        elif request.tool == MCPToolType.LIST_OBJECT_MEMBERS:
            return await handle_list_object_members(ListObjectMembersRequest(**request.arguments))
        else:
            return {"content": [], "error": f"РќРµРёР·РІРµСЃС‚РЅС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚: {request.tool}"}

    except Exception as e:
        logger.error(f"РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё MCP Р·Р°РїСЂРѕСЃР°: {e}")
        return {"content": [], "error": str(e)}
@app.websocket("/mcp/ws")
async def mcp_websocket_endpoint(websocket: WebSocket):
    """MCP WebSocket endpoint РґР»СЏ РѕР±СЂР°Р±РѕС‚РєРё MCP РїСЂРѕС‚РѕРєРѕР»Р° С‡РµСЂРµР· WebSocket."""
    logger.info("WebSocket connection initiated")
    
    await websocket.accept()
    
    try:
        # РћС‚РїСЂР°РІР»СЏРµРј РЅР°С‡Р°Р»СЊРЅРѕРµ СЃРѕР±С‹С‚РёРµ РїРѕРґРєР»СЋС‡РµРЅРёСЏ
        await websocket.send_json({
            "type": "connection", 
            "status": "connected",
            "timestamp": int(time.time())
        })
        
        while True:
            try:
                # РџРѕР»СѓС‡Р°РµРј СЃРѕРѕР±С‰РµРЅРёРµ РѕС‚ РєР»РёРµРЅС‚Р°
                message = await websocket.receive_json()
                logger.info(f"РџРѕР»СѓС‡РµРЅРѕ WebSocket СЃРѕРѕР±С‰РµРЅРёРµ: {json.dumps(message, ensure_ascii=False)}")
                
                # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј JSON-RPC Р·Р°РїСЂРѕСЃ
                response = await process_jsonrpc_message(message)
                
                # РћС‚РїСЂР°РІР»СЏРµРј РѕС‚РІРµС‚
                await websocket.send_json(response)
                
            except WebSocketDisconnect:
                logger.info("WebSocket РєР»РёРµРЅС‚ РѕС‚РєР»СЋС‡РёР»СЃСЏ")
                break
            except json.JSONDecodeError:
                # РћС‚РїСЂР°РІР»СЏРµРј РѕС€РёР±РєСѓ РїР°СЂСЃРёРЅРіР° JSON
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                }
                await websocket.send_json(error_response)
            except Exception as e:
                logger.error(f"РћС€РёР±РєР° РІ WebSocket РѕР±СЂР°Р±РѕС‚С‡РёРєРµ: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id") if isinstance(message, dict) else None,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
                }
                await websocket.send_json(error_response)
                
    except Exception as e:
        logger.error(f"РљСЂРёС‚РёС‡РµСЃРєР°СЏ РѕС€РёР±РєР° WebSocket СЃРѕРµРґРёРЅРµРЅРёСЏ: {e}")
    finally:
        logger.info("WebSocket СЃРѕРµРґРёРЅРµРЅРёРµ Р·Р°РєСЂС‹С‚Рѕ")


async def process_jsonrpc_message(data):
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ JSON-RPC СЃРѕРѕР±С‰РµРЅРёРµ (РїРµСЂРµРёСЃРїРѕР»СЊР·СѓРµС‚ Р»РѕРіРёРєСѓ РёР· HTTP endpoint)."""
    # РџРѕРґРґРµСЂР¶РєР° batch Р·Р°РїСЂРѕСЃРѕРІ JSON-RPC
    if isinstance(data, list):
        # РџСѓСЃС‚РѕР№ РјР°СЃСЃРёРІ вЂ” РЅРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ JSON-RPC Р·Р°РїСЂРѕСЃ
        if len(data) == 0:
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}
            }
        
        results = []
        for item in data:
            result = await process_single_jsonrpc_message(item)
            results.append(result)
        return results
    else:
        # РћР±С‹С‡РЅС‹Р№ РѕРґРёРЅРѕС‡РЅС‹Р№ Р·Р°РїСЂРѕСЃ
        return await process_single_jsonrpc_message(data)


async def process_single_jsonrpc_message(data):
    """РћР±СЂР°Р±Р°С‚С‹РІР°РµС‚ РѕРґРёРЅРѕС‡РЅРѕРµ JSON-RPC СЃРѕРѕР±С‰РµРЅРёРµ."""
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": data.get("id") if isinstance(data, dict) else None,
            "error": {"code": -32600, "message": "Invalid Request"}
        }

    method = data.get("method")
    params = data.get("params", {})
    request_id = data.get("id")
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј initialize Р·Р°РїСЂРѕСЃ
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {
                        "listChanged": False
                    },
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
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј tools/list Р·Р°РїСЂРѕСЃ
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
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј prompts/list Р·Р°РїСЂРѕСЃ
    elif method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "prompts": []
            }
        }
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј prompts/get Р·Р°РїСЂРѕСЃ
    elif method == "prompts/get":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Prompt not found"}
        }
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј notifications/initialized
    elif method == "notifications/initialized":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {}
        }
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј resources/list
    elif method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"resources": []}
        }
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј resources/read
    elif method == "resources/read":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32004, "message": "Resource not found"}
        }
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј roots/list
    elif method == "roots/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"roots": []}
        }
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј sampling/create
    elif method == "sampling/create":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Sampling not supported"}
        }
    
    # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј sampling/complete
    elif method == "sampling/complete":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Sampling not supported"}
        }
    
    # Обрабатываем tools/call запрос
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        # Преобразуем в наш формат MCPRequest
        from src.models.mcp_models import MCPRequest
        mcp_request = MCPRequest(tool=tool_name, arguments=arguments)

        # Вызываем наш существующий обработчик
        result = await mcp_endpoint_handler(mcp_request)

        # Преобразуем MCPResponse в JSON-сериализуемый формат
        if hasattr(result, 'model_dump'):
            # Pydantic v2
            result_dict = result.model_dump()
        elif hasattr(result, 'dict'):
            # Pydantic v1
            result_dict = result.dict()
        else:
            result_dict = result if isinstance(result, dict) else {"content": [], "error": str(result)}

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": result_dict.get("content", []),
                "isError": bool(result_dict.get("error"))
            }
        }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


@app.get("/metrics")
async def get_metrics(request: Request, format: Optional[str] = None):
    """
    Получение метрик системы.

    Args:
        format: Формат вывода ('json' или 'prometheus'). По умолчанию определяется по Accept заголовку.
    """
    metrics = get_metrics_collector()
    rate_limiter = get_rate_limiter()

    # Определяем формат по Accept заголовку или параметру
    accept_header = request.headers.get("accept", "")
    use_prometheus = format == "prometheus" or "text/plain" in accept_header or "prometheus" in accept_header

    if use_prometheus:
        # Prometheus format
        prometheus_metrics = metrics.get_prometheus_format()
        return Response(content=prometheus_metrics, media_type="text/plain")
    else:
        # JSON format
        all_metrics = await metrics.get_all_metrics()
        performance_stats = metrics.performance_stats
        global_rate_stats = rate_limiter.get_global_stats()

        return {
            "metrics": all_metrics,
            "performance": {
                "total_requests": performance_stats.total_requests,
                "successful_requests": performance_stats.successful_requests,
                "failed_requests": performance_stats.failed_requests,
                "success_rate": (performance_stats.successful_requests / max(performance_stats.total_requests, 1)) * 100,
                "avg_response_time": performance_stats.avg_response_time,
                "max_response_time": performance_stats.max_response_time,
                "min_response_time": performance_stats.min_response_time if performance_stats.min_response_time != float('inf') else 0,
                "current_active_requests": performance_stats.current_active_requests
            },
            "rate_limiting": global_rate_stats
        }


@app.get("/metrics/{client_id}")
async def get_client_metrics(client_id: str):
    """РџРѕР»СѓС‡РµРЅРёРµ РјРµС‚СЂРёРє РґР»СЏ РєРѕРЅРєСЂРµС‚РЅРѕРіРѕ РєР»РёРµРЅС‚Р°."""
    rate_limiter = get_rate_limiter()
    client_stats = rate_limiter.get_client_stats(client_id)
    
    return {
        "client_id": client_id,
        "rate_limiting": client_stats
    }


@app.get("/sse")
async def sse_endpoint():
    """SSE endpoint for MCP clients (Qwen Code, etc.)."""
    return await mcp_sse_endpoint()

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host=settings.server.host,
        port=settings.server.port,
        log_level=settings.server.log_level.lower(),
        reload=settings.debug
    )


