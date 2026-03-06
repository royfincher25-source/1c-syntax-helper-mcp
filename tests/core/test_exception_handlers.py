"""Тесты для модуля exception handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exception_handlers import (
    ExceptionHandler,
    ValidationErrorHandler,
    ParserErrorHandler,
    GeneralErrorHandler,
    HTTPExceptionHandler,
    ExceptionHandlerRegistry,
    get_exception_handler_registry,
    setup_exception_handlers,
    reset_exception_handlers,
    validation_exception_handler,
    parser_exception_handler,
    general_exception_handler,
    http_exception_handler
)
from src.core.validation import ValidationError
from src.parsers.hbk_parser import HBKParserError


@pytest.fixture
def mock_request():
    """Создать mock HTTP запроса."""
    request = MagicMock(spec=Request)
    request.url.path = "/test/path"
    return request


@pytest.fixture
def mock_metrics():
    """Mock metrics collector."""
    with patch('src.core.exception_handlers.get_metrics_collector') as mock:
        metrics_instance = MagicMock()
        metrics_instance.increment = AsyncMock()
        mock.return_value = metrics_instance
        yield metrics_instance


class TestExceptionHandler:
    """Тесты для базового ExceptionHandler."""

    @pytest.mark.asyncio
    async def test_handle_basic(self, mock_request, mock_metrics):
        """Тест базовой обработки исключения."""
        exc = Exception("Test error")
        
        response = await ExceptionHandler.handle(
            request=mock_request,
            exc=exc,
            status_code=500,
            error_type="Test error",
            message="Test message"
        )
        
        assert response.status_code == 500
        data = response.body.decode()
        assert "Test error" in data
        assert "Test message" in data

    @pytest.mark.asyncio
    async def test_handle_with_warning_level(self, mock_request):
        """Тест обработки с уровнем логирования warning."""
        exc = Exception("Test error")
        
        response = await ExceptionHandler.handle(
            request=mock_request,
            exc=exc,
            status_code=400,
            error_type="Validation error",
            message="Test message",
            log_level="warning"
        )
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_handle_with_info_level(self, mock_request):
        """Тест обработки с уровнем логирования info."""
        exc = Exception("Test error")
        
        response = await ExceptionHandler.handle(
            request=mock_request,
            exc=exc,
            status_code=200,
            error_type="Info",
            message="Test message",
            log_level="info"
        )
        
        assert response.status_code == 200


class TestValidationErrorHandler:
    """Тесты для ValidationErrorHandler."""

    @pytest.mark.asyncio
    async def test_handle_validation_error(self, mock_request, mock_metrics):
        """Тест обработки ошибки валидации."""
        exc = ValidationError("Field 'name' is required")
        
        response = await ValidationErrorHandler.handle(mock_request, exc)
        
        assert response.status_code == 400
        data = response.body.decode()
        assert "Validation error" in data
        assert "Field 'name' is required" in data
        mock_metrics.increment.assert_called_with("errors.validation error")


class TestParserErrorHandler:
    """Тесты для ParserErrorHandler."""

    @pytest.mark.asyncio
    async def test_handle_parser_error(self, mock_request, mock_metrics):
        """Тест обработки ошибки парсера."""
        exc = HBKParserError("Failed to parse archive")
        
        response = await ParserErrorHandler.handle(mock_request, exc)
        
        assert response.status_code == 500
        data = response.body.decode()
        assert "Parser error" in data
        assert "Failed to parse archive" in data
        mock_metrics.increment.assert_called_with("errors.parser error")


class TestGeneralErrorHandler:
    """Тесты для GeneralErrorHandler."""

    @pytest.mark.asyncio
    async def test_handle_general_error(self, mock_request, mock_metrics):
        """Тест обработки общей ошибки."""
        exc = Exception("Unexpected error")
        
        response = await GeneralErrorHandler.handle(mock_request, exc)
        
        assert response.status_code == 500
        data = response.body.decode()
        assert "Internal server error" in data
        assert "An unexpected error occurred" in data
        mock_metrics.increment.assert_called_with("errors.internal server error")


class TestHTTPExceptionHandler:
    """Тесты для HTTPExceptionHandler."""

    @pytest.mark.asyncio
    async def test_handle_404_error(self, mock_request):
        """Тест обработки 404 ошибки."""
        exc = StarletteHTTPException(status_code=404, detail="Not found")
        
        response = await HTTPExceptionHandler.handle(mock_request, exc)
        
        assert response.status_code == 404
        data = response.body.decode()
        assert "404" in data
        assert "Not found" in data

    @pytest.mark.asyncio
    async def test_handle_500_error(self, mock_request):
        """Тест обработки 500 ошибки."""
        exc = StarletteHTTPException(status_code=500, detail="Internal error")
        
        response = await HTTPExceptionHandler.handle(mock_request, exc)
        
        assert response.status_code == 500
        data = response.body.decode()
        assert "500" in data
        assert "Internal error" in data

    @pytest.mark.asyncio
    async def test_handle_error_without_detail(self, mock_request):
        """Тест обработки ошибки без деталей."""
        exc = StarletteHTTPException(status_code=400, detail=None)
        
        response = await HTTPExceptionHandler.handle(mock_request, exc)
        
        assert response.status_code == 400
        data = response.body.decode()
        assert "400" in data
        assert "HTTP error" in data


class TestExceptionHandlerRegistry:
    """Тесты для ExceptionHandlerRegistry."""

    def setup_method(self):
        """Сброс перед каждым тестом."""
        reset_exception_handlers()

    def teardown_method(self):
        """Сброс после каждого теста."""
        reset_exception_handlers()

    def test_register_handler(self):
        """Тест регистрации обработчика."""
        registry = ExceptionHandlerRegistry()
        handler = AsyncMock()
        
        registry.register(Exception, handler)
        
        assert registry.get(Exception) == handler

    def test_get_unknown_handler(self):
        """Тест получения неизвестного обработчика."""
        registry = ExceptionHandlerRegistry()
        
        result = registry.get(ValueError)
        
        assert result is None

    def test_get_all_handlers(self):
        """Тест получения всех обработчиков."""
        registry = ExceptionHandlerRegistry()
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        
        registry.register(Exception, handler1)
        registry.register(ValueError, handler2)
        
        all_handlers = registry.get_all_handlers()
        
        assert len(all_handlers) == 2
        assert all_handlers[Exception] == handler1
        assert all_handlers[ValueError] == handler2

    def test_setup_exception_handlers(self):
        """Тест настройки обработчиков по умолчанию."""
        registry = setup_exception_handlers()
        
        all_handlers = registry.get_all_handlers()
        
        assert len(all_handlers) >= 4
        assert ValidationError in all_handlers
        assert HBKParserError in all_handlers
        assert Exception in all_handlers
        assert StarletteHTTPException in all_handlers

    def test_reset_exception_handlers(self):
        """Тест сброса обработчиков."""
        setup_exception_handlers()
        reset_exception_handlers()
        
        registry = get_exception_handler_registry()
        all_handlers = registry.get_all_handlers()
        
        assert len(all_handlers) == 0


class TestWrapperFunctions:
    """Тесты для функций-оберток."""

    @pytest.mark.asyncio
    async def test_validation_exception_handler(self, mock_request):
        """Тест обертки для ValidationError."""
        exc = ValidationError("Test")
        
        response = await validation_exception_handler(mock_request, exc)
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_parser_exception_handler(self, mock_request):
        """Тест обертки для HBKParserError."""
        exc = HBKParserError("Test")
        
        response = await parser_exception_handler(mock_request, exc)
        
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_general_exception_handler(self, mock_request):
        """Тест обертки для Exception."""
        exc = Exception("Test")
        
        response = await general_exception_handler(mock_request, exc)
        
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_http_exception_handler(self, mock_request):
        """Тест обертки для StarletteHTTPException."""
        exc = StarletteHTTPException(status_code=404, detail="Test")
        
        response = await http_exception_handler(mock_request, exc)
        
        assert response.status_code == 404
