"""Модуль маршрутов приложения."""

from src.routes.health_routes import router as health_router
from src.routes.admin_routes import router as admin_router
from src.routes.mcp_routes import router as mcp_router
from src.routes.sse_router import router as sse_router

__all__ = ["health_router", "admin_router", "mcp_router", "sse_router"]
