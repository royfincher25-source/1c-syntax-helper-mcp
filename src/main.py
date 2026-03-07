"""Р“Р»Р°РІРЅРѕРµ РїСЂРёР»РѕР¶РµРЅРёРµ MCP СЃРµСЂРІРµСЂР° СЃРёРЅС‚Р°РєСЃРёСЃ-РїРѕРјРѕС‰РЅРёРєР° 1РЎ."""

from typing import Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from src.core.config import settings
from src.core.logging import get_logger
from src.core.rate_limiter import get_rate_limiter
from src.core.metrics.collector import get_metrics_collector
from src.core.lifespan import get_lifespan_manager
from src.core.exception_handlers import setup_exception_handlers

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
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8002"],
    allow_origin_regex=r"https://.*\.yourdomain\.com",
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
from src.routes import health_router, admin_router, mcp_router, sse_router

app.include_router(health_router)
app.include_router(admin_router)
app.include_router(mcp_router)
app.include_router(sse_router)


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


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host=settings.server.host,
        port=settings.server.port,
        log_level=settings.server.log_level.lower(),
        reload=settings.debug
    )


