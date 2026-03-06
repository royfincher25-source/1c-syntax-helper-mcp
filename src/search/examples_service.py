"""Сервис для получения примеров кода элементов 1С."""

from typing import Optional, Dict, Any

from src.core.elasticsearch import es_client
from src.core.logging import get_logger
from src.search.cache_service import search_cache_service

logger = get_logger(__name__)


class ExamplesService:
    """
    Сервис для получения примеров кода элементов 1С.
    
    Отвечает за:
    - Поиск примеров для глобальных функций
    - Поиск примеров для методов объектов
    - Кэширование результатов
    """

    async def get_examples_for_element(
        self,
        element_name: str,
        object_name: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Получить примеры кода для элемента (отдельный запрос для lazy loading).
        
        Args:
            element_name: Имя элемента (функция, метод)
            object_name: Имя объекта (опционально, для методов)
            limit: Максимальное количество примеров
            
        Returns:
            Словарь с примерами кода
        """
        try:
            # Пытаемся получить из кэша
            cached_result = await search_cache_service.get_cached_examples(
                element_name, object_name
            )
            if cached_result is not None:
                logger.debug(f"Примеры для '{element_name}' найдены в кэше")
                return cached_result

            # Формируем запрос для поиска элемента
            elasticsearch_query = self._build_examples_query(element_name, object_name, limit)

            response = await es_client.search(elasticsearch_query)

            if not response or response.get('hits', {}).get('total', {}).get('value', 0) == 0:
                return {
                    "element": element_name,
                    "object": object_name,
                    "examples": [],
                    "total": 0,
                    "error": "Элемент не найден"
                }

            # Извлекаем примеры
            examples = []
            for hit in response.get('hits', {}).get('hits', []):
                doc = hit['_source']
                doc_examples = doc.get('examples', [])
                if doc_examples:
                    examples.extend(doc_examples)

            result = {
                "element": element_name,
                "object": object_name,
                "examples": examples[:limit],
                "total": len(examples)
            }

            # Кэшируем результат
            await search_cache_service.set_cached_examples(
                element_name, result, object_name
            )

            logger.info(f"Получено {len(examples)} примеров для '{element_name}'")

            return result

        except Exception as e:
            logger.error(f"Ошибка получения примеров для '{element_name}': {e}")
            return {
                "element": element_name,
                "object": object_name,
                "examples": [],
                "total": 0,
                "error": str(e)
            }

    def _build_examples_query(
        self,
        element_name: str,
        object_name: Optional[str],
        limit: int
    ) -> Dict[str, Any]:
        """Строит Elasticsearch запрос для поиска примеров."""
        if object_name:
            return {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"object": object_name}},
                            {"term": {"name.keyword": element_name}}
                        ]
                    }
                },
                "size": limit,
                "_source": ["name", "object", "full_path", "examples", "syntax_ru"]
            }
        else:
            return {
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"name.keyword": {"value": element_name, "boost": 5.0}}},
                            {"term": {"full_path": {"value": element_name, "boost": 3.0}}}
                        ],
                        "must_not": [
                            {"exists": {"field": "object"}}
                        ]
                    }
                },
                "size": limit,
                "_source": ["name", "full_path", "examples", "syntax_ru"]
            }


examples_service = ExamplesService()
