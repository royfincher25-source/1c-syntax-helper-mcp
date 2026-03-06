"""Middleware для Gzip компрессии ответов."""

import gzip
import io
from typing import List
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse

from src.core.logging import get_logger

logger = get_logger(__name__)


class GzipMiddleware(BaseHTTPMiddleware):
    """
    Middleware для автоматической Gzip компрессии ответов.
    
    Особенности:
    - Сжатие ответов больше min_size
    - Пропуск уже сжатых типов (images, video)
    - Добавление заголовка Content-Encoding: gzip
    - Сохранение оригинальных заголовков
    """

    def __init__(
        self,
        app,
        min_size: int = 1024,  # 1KB
        compress_level: int = 6,
        exclude_content_types: List[str] = None
    ):
        """
        Инициализирует Gzip middleware.
        
        Args:
            app: FastAPI приложение
            min_size: Минимальный размер ответа для сжатия (в байтах)
            compress_level: Уровень сжатия (1-9, где 9 - максимальное)
            exclude_content_types: Список типов контента для исключения из сжатия
        """
        super().__init__(app)
        self.min_size = min_size
        self.compress_level = compress_level
        self.exclude_content_types = exclude_content_types or [
            "image/",
            "video/",
            "audio/",
            "application/pdf",
            "application/zip",
            "application/x-tar",
        ]

    async def dispatch(self, request: Request, call_next):
        """Обрабатывает запрос, сжимая ответ если необходимо."""
        # Получаем ответ
        response = await call_next(request)
        
        # Проверяем необходимость сжатия
        if not self._should_compress(response):
            return response
        
        # Для StreamingResponse сжатие не применяем
        if isinstance(response, StreamingResponse):
            return response
        
        # Читаем тело ответа
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        
        # Проверяем размер после получения тела
        if len(body) < self.min_size:
            # Возвращаем оригинальный ответ
            return Response(
                body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        
        # Сжимаем тело
        compressed_body = gzip.compress(body, compresslevel=self.compress_level)
        
        # Проверяем эффективность сжатия
        if len(compressed_body) >= len(body):
            # Сжатие неэффективно, возвращаем оригинал
            return Response(
                body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        
        # Создаём новый ответ со сжатым телом
        new_response = Response(
            compressed_body,
            status_code=response.status_code,
            media_type=response.media_type,
        )

        # Копируем заголовки кроме content-length
        for name, value in response.headers.items():
            if name.lower() != "content-length":
                new_response.headers[name] = value

        # Добавляем заголовок сжатия
        new_response.headers["Content-Encoding"] = "gzip"
        new_response.headers["Content-Length"] = str(len(compressed_body))
        
        # Логируем
        compression_ratio = (1 - len(compressed_body) / len(body)) * 100
        logger.debug(
            f"Gzip сжатие: {request.method} {request.url.path}",
            extra={
                "extra_data": {
                    "original_size": len(body),
                    "compressed_size": len(compressed_body),
                    "compression_ratio_percent": round(compression_ratio, 2),
                }
            }
        )
        
        return new_response

    def _should_compress(self, response: Response) -> bool:
        """Проверяет, нужно ли сжимать ответ."""
        # Не сжимаем ошибки
        if response.status_code >= 400:
            return False
        
        # Проверяем тип контента
        content_type = response.headers.get("content-type", "")
        
        for exclude_type in self.exclude_content_types:
            if exclude_type in content_type:
                return False
        
        return True
