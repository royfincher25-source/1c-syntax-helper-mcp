"""Модуль обработки исключений приложения."""

from typing import Optional, Callable, Awaitable, Any, Dict, Type
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.logging import get_logger
from src.core.validation import ValidationError
from src.parsers.hbk_parser import HBKParserError

logger = get_logger(__name__)


class ExceptionHandler:
    """
    Базовый класс для обработчиков исключений.

    Предоставляет:
    - Стандартизированное логирование
    - Форматирование ответов
    - Метрики ошибок
    """

    @staticmethod
    async def handle(
        request: Request,
        exc: Exception,
        status_code: int,
        error_type: str,
        message: str,
        log_level: str = "error"
    ) -> JSONResponse:
        """
        Базовый метод обработки исключения.

        Args:
            request: HTTP запрос
            exc: Исключение
            status_code: HTTP статус код
            error_type: Тип ошибки
            message: Сообщение
            log_level: Уровень логирования

        Returns:
            JSONResponse с информацией об ошибке
        """
        # Логируем
        if log_level == "error":
            logger.error(f"{error_type}: {exc}", exc_info=True)
        elif log_level == "warning":
            logger.warning(f"{error_type}: {exc}")
        else:
            logger.info(f"{error_type}: {exc}")

        # Получаем метрики
        try:
            from src.core._metrics import get_metrics_collector
            metrics = get_metrics_collector()
            await metrics.increment(f"errors.{error_type.lower()}")
        except Exception:
            pass  # Игнорируем ошибки метрик

        return JSONResponse(
            status_code=status_code,
            content={
                "error": error_type,
                "message": message,
                "path": str(request.url.path)
            }
        )


class ValidationErrorHandler(ExceptionHandler):
    """Обработчик ошибок валидации."""

    @staticmethod
    async def handle(request: Request, exc: ValidationError) -> JSONResponse:
        """
        Обрабатывает ValidationError.

        Args:
            request: HTTP запрос
            exc: ValidationError

        Returns:
            JSONResponse с ошибкой валидации
        """
        return await ExceptionHandler.handle(
            request=request,
            exc=exc,
            status_code=400,
            error_type="Validation error",
            message=str(exc),
            log_level="warning"
        )


class ParserErrorHandler(ExceptionHandler):
    """Обработчик ошибок парсера."""

    @staticmethod
    async def handle(request: Request, exc: HBKParserError) -> JSONResponse:
        """
        Обрабатывает HBKParserError.

        Args:
            request: HTTP запрос
            exc: HBKParserError

        Returns:
            JSONResponse с ошибкой парсера
        """
        return await ExceptionHandler.handle(
            request=request,
            exc=exc,
            status_code=500,
            error_type="Parser error",
            message=str(exc),
            log_level="error"
        )


class GeneralErrorHandler(ExceptionHandler):
    """Обработчик общих исключений."""

    @staticmethod
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        """
        Обрабатывает необработанные исключения.

        Args:
            request: HTTP запрос
            exc: Исключение

        Returns:
            JSONResponse с общей ошибкой
        """
        return await ExceptionHandler.handle(
            request=request,
            exc=exc,
            status_code=500,
            error_type="Internal server error",
            message="An unexpected error occurred",
            log_level="error"
        )


class HTTPExceptionHandler(ExceptionHandler):
    """Обработчик HTTP исключений."""

    @staticmethod
    async def handle(
        request: Request,
        exc: StarletteHTTPException
    ) -> JSONResponse:
        """
        Обрабатывает StarletteHTTPException.

        Args:
            request: HTTP запрос
            exc: StarletteHTTPException

        Returns:
            JSONResponse с HTTP ошибкой
        """
        # Логируем только 5xx ошибки
        log_level = "error" if exc.status_code >= 500 else "info"
        
        logger.log(
            level=log_level,
            msg=f"HTTPException {exc.status_code} at {request.url}: {exc.detail}"
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.status_code,
                    "message": str(exc.detail) if exc.detail else "HTTP error"
                },
                "path": str(request.url.path)
            }
        )


class ExceptionHandlerRegistry:
    """
    Реестр обработчиков исключений.

    Позволяет регистрировать и получать обработчики для разных типов исключений.
    """

    def __init__(self):
        self._handlers: Dict[Type[Exception], Callable[[Request, Exception], Awaitable[JSONResponse]]] = {}

    def register(
        self,
        exc_type: Type[Exception],
        handler: Callable[[Request, Exception], Awaitable[JSONResponse]]
    ) -> None:
        """
        Зарегистрировать обработчик для типа исключения.

        Args:
            exc_type: Тип исключения
            handler: Функция обработчика
        """
        self._handlers[exc_type] = handler
        logger.debug(f"Зарегистрирован обработчик для {exc_type.__name__}")

    def get(
        self,
        exc_type: Type[Exception]
    ) -> Optional[Callable[[Request, Exception], Awaitable[JSONResponse]]]:
        """
        Получить обработчик для типа исключения.

        Args:
            exc_type: Тип исключения

        Returns:
            Функция обработчика или None
        """
        return self._handlers.get(exc_type)

    def get_all_handlers(self) -> Dict[Type[Exception], Callable]:
        """
        Получить все зарегистрированные обработчики.

        Returns:
            Словарь {тип_исключения: обработчик}
        """
        return self._handlers.copy()


# Глобальный реестр обработчиков
_exception_handler_registry = ExceptionHandlerRegistry()


def get_exception_handler_registry() -> ExceptionHandlerRegistry:
    """
    Получить глобальный реестр обработчиков исключений.

    Returns:
        ExceptionHandlerRegistry
    """
    return _exception_handler_registry


def setup_exception_handlers() -> ExceptionHandlerRegistry:
    """
    Настроить обработчики исключений по умолчанию.

    Returns:
        Настроенный ExceptionHandlerRegistry
    """
    registry = get_exception_handler_registry()

    # Регистрируем обработчики по умолчанию
    registry.register(ValidationError, ValidationErrorHandler.handle)
    registry.register(HBKParserError, ParserErrorHandler.handle)
    registry.register(Exception, GeneralErrorHandler.handle)
    registry.register(StarletteHTTPException, HTTPExceptionHandler.handle)

    logger.info("Обработчики исключений настроены")

    return registry


def reset_exception_handlers() -> None:
    """Сбросить реестр обработчиков (для тестов)."""
    global _exception_handler_registry
    _exception_handler_registry = ExceptionHandlerRegistry()


# Функции-обертки для совместимости с FastAPI exception handlers

async def validation_exception_handler(
    request: Request,
    exc: ValidationError
) -> JSONResponse:
    """Обработчик ValidationError для FastAPI."""
    return await ValidationErrorHandler.handle(request, exc)


async def parser_exception_handler(
    request: Request,
    exc: HBKParserError
) -> JSONResponse:
    """Обработчик HBKParserError для FastAPI."""
    return await ParserErrorHandler.handle(request, exc)


async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """Обработчик Exception для FastAPI."""
    return await GeneralErrorHandler.handle(request, exc)


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException
) -> JSONResponse:
    """Обработчик StarletteHTTPException для FastAPI."""
    return await HTTPExceptionHandler.handle(request, exc)
