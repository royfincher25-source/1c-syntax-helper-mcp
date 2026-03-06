"""Сервис для получения списка элементов объекта 1С."""

from typing import Optional, Dict, Any, List

from src.core.elasticsearch import es_client
from src.core.logging import get_logger

logger = get_logger(__name__)


class ObjectMembersService:
    """
    Сервис для получения списка элементов объекта 1С.
    
    Отвечает за:
    - Получение списка методов, свойств, событий объекта
    - Группировку по типу элементов
    - Сортировку результатов
    """

    async def get_object_members_list(
        self,
        object_name: str,
        member_type: str = "all",
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Получить список элементов объекта с фильтрацией по типу.
        
        Args:
            object_name: Имя объекта
            member_type: Тип элементов (all, methods, properties, events)
            limit: Максимальное количество результатов
            
        Returns:
            Словарь с методами, свойствами и событиями объекта
        """
        try:
            # Базовый фильтр по объекту
            query_filters = [{"term": {"object": object_name}}]
            
            # Добавляем фильтры по типу элементов
            type_filters = self._build_member_type_filters(member_type)
            if type_filters:
                query_filters.append({"bool": {"should": type_filters}})
            
            # Строим запрос
            elasticsearch_query = {
                "query": {
                    "bool": {
                        "filter": query_filters
                    }
                },
                "size": limit,
                "sort": [{"name.keyword": {"order": "asc"}}]
            }
            
            response = await es_client.search(elasticsearch_query)
            
            # Группируем результаты
            methods = []
            properties = []
            events = []
            
            for hit in response.get('hits', {}).get('hits', []):
                doc = hit['_source']
                doc_type = doc.get('type', '').lower()
                
                if 'function' in doc_type or 'procedure' in doc_type or 'constructor' in doc_type:
                    methods.append(doc)
                elif 'property' in doc_type:
                    properties.append(doc)
                elif 'event' in doc_type:
                    events.append(doc)
            
            return {
                "object": object_name,
                "member_type": member_type,
                "methods": methods,
                "properties": properties,
                "events": events,
                "total": len(methods) + len(properties) + len(events)
            }

        except Exception as e:
            logger.error(f"Ошибка получения элементов объекта '{object_name}': {e}")
            return {
                "object": object_name,
                "member_type": member_type,
                "methods": [],
                "properties": [],
                "events": [],
                "total": 0,
                "error": str(e)
            }

    def _build_member_type_filters(self, member_type: str) -> List[Dict[str, Any]]:
        """Строит фильтры по типу элементов."""
        if member_type == "methods":
            return [
                {"term": {"type": "object_function"}},
                {"term": {"type": "object_procedure"}},
                {"term": {"type": "object_constructor"}}
            ]
        elif member_type == "properties":
            return [{"term": {"type": "object_property"}}]
        elif member_type == "events":
            return [{"term": {"type": "object_event"}}]
        return []

    async def get_methods(self, object_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить только методы объекта."""
        result = await self.get_object_members_list(object_name, "methods", limit)
        return result.get("methods", [])

    async def get_properties(self, object_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить только свойства объекта."""
        result = await self.get_object_members_list(object_name, "properties", limit)
        return result.get("properties", [])

    async def get_events(self, object_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить только события объекта."""
        result = await self.get_object_members_list(object_name, "events", limit)
        return result.get("events", [])


# Глобальный экземпляр сервиса
object_members_service = ObjectMembersService()
