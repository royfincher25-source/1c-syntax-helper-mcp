"""Integration тесты для MCP Handlers."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.handlers.mcp_handler import MCPHandler
from src.handlers.mcp_formatter import MCPResponseFormatter
from src.models.mcp_models import MCPRequest


class TestMCPHandlerIntegration:
    """Интеграционные тесты MCPHandler."""
    
    @pytest.fixture
    def formatter(self):
        """Фикстура для форматтера."""
        return MCPResponseFormatter()
    
    @pytest.fixture
    def mock_search_service(self):
        """Мок для SearchService."""
        mock = Mock()
        mock.search_1c_syntax = AsyncMock(return_value={
            "results": [
                {
                    "name": "СтрДлина",
                    "object": "Global context",
                    "description": "Получает длину строки"
                }
            ],
            "total": 1,
            "search_time_ms": 50
        })
        mock.get_detailed_syntax_info = AsyncMock(return_value={
            "name": "СтрДлина",
            "syntax_ru": "СтрДлина(Строка)",
            "description": "Получает длину строки",
            "parameters": [{"name": "Строка", "type": "Строка", "required": True}],
            "return_type": "Число"
        })
        mock.get_object_members_list = AsyncMock(return_value={
            "object": "ТаблицаЗначений",
            "methods": [{"name": "Добавить"}, {"name": "Количество"}],
            "properties": [],
            "events": []
        })
        return mock
    
    @pytest.mark.asyncio
    async def test_handle_search_request(self, mock_search_service, formatter):
        """Тест обработки запроса поиска."""
        handler = MCPHandler(
            search_service=mock_search_service,
            formatter=formatter
        )
        
        request = MCPRequest(
            method="search",
            params={"query": "СтрДлина", "limit": 5}
        )
        
        result = await handler.handle_request(request)
        
        assert result is not None
        assert "content" in result or "error" in result
    
    @pytest.mark.asyncio
    async def test_handle_syntax_request(self, mock_search_service, formatter):
        """Тест обработки запроса синтаксиса."""
        handler = MCPHandler(
            search_service=mock_search_service,
            formatter=formatter
        )
        
        request = MCPRequest(
            method="get_syntax_info",
            params={"element_name": "СтрДлина"}
        )
        
        result = await handler.handle_request(request)
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_handle_members_request(self, mock_search_service, formatter):
        """Тест обработки запроса членов объекта."""
        handler = MCPHandler(
            search_service=mock_search_service,
            formatter=formatter
        )
        
        request = MCPRequest(
            method="get_object_members",
            params={"object_name": "ТаблицаЗначений", "member_type": "methods"}
        )
        
        result = await handler.handle_request(request)
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mock_search_service, formatter):
        """Тест обработки ошибок."""
        mock_search_service.search_1c_syntax = AsyncMock(
            side_effect=Exception("Search failed")
        )
        
        handler = MCPHandler(
            search_service=mock_search_service,
            formatter=formatter
        )
        
        request = MCPRequest(
            method="search",
            params={"query": "тест"}
        )
        
        result = await handler.handle_request(request)
        
        assert result is not None
        assert "error" in result


class TestMCPFormatterIntegration:
    """Интеграционные тесты MCPResponseFormatter."""
    
    @pytest.fixture
    def formatter(self):
        """Фикстура для форматтера."""
        return MCPResponseFormatter()
    
    def test_create_error_response(self, formatter):
        """Тест создания ответа с ошибкой."""
        result = formatter.create_error_response("Test error", "Details")
        
        assert result.error is not None
        assert "Test error" in result.error
    
    def test_create_not_found_response(self, formatter):
        """Тест создания ответа 'не найдено'."""
        result = formatter.create_not_found_response("тест")
        
        assert result.content is not None
        assert len(result.content) > 0
    
    def test_format_search_results(self, formatter):
        """Тест форматирования результатов поиска."""
        results = [
            {"name": "СтрДлина", "object": "Global", "description": "Тест"}
        ]
        
        header = formatter.format_search_header(len(results), "тест")
        
        assert header is not None
        assert "type" in header
    
    def test_format_syntax_info(self, formatter):
        """Тест форматирования синтаксической информации."""
        data = {
            "name": "СтрДлина",
            "syntax_ru": "СтрДлина(Строка)",
            "description": "Получает длину строки",
            "parameters": [{"name": "Строка", "type": "Строка", "required": True}],
            "return_type": "Число"
        }
        
        result = formatter.format_syntax_info(data)
        
        assert "СтрДлина" in result
        assert "Строка" in result
    
    def test_format_quick_reference(self, formatter):
        """Тест форматирования краткой справки."""
        data = {
            "name": "СтрДлина",
            "syntax_ru": "СтрДлина(Строка)",
            "description": "Получает длину строки."
        }
        
        result = formatter.format_quick_reference(data)
        
        assert "КРАТКАЯ СПРАВКА" in result
        assert "СтрДлина" in result
