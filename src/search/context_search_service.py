"""Сервис контекстного поиска 1С."""

from typing import Optional, Dict, Any

from src.core.elasticsearch import es_client
from src.core.logging import get_logger
from src.search.query_builder import QueryBuilder
from src.search.ranker import SearchRanker
from src.search.formatter import SearchFormatter

logger = get_logger(__name__)


class ContextSearchService:
    """
    Сервис контекстного поиска элементов 1С.
    
    Отвечает за:
    - Поиск с фильтром по контексту (global/object/all)
    - Фильтрацию по типу элементов
    - Ранжирование результатов
    """

    def __init__(self):
        self.query_builder = QueryBuilder()
        self.ranker = SearchRanker()
        self.formatter = SearchFormatter()

    async def search_with_context_filter(
        self,
        query: str,
        context: str,
        object_name: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Поиск с фильтром по контексту (global/object/all).
        
        Args:
            query: Поисковый запрос
            context: Контекст поиска (global, object, all)
            object_name: Имя объекта (опционально)
            limit: Максимальное количество результатов
            
        Returns:
            Результаты поиска с метаинформацией
        """
        try:
            # Строим базовый запрос
            elasticsearch_query = self.query_builder.build_search_query(query, limit)
            
            # Добавляем фильтры по контексту
            context_filters = self._build_context_filters(context, object_name)
            
            # Применяем фильтры
            if context_filters:
                elasticsearch_query["query"] = {
                    "bool": {
                        "must": [elasticsearch_query["query"]],
                        "filter": [{"bool": {"should": context_filters}}]
                    }
                }
            
            response = await es_client.search(elasticsearch_query)
            
            # Обрабатываем ответ
            if not response:
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "context": context,
                    "error": "Ошибка выполнения поиска"
                }
            
            # Извлекаем результаты
            hits = response.get("hits", {}).get("hits", [])
            total = response.get("hits", {}).get("total", {})
            total_count = total.get("value", 0) if isinstance(total, dict) else total
            
            # Ранжируем результаты
            ranked_results = self.ranker.rank_results(hits, query)
            
            # Форматируем для вывода
            formatted_results = self.formatter.format_search_results(ranked_results)
            
            return {
                "results": formatted_results,
                "total": total_count,
                "query": query,
                "context": context
            }
            
        except Exception as e:
            logger.error(f"Ошибка контекстного поиска '{query}' в контексте '{context}': {e}")
            return {
                "results": [],
                "total": 0,
                "query": query,
                "context": context,
                "error": str(e)
            }

    def _build_context_filters(
        self,
        context: str,
        object_name: Optional[str] = None
    ) -> list:
        """Строит фильтры для контекстного поиска."""
        context_filters = []
        
        if context == "global":
            context_filters.extend([
                {"term": {"type": "global_function"}},
                {"term": {"type": "global_procedure"}},
                {"term": {"type": "global_event"}}
            ])
        elif context == "object":
            context_filters.extend([
                {"term": {"type": "object_function"}},
                {"term": {"type": "object_procedure"}},
                {"term": {"type": "object_property"}},
                {"term": {"type": "object_event"}},
                {"term": {"type": "object_constructor"}}
            ])
        # Для "all" не добавляем фильтры
        
        # Добавляем фильтр по объекту если указан
        if object_name and context != "global":
            context_filters.append({"term": {"object": object_name}})
        
        return context_filters


# Глобальный экземпляр сервиса
context_search_service = ContextSearchService()
