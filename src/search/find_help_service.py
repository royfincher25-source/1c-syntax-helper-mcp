"""Сервис основного поиска по документации 1С."""

from typing import Optional, Dict, Any
import time

from src.core.elasticsearch import es_client
from src.core.logging import get_logger
from src.search.cache_service import search_cache_service
from src.search.circuit_breaker_handler import search_circuit_breaker_handler
from src.search.query_builder import QueryBuilder
from src.search.ranker import SearchRanker
from src.search.formatter import SearchFormatter

logger = get_logger(__name__)


class FindHelpService:
    """
    Сервис основного поиска по документации 1С.
    
    Отвечает за:
    - Универсальный поиск с фильтрами
    - Кэширование результатов
    - Circuit breaker с fallback
    """

    def __init__(self):
        self.query_builder = QueryBuilder()
        self.ranker = SearchRanker()
        self.formatter = SearchFormatter()

    async def find_help_by_query(
        self,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        include_examples: bool = False
    ) -> Dict[str, Any]:
        """
        Универсальный поиск справки по любому элементу 1С с фильтрами.
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            filters: Опциональные фильтры {type: ..., object: ..., version_from: ...}
            include_examples: Включать примеры кода
        """
        start_time = time.time()

        try:
            # Пытаемся получить из кэша
            cached_result = await search_cache_service.get_cached_search(
                query, limit, filters, include_examples
            )
            if cached_result is not None:
                search_time = int((time.time() - start_time) * 1000)
                logger.info(
                    f"Поиск '{query}' найден в кэше за {search_time}ms",
                    extra={
                        "extra_data": {
                            "cached": True,
                            "query": query,
                            "limit": limit,
                            "filters": filters,
                            "include_examples": include_examples
                        }
                    }
                )
                return cached_result

            # Проверяем подключение к Elasticsearch
            if not await es_client.is_connected():
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "search_time_ms": 0,
                    "error": "Elasticsearch недоступен"
                }

            # Строим запрос с фильтрами
            es_query = self.query_builder.build_search_query(
                query=query,
                limit=limit,
                search_type="auto",
                filters=filters
            )

            # Выполняем поиск с обработкой circuit breaker и fallback
            async def execute_search():
                return await es_client.search(es_query)
            
            response = await search_circuit_breaker_handler.execute_with_fallback(
                query, limit, filters, execute_search
            )
            
            # Проверяем, вернулся ли fallback или ошибка
            if "error" in response and response.get("fallback_used"):
                return response

            if not response:
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "search_time_ms": int((time.time() - start_time) * 1000),
                    "error": "Ошибка выполнения поиска"
                }

            # Извлекаем результаты
            hits = response.get("hits", {}).get("hits", [])
            total = response.get("hits", {}).get("total", {})
            total_count = total.get("value", 0) if isinstance(total, dict) else total

            # Ранжируем результаты
            ranked_results = self.ranker.rank_results(hits, query)

            # Форматируем для вывода
            formatted_results = self.formatter.format_search_results(
                ranked_results,
                include_examples=include_examples
            )

            search_time = int((time.time() - start_time) * 1000)

            result = {
                "results": formatted_results,
                "total": total_count,
                "query": query,
                "search_time_ms": search_time,
                "filters_applied": filters is not None,
                "examples_included": include_examples
            }

            # Кэшируем результат
            await search_cache_service.set_cached_search(
                query, limit, result, filters, include_examples
            )

            logger.info(
                f"Поиск '{query}' завершен за {search_time}ms. Найдено: {len(formatted_results)}",
                extra={
                    "extra_data": {
                        "filters_applied": filters is not None,
                        "examples_included": include_examples
                    }
                }
            )

            return result

        except Exception as e:
            search_time = int((time.time() - start_time) * 1000)
            logger.error(f"Ошибка поиска '{query}': {e}")

            return {
                "results": [],
                "total": 0,
                "query": query,
                "search_time_ms": search_time,
                "error": str(e)
            }


find_help_service = FindHelpService()
