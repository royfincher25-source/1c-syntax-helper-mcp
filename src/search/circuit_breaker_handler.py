"""Circuit breaker handler для поиска с fallback логикой."""

from typing import Optional, Dict, Any
import time

from src.core.elasticsearch import CircuitOpenError, get_circuit_breaker_state
from src.core.logging import get_logger
from src.search.cache_service import search_cache_service

logger = get_logger(__name__)


class SearchCircuitBreakerHandler:
    """
    Обработчик circuit breaker для поисковых запросов.
    
    Обеспечивает:
    - Fallback на кэш при открытом circuit breaker
    - Логирование переходов между состояниями
    - Возврат понятных ошибок клиенту
    """

    def __init__(self):
        self._fallback_ttl = 300  # 5 минут

    async def execute_with_fallback(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]],
        execute_search
    ) -> Dict[str, Any]:
        """
        Выполняет поиск с circuit breaker и fallback.
        
        Args:
            query: Поисковый запрос
            limit: Лимит результатов
            filters: Фильтры запроса
            execute_search: Async функция для выполнения поиска
            
        Returns:
            Результат поиска или fallback из кэша
        """
        start_time = time.time()
        
        try:
            # Выполняем поиск
            return await execute_search()
            
        except CircuitOpenError as e:
            # Circuit breaker открыт - пытаемся получить данные из кэша
            logger.warning(
                f"Circuit breaker открыт, fallback на кэш для запроса '{query}'"
            )
            
            # Пытаемся найти fallback в кэше (без include_examples)
            cached_result = await search_cache_service.get_cached_search_fallback(
                query, limit, filters
            )
            
            if cached_result:
                logger.info(f"Fallback успешен: данные получены из кэша")
                cached_result["fallback_used"] = True
                cached_result["circuit_state"] = get_circuit_breaker_state()
                return cached_result
            
            # Кэш пуст - возвращаем ошибку
            return {
                "results": [],
                "total": 0,
                "query": query,
                "search_time_ms": int((time.time() - start_time) * 1000),
                "error": "Elasticsearch временно недоступен. Попробуйте позже.",
                "fallback_used": True,
                "circuit_state": get_circuit_breaker_state()
            }

    def get_error_response(
        self,
        query: str,
        start_time: float,
        error_message: str = "Ошибка выполнения поиска"
    ) -> Dict[str, Any]:
        """Создаёт стандартный ответ об ошибке."""
        return {
            "results": [],
            "total": 0,
            "query": query,
            "search_time_ms": int((time.time() - start_time) * 1000),
            "error": error_message
        }


# Глобальный экземпляр обработчика
search_circuit_breaker_handler = SearchCircuitBreakerHandler()
