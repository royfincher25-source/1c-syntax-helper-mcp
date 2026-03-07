"""Сервис для получения детальной информации о синтаксисе 1С."""

from typing import Optional, Dict, Any

from src.core.elasticsearch import es_client
from src.core.logging import get_logger
from src.search.cache_service import search_cache_service
from src.search.query_builder import QueryBuilder

logger = get_logger(__name__)


class SyntaxInfoService:
    """
    Сервис для получения детальной информации о синтаксисе элементов 1С.
    
    Отвечает за:
    - Точный поиск элементов по имени
    - Поиск методов объектов
    - Кэширование результатов
    """

    def __init__(self):
        self.query_builder = QueryBuilder()

    async def get_detailed_syntax_info(
        self,
        element_name: str,
        object_name: Optional[str] = None,
        include_examples: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Получить полную техническую информацию об элементе.
        
        Args:
            element_name: Имя элемента
            object_name: Имя объекта (опционально)
            include_examples: Включать примеры кода
            
        Returns:
            Словарь с информацией об элементе или None
        """
        try:
            # Пытаемся получить из кэша
            cached_result = await search_cache_service.get_cached_syntax(
                element_name, object_name, include_examples
            )
            if cached_result is not None:
                logger.debug(
                    f"Детальная информация '{element_name}' найдена в кэше",
                    extra={"extra_data": {"cached": True, "element": element_name}}
                )
                return cached_result

            # Формируем запрос для точного поиска
            elasticsearch_query = self._build_syntax_query(element_name, object_name)

            response = await es_client.search(elasticsearch_query)

            if response.get('hits', {}).get('total', {}).get('value', 0) > 0:
                doc = response['hits']['hits'][0]['_source']

                # Фильтруем примеры если не нужны
                if not include_examples:
                    doc = doc.copy()
                    doc.pop('examples', None)

                # Кэшируем результат
                await search_cache_service.set_cached_syntax(
                    element_name, doc, object_name, include_examples
                )

                return doc

            return None

        except Exception as e:
            logger.error(f"Ошибка получения детальной информации для '{element_name}': {e}")
            return None

    def _build_syntax_query(
        self,
        element_name: str,
        object_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Строит Elasticsearch запрос для поиска синтаксиса."""
        if object_name:
            # Для поиска метода объекта используем гибкий поиск с .keyword для точных совпадений
            return {
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"object.keyword": object_name}}
                        ],
                        "should": [
                            {"term": {"name.keyword": {"value": element_name, "boost": 5.0}}},
                            {"match": {"name": {"query": element_name, "boost": 3.0}}},
                            {"wildcard": {"name.keyword": {"value": f"*{element_name}*", "boost": 2.0}}},
                            {"match_phrase": {"name": {"query": element_name, "boost": 2.5}}}
                        ],
                        "minimum_should_match": 1
                    }
                },
                "size": 1
            }
        else:
            # Для поиска без объекта используем точный запрос
            return self.query_builder.build_exact_query(element_name)


# Глобальный экземпляр сервиса
syntax_info_service = SyntaxInfoService()
