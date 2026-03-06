"""Сервис кэширования для поиска 1С."""

from typing import Any, Dict, Optional
import hashlib

from src.core.cache import cache
from src.core.logging import get_logger

logger = get_logger(__name__)


class SearchCacheService:
    """
    Сервис кэширования для поисковых запросов.
    
    Отвечает за генерацию ключей кэша и управление кэшированием
    результатов поиска.
    """

    SEARCH_TTL = 300  # 5 минут
    SYNTAX_TTL = 3600  # 1 час
    EXAMPLES_TTL = 3600  # 1 час

    def _generate_filters_hash(self, filters: Optional[Dict[str, Any]]) -> str:
        """Генерирует хэш для фильтров."""
        if not filters:
            return "no_filters"
        return hashlib.md5(str(filters).encode()).hexdigest()[:8]

    def generate_search_cache_key(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
        include_examples: bool = False
    ) -> str:
        """Генерирует ключ кэша для поискового запроса."""
        filters_hash = self._generate_filters_hash(filters)
        return f"search:{query}:{limit}:{filters_hash}:{include_examples}"

    def generate_search_fallback_cache_key(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> str:
        """Генерирует fallback ключ кэша (без include_examples)."""
        filters_hash = self._generate_filters_hash(filters)
        return f"search:{query}:{limit}:{filters_hash}:False"

    def generate_syntax_cache_key(
        self,
        element_name: str,
        object_name: Optional[str] = None,
        include_examples: bool = True
    ) -> str:
        """Генерирует ключ кэша для детальной информации."""
        return f"syntax:{object_name or 'global'}:{element_name}:{include_examples}"

    def generate_examples_cache_key(
        self,
        element_name: str,
        object_name: Optional[str] = None
    ) -> str:
        """Генерирует ключ кэша для примеров кода."""
        return f"examples:{object_name or 'global'}:{element_name}"

    async def get_cached_search(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
        include_examples: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Получает кэшированный результат поиска."""
        cache_key = self.generate_search_cache_key(query, limit, filters, include_examples)
        return await cache.get(cache_key)

    async def get_cached_search_fallback(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Получает fallback кэш поиска (без include_examples)."""
        cache_key = self.generate_search_fallback_cache_key(query, limit, filters)
        return await cache.get(cache_key)

    async def set_cached_search(
        self,
        query: str,
        limit: int,
        result: Dict[str, Any],
        filters: Optional[Dict[str, Any]] = None,
        include_examples: bool = False
    ) -> None:
        """Кэширует результат поиска."""
        cache_key = self.generate_search_cache_key(query, limit, filters, include_examples)
        await cache.set(cache_key, result, ttl=self.SEARCH_TTL)

    async def get_cached_syntax(
        self,
        element_name: str,
        object_name: Optional[str] = None,
        include_examples: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Получает кэшированную детальную информацию."""
        cache_key = self.generate_syntax_cache_key(element_name, object_name, include_examples)
        return await cache.get(cache_key)

    async def set_cached_syntax(
        self,
        element_name: str,
        result: Dict[str, Any],
        object_name: Optional[str] = None,
        include_examples: bool = True
    ) -> None:
        """Кэширует детальную информацию."""
        cache_key = self.generate_syntax_cache_key(element_name, object_name, include_examples)
        await cache.set(cache_key, result, ttl=self.SYNTAX_TTL)

    async def get_cached_examples(
        self,
        element_name: str,
        object_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Получает кэшированные примеры."""
        cache_key = self.generate_examples_cache_key(element_name, object_name)
        return await cache.get(cache_key)

    async def set_cached_examples(
        self,
        element_name: str,
        result: Dict[str, Any],
        object_name: Optional[str] = None
    ) -> None:
        """Кэширует примеры кода."""
        cache_key = self.generate_examples_cache_key(element_name, object_name)
        await cache.set(cache_key, result, ttl=self.EXAMPLES_TTL)

    async def invalidate_search(self, query: str) -> None:
        """Инвалидирует кэш поиска по префиксу query (удаляет все связанные записи)."""
        search_prefix = f"search:{query}"
        logger.debug(f"Search cache invalidation for prefix: {search_prefix}")
        # Примечание: для полной инвалидации по префиксу нужно добавить метод в cache.py

    async def invalidate_syntax(self, element_name: str, object_name: Optional[str] = None) -> None:
        """Инвалидирует кэш синтаксиса."""
        cache_key = self.generate_syntax_cache_key(element_name, object_name)
        await cache.delete(cache_key)

    async def invalidate_examples(self, element_name: str, object_name: Optional[str] = None) -> None:
        """Инвалидирует кэш примеров."""
        cache_key = self.generate_examples_cache_key(element_name, object_name)
        await cache.delete(cache_key)

    async def clear_all(self) -> None:
        """Очищает весь кэш поиска."""
        await cache.clear()
        logger.info("Search cache cleared")


# Глобальный экземпляр сервиса кэширования
search_cache_service = SearchCacheService()
