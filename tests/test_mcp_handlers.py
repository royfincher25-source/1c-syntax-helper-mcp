"""Integration тесты для MCP handlers."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.handlers.mcp_handlers import (
    handle_find_1c_help,
    handle_get_syntax_info,
    handle_get_quick_reference,
    handle_search_by_context,
    handle_list_object_members
)
from src.models.mcp_models import (
    Find1CHelpRequest,
    GetSyntaxInfoRequest,
    GetQuickReferenceRequest,
    SearchByContextRequest,
    ListObjectMembersRequest
)


class TestHandleFind1CHelp:
    """Тесты handle_find_1c_help."""

    @pytest.mark.asyncio
    async def test_find_global_function(self):
        """Поиск глобальной функции."""
        request = Find1CHelpRequest(query="СтрДлина")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.find_help_by_query = AsyncMock(return_value={
                "results": [
                    {
                        "type": "global_function",
                        "name": "СтрДлина",
                        "description": "Возвращает количество символов"
                    }
                ],
                "total": 1,
                "search_time_ms": 50
            })
            
            result = await handle_find_1c_help(request)
            
            assert "content" in result
            assert "СтрДлина" in str(result)

    @pytest.mark.asyncio
    async def test_find_object_method(self):
        """Поиск метода объекта."""
        request = Find1CHelpRequest(query="ТаблицаЗначений.Добавить")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.find_help_by_query = AsyncMock(return_value={
                "results": [
                    {
                        "type": "object_method",
                        "object": "ТаблицаЗначений",
                        "name": "Добавить",
                        "description": "Добавляет строку"
                    }
                ],
                "total": 1
            })
            
            result = await handle_find_1c_help(request)
            
            assert "content" in result
            assert "ТаблицаЗначений" in str(result)

    @pytest.mark.asyncio
    async def test_find_no_results(self):
        """Поиск без результатов."""
        request = Find1CHelpRequest(query="НесуществующаяФункция")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.find_help_by_query = AsyncMock(return_value={
                "results": [],
                "total": 0,
                "error": "Не найдено"
            })
            
            result = await handle_find_1c_help(request)
            
            assert "content" in result
            assert "не найдено" in str(result).lower() or "0" in str(result)


class TestHandleGetSyntaxInfo:
    """Тесты handle_get_syntax_info."""

    @pytest.mark.asyncio
    async def test_get_function_details(self):
        """Получение детальной информации о функции."""
        request = GetSyntaxInfoRequest(element_name="СтрДлина")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.get_detailed_syntax_info = AsyncMock(return_value={
                "name": "СтрДлина",
                "syntax_ru": "СтрДлина(Строка)",
                "syntax_en": "StrLen(String)",
                "description": "Возвращает количество символов",
                "parameters": [
                    {
                        "name": "Строка",
                        "type": "Строка",
                        "description": "Строка"
                    }
                ],
                "return_type": "Число",
                "examples": ["Длина = СтрДлина(\"Тест\");"]
            })
            
            result = await handle_get_syntax_info(request)
            
            assert "content" in result
            assert "СтрДлина" in str(result)
            assert "syntax_ru" in str(result)

    @pytest.mark.asyncio
    async def test_get_method_details(self):
        """Получение детальной информации о методе."""
        request = GetSyntaxInfoRequest(
            element_name="Добавить",
            object_name="ТаблицаЗначений"
        )
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.get_detailed_syntax_info = AsyncMock(return_value={
                "name": "Добавить",
                "object": "ТаблицаЗначений",
                "syntax_ru": "Добавить()",
                "description": "Добавляет строку"
            })
            
            result = await handle_get_syntax_info(request)
            
            assert "content" in result
            assert "ТаблицаЗначений" in str(result)

    @pytest.mark.asyncio
    async def test_get_syntax_info_not_found(self):
        """Получение информации о несуществующем элементе."""
        request = GetSyntaxInfoRequest(element_name="НесуществующаяФункция")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.get_detailed_syntax_info = AsyncMock(return_value=None)
            
            result = await handle_get_syntax_info(request)
            
            assert "content" in result
            assert "не найдено" in str(result).lower() or "not found" in str(result).lower()


class TestHandleGetQuickReference:
    """Тесты handle_get_quick_reference."""

    @pytest.mark.asyncio
    async def test_get_quick_reference(self):
        """Получение краткой справки."""
        request = GetQuickReferenceRequest(element_name="СтрДлина")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.get_detailed_syntax_info = AsyncMock(return_value={
                "name": "СтрДлина",
                "syntax_ru": "СтрДлина(Строка)",
                "description": "Возвращает количество символов"
            })
            
            result = await handle_get_quick_reference(request)
            
            assert "content" in result
            assert "СтрДлина" in str(result)


class TestHandleSearchByContext:
    """Тесты handle_search_by_context."""

    @pytest.mark.asyncio
    async def test_search_global(self):
        """Поиск в глобальном контексте."""
        request = SearchByContextRequest(
            query="Стр",
            context="global"
        )
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.search_with_context_filter = AsyncMock(return_value={
                "results": [
                    {"name": "СтрДлина", "type": "global_function"},
                    {"name": "СтрЗаменить", "type": "global_function"}
                ],
                "total": 2
            })
            
            result = await handle_search_by_context(request)
            
            assert "content" in result
            assert len(result["content"]) > 0

    @pytest.mark.asyncio
    async def test_search_object(self):
        """Поиск в контексте объекта."""
        request = SearchByContextRequest(
            query="Добавить",
            context="object",
            object_name="ТаблицаЗначений"
        )
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.search_with_context_filter = AsyncMock(return_value={
                "results": [
                    {"name": "Добавить", "type": "object_method"}
                ],
                "total": 1
            })
            
            result = await handle_search_by_context(request)
            
            assert "content" in result


class TestHandleListObjectMembers:
    """Тесты handle_list_object_members."""

    @pytest.mark.asyncio
    async def test_list_all_members(self):
        """Получение всех элементов объекта."""
        request = ListObjectMembersRequest(object_name="ТаблицаЗначений")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.get_object_members_list = AsyncMock(return_value={
                "object": "ТаблицаЗначений",
                "methods": [
                    {"name": "Добавить"},
                    {"name": "Удалить"}
                ],
                "properties": [
                    {"name": "Колонки"}
                ],
                "events": [],
                "total": 3
            })
            
            result = await handle_list_object_members(request)
            
            assert "content" in result
            assert "ТаблицаЗначений" in str(result)
            assert "Добавить" in str(result)

    @pytest.mark.asyncio
    async def test_list_methods_only(self):
        """Получение только методов."""
        request = ListObjectMembersRequest(
            object_name="ТаблицаЗначений",
            member_type="methods"
        )
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.get_object_members_list = AsyncMock(return_value={
                "object": "ТаблицаЗначений",
                "methods": [{"name": "Добавить"}],
                "properties": [],
                "events": [],
                "total": 1
            })
            
            result = await handle_list_object_members(request)
            
            assert "content" in result
            assert "methods" in str(result).lower()

    @pytest.mark.asyncio
    async def test_list_properties(self):
        """Получение только свойств."""
        request = ListObjectMembersRequest(
            object_name="ТаблицаЗначений",
            member_type="properties"
        )
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.get_object_members_list = AsyncMock(return_value={
                "object": "ТаблицаЗначений",
                "methods": [],
                "properties": [{"name": "Колонки"}],
                "events": [],
                "total": 1
            })
            
            result = await handle_list_object_members(request)
            
            assert "content" in result
            assert "Колонки" in str(result)


class TestErrorHandling:
    """Тесты обработки ошибок в MCP handlers."""

    @pytest.mark.asyncio
    async def test_handle_exception(self):
        """Обработка исключений."""
        request = Find1CHelpRequest(query="Тест")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.find_help_by_query = AsyncMock(
                side_effect=Exception("Test error")
            )
            
            result = await handle_find_1c_help(request)
            
            assert "content" in result
            assert "error" in str(result).lower() or "ошибка" in str(result).lower()


class TestMCPResponseFormat:
    """Тесты формата MCP ответов."""

    @pytest.mark.asyncio
    async def test_response_has_content(self):
        """Проверка что ответ содержит content."""
        request = Find1CHelpRequest(query="Тест")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.find_help_by_query = AsyncMock(return_value={
                "results": [{"name": "Тест"}],
                "total": 1
            })
            
            result = await handle_find_1c_help(request)
            
            assert "content" in result
            assert isinstance(result["content"], list)

    @pytest.mark.asyncio
    async def test_response_content_type(self):
        """Проверка типа content."""
        request = Find1CHelpRequest(query="Тест")
        
        with patch('src.handlers.mcp_handlers.search_service') as mock_search:
            mock_search.find_help_by_query = AsyncMock(return_value={
                "results": [{"name": "Тест"}],
                "total": 1
            })
            
            result = await handle_find_1c_help(request)
            
            # Content должен быть списком
            assert isinstance(result["content"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
