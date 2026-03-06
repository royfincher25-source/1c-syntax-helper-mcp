"""Benchmarks для поиска."""

import asyncio
import time
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.search.search_service import SearchService
from src.search.cache_service import SearchCacheService
from src.core.cache import InMemoryCache


class BenchmarkSearch:
    """Бенчмарки для поиска."""
    
    @pytest.fixture
    def cache(self):
        return InMemoryCache(max_size=1000, default_ttl=300)
    
    @pytest.fixture
    def mock_es_client(self):
        mock = Mock()
        mock.is_connected = AsyncMock(return_value=True)
        mock.search = AsyncMock(return_value={
            "hits": {
                "total": {"value": 10},
                "hits": [
                    {
                        "_source": {
                            "name": f"Method{i}",
                            "object": "TestObject",
                            "syntax_ru": f"Method{i}(param)",
                            "description": f"Test method {i}"
                        }
                    }
                    for i in range(10)
                ]
            },
            "took": 5
        })
        return mock
    
    @pytest.mark.asyncio
    async def benchmark_search_cold(self, cache, mock_es_client):
        """Бенчмарк холодного поиска (без кэша)."""
        await cache.clear()
        
        with patch('src.search.search_service.es_client', mock_es_client):
            service = SearchService(cache_service=SearchCacheService(cache))
            
            iterations = 100
            start = time.perf_counter()
            
            for _ in range(iterations):
                await service.search_1c_syntax("тест", limit=10)
            
            elapsed = time.perf_counter() - start
            avg_ms = (elapsed / iterations) * 1000
            
            print(f"\n=== Search Benchmark (Cold) ===")
            print(f"Iterations: {iterations}")
            print(f"Total time: {elapsed:.3f}s")
            print(f"Average per request: {avg_ms:.2f}ms")
            print(f"Requests per second: {iterations/elapsed:.1f}")
            
            assert avg_ms < 100, f"Search too slow: {avg_ms:.2f}ms"
    
    @pytest.mark.asyncio
    async def benchmark_search_warm(self, cache, mock_es_client):
        """Бенчмарк теплого поиска (с кэшем)."""
        with patch('src.search.search_service.es_client', mock_es_client):
            service = SearchService(cache_service=SearchCacheService(cache))
            
            await service.search_1c_syntax("тест", limit=10)
            
            iterations = 1000
            start = time.perf_counter()
            
            for _ in range(iterations):
                await service.search_1c_syntax("тест", limit=10)
            
            elapsed = time.perf_counter() - start
            avg_ms = (elapsed / iterations) * 1000
            
            print(f"\n=== Search Benchmark (Warm/Cached) ===")
            print(f"Iterations: {iterations}")
            print(f"Total time: {elapsed:.3f}s")
            print(f"Average per request: {avg_ms:.4f}ms")
            print(f"Requests per second: {iterations/elapsed:.1f}")
            
            assert avg_ms < 10, f"Cached search too slow: {avg_ms:.2f}ms"
    
    @pytest.mark.asyncio
    async def benchmark_concurrent_search(self, cache, mock_es_client):
        """Бенчмарк конкурентного поиска."""
        with patch('src.search.search_service.es_client', mock_es_client):
            service = SearchService(cache_service=SearchCacheService(cache))
            
            iterations = 100
            concurrent_requests = 10
            
            async def run_search():
                start = time.perf_counter()
                await service.search_1c_syntax("тест", limit=10)
                return time.perf_counter() - start
            
            start = time.perf_counter()
            
            tasks = [run_search() for _ in range(concurrent_requests)]
            results = await asyncio.gather(*tasks)
            
            total_elapsed = time.perf_counter() - start
            avg_ms = (sum(results) / len(results)) * 1000
            throughput = iterations / total_elapsed
            
            print(f"\n=== Concurrent Search Benchmark ===")
            print(f"Concurrent requests: {concurrent_requests}")
            print(f"Total iterations: {iterations}")
            print(f"Total time: {total_elapsed:.3f}s")
            print(f"Average per request: {avg_ms:.2f}ms")
            print(f"Throughput: {throughput:.1f} req/s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
