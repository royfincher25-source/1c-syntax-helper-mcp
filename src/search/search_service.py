"""Основной сервис поиска по документации 1С (Facade)."""

from typing import Optional, Dict, Any

from src.core.logging import get_logger
from src.search.cache_service import search_cache_service
from src.search.syntax_info_service import syntax_info_service
from src.search.context_search_service import context_search_service
from src.search.object_members_service import object_members_service

logger = get_logger(__name__)


class SearchService:
    """
    Фасад для поисковых сервисов 1С.
    
    Делегирует выполнение специализированным сервисам:
    - SyntaxInfoService: получение детальной информации о синтаксисе
    - ContextSearchService: контекстный поиск
    - ObjectMembersService: получение списка элементов объекта
    
    Для обратной совместимости также содержит:
    - find_help_by_query: основной поиск
    - get_examples_for_element: получение примеров
    """
    
    def __init__(self):
        self.syntax = syntax_info_service
        self.context = context_search_service
        self.members = object_members_service

    async def find_help_by_query(
        self,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        include_examples: bool = False
    ) -> Dict[str, Any]:
        """Универсальный поиск справки (делегирует в FindHelpService)."""
        from src.search.find_help_service import find_help_service
        return await find_help_service.find_help_by_query(
            query=query,
            limit=limit,
            filters=filters,
            include_examples=include_examples
        )

    async def get_detailed_syntax_info(
        self,
        element_name: str,
        object_name: Optional[str] = None,
        include_examples: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Получить полную техническую информацию об элементе."""
        return await self.syntax.get_detailed_syntax_info(
            element_name=element_name,
            object_name=object_name,
            include_examples=include_examples
        )

    async def search_with_context_filter(
        self,
        query: str,
        context: str,
        object_name: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Поиск с фильтром по контексту (global/object/all)."""
        return await self.context.search_with_context_filter(
            query=query,
            context=context,
            object_name=object_name,
            limit=limit
        )

    async def get_object_members_list(
        self,
        object_name: str,
        member_type: str = "all",
        limit: int = 50
    ) -> Dict[str, Any]:
        """Получить список элементов объекта с фильтрацией по типу."""
        return await self.members.get_object_members_list(
            object_name=object_name,
            member_type=member_type,
            limit=limit
        )

    async def get_examples_for_element(
        self,
        element_name: str,
        object_name: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """Получить примеры кода для элемента."""
        from src.search.examples_service import examples_service
        return await examples_service.get_examples_for_element(
            element_name=element_name,
            object_name=object_name,
            limit=limit
        )


search_service = SearchService()
