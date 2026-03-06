"""Middleware для логирования запросов с request_id."""

import time
import uuid
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.logging import LogContext, get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware:
    """Middleware для логирования запросов с request_id и контекстом."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Обрабатывает запрос, добавляя логирование с request_id."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Генерируем request_id
        request_id = str(uuid.uuid4())

        # Устанавливаем контекст логирования
        LogContext.set_request_id(request_id)
        LogContext.set_start_time(time.time())

        # Логируем начало запроса
        logger.info(
            f"Request started: {scope['method']} {scope['path']}",
            extra={
                "extra_data": {
                    "method": scope["method"],
                    "path": scope["path"],
                    "request_id": request_id,
                }
            }
        )

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Добавляем request_id в заголовки
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers

                # Логируем завершение
                elapsed = time.time() - LogContext.get_start_time()
                logger.info(
                    f"Request completed: {scope['method']} {scope['path']} - {message['status']} ({elapsed*1000:.2f}ms)",
                    extra={
                        "extra_data": {
                            "status_code": message["status"],
                            "elapsed_ms": round(elapsed * 1000, 2),
                        }
                    }
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            logger.error(f"Request failed: {scope['method']} {scope['path']} - {e}")
            raise
