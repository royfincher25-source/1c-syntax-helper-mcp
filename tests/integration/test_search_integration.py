"""Integration тесты для Search Service."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from src.search.search_service import SearchService
from src.search.cache_service import SearchCacheService
from src.core.cache import InMemoryCache


class TestSearchServiceIntegration:
    """Интеграционные тесты SearchService."""
    
    @pytest.fixture
    def cache(self):
        """Фикстура для кэша."""
        return InMemoryCache(max_size=100, default_ttl=60)
    
    @pytest.fixture
    def mock_es_client(self):
        """Мок для Elasticsearch клиента."""
        mock = Mock()
        mock.is_connected = AsyncMock(return_value=True)
        mock.search = AsyncMock(return_value={
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {
                            "name": "СтрДлина",
                            "object": "Global context",
                            "syntax_ru": "СтрДлина(Строка)",
                            "description": "Получает длину строки"
                        }
                    }
                ]
            }
        })
        return mock
    
    @pytest.mark.asyncio
    async def test_search_with_cache_hit(self, cache, mock_es_client):
        """Тест поиска с попаданием в кэш."""
        cache_service = SearchCacheService(cache)
        
        cached_result = {"name": "Test", "results": []}
        await cache.set("search:query:test", cached_result, ttl=60)
        
        with patch('src.search.search_service.es_client', mock_es_client):
            service = SearchService(cache_service=cache_service)
            
            result = await service.search_1c_syntax("тест", limit=10)
            
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_search_with_context_filter(self, mock_es_client):
        """Тест контекстного поиска."""
        mock_es_client.search = AsyncMock(return_value={
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {
                        "_source": {
                            "name": "Добавить",
                            "object": "ТаблицаЗначений",
                            "syntax_ru": "Добавить(Колонка)",
                            "description": "Добавляет колонку"
                        }
                    },
                    {
                        "_source": {
                            "name": "Добавить",
                            "object": "Массив",
                            "syntax_ru": "Добавить(Значение)",
                            "description": "Добавляет элемент"
                        }
                    }
                ]
            }
        })
        
        with patch('src.search.search_service.es_client', mock_es_client):
            service = SearchService()
            
            result = await service.search_with_context_filter(
                "Добавить",
                context="object",
                limit=10
            )
            
            assert result is not None
            assert "results" in result
    
    @pytest.mark.asyncio
    async def test_get_syntax_info(self, mock_es_client):
        """Тест получения синтаксической информации."""
        mock_es_client.search = AsyncMock(return_value={
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {
                            "name": "СтрДлина",
                            "object": "Global context",
                            "syntax_ru": "СтрДлина(Строка)",
                            "description": "Получает длину строки",
                            "parameters": [
                                {"name": "Строка", "type": "Строка", "required": True}
                            ],
                            "return_type": "Число"
                        }
                    }
                ]
            }
        })
        
        with patch('src.search.search_service.es_client', mock_es_client):
            service = SearchService()
            
            result = await service.get_detailed_syntax_info("СтрДлина")
            
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_get_object_members(self, mock_es_client):
        """Тест получения списка членов объекта."""
        mock_es_client.search = AsyncMock(return_value={
            "hits": {
                "total": {"value": 5},
                "hits": [
                    {
                        "_source": {
                            "name": "Количество",
                            "object": "ТаблицаЗначений",
                            "type": "method"
                        }
                    },
                    {
                        "_source": {
                            "name": "Добавить",
                            "object": "ТаблицаЗначений", 
                            "type": "method"
                        }
                    }
                ]
            }
        })
        
        with patch('src.search.search_service.es_client', mock_es_client):
            service = SearchService()
            
            result = await service.get_object_members_list(
                "ТаблицаЗначений",
                member_type="methods"
            )
            
            assert result is not None


class TestSearchCacheIntegration:
    """Интеграционные тесты кэширования поиска."""
    
    @pytest.fixture
    def cache(self):
        """Фикстура для кэша."""
        return InMemoryCache(max_size=50, default_ttl=30)
    
    @pytest.mark.asyncio
    async def test_cache_key_generation(self, cache):
        """Тест генерации ключей кэша."""
        cache_service = SearchCacheService(cache)
        
        key1 = await cache_service._generate_cache_key("тест", "object", 10)
        key2 = await cache_service._generate_cache_key("тест", "object", 10)
        key3 = await cache_service._generate_cache_key("другой", "object", 10)
        
        assert key1 == key2
        assert key1 != key3
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self, cache):
        """Тест инвалидации кэша."""
        cache_service = SearchCacheService(cache)
        
        await cache.set("search:query:test:object:10", {"data": "test"}, ttl=60)
        
        await cache_service.invalidate_search_cache("test")
        
        result = await cache.get("search:query:test:object:10")
        assert result is None
