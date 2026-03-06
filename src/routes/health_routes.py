"""Модуль маршрутов для проверки здоровья."""

from fastapi import APIRouter
from src.core.health import get_health_report, get_basic_health
from src.models.mcp_models import HealthResponse

router = APIRouter(prefix="", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Базовая проверка состояния системы (для совместимости)."""
    return await get_basic_health()


@router.get("/health/detailed")
async def health_check_detailed():
    """
    Детальная проверка состояния системы.
    
    Проверяет:
    - Elasticsearch: состояние подключения
    - Cache: статус кэша
    - Метрики: собранные показатели
    """
    return await get_health_report()


@router.get("/")
async def root():
    """Корневой эндпоинт - перенаправление на health."""
    return {"status": "ok", "message": "1C Syntax Helper MCP Server", "health": "/health"}
