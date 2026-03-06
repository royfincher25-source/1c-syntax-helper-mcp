"""Benchmarks для кэша."""

import asyncio
import time
import pytest
import random
import string

from src.core.cache import InMemoryCache, CacheEntry
from src.core.cache.strategies import LRUStrategy, LFUStrategy


class BenchmarkCache:
    """Бенчмарки для кэша."""
    
    def generate_test_data(self, size: int = 1000) -> list:
        """Генерирует тестовые данные."""
        return [
            {
                "id": i": '',
                "name.join(random.choices(string.ascii_letters, k=10)),
                "data": ''.join(random.choices(string.ascii_letters, k=100))
            }
            for i in range(size)
        ]
    
    @pytest.mark.asyncio
    async def benchmark_cache_set_lru(self):
        """Бенчмарк записи в кэш LRU."""
        cache = InMemoryCache(max_size=10000, default_ttl=300)
        test_data = self.generate_test_data(1000)
        
        iterations = 100
        start = time.perf_counter()
        
        for _ in range(iterations):
            for i, item in enumerate(test_data):
                await cache.set(f"key:{i}", item, ttl=60)
        
        elapsed = time.perf_counter() - start
        total_ops = iterations * len(test_data)
        
        print(f"\n=== Cache Set Benchmark (LRU) ===")
        print(f"Operations: {total_ops}")
        print(f"Total time: {elapsed:.3f}s")
        print(f"Ops per second: {total_ops/elapsed:.0f}")
        print(f"Average per op: {elapsed/total_ops*1000:.4f}ms")
        
        assert elapsed < 5, f"Cache set too slow: {elapsed:.2f}s"
    
    @pytest.mark.asyncio
    async def benchmark_cache_get_lru(self):
        """Бенчмарк чтения из кэша LRU."""
        cache = InMemoryCache(max_size=10000, default_ttl=300)
        test_data = self.generate_test_data(1000)
        
        for i, item in enumerate(test_data):
            await cache.set(f"key:{i}", item, ttl=60)
        
        iterations = 1000
        keys = [f"key:{i}" for i in range(1000)]
        
        start = time.perf_counter()
        
        for _ in range(iterations):
            for key in keys:
                await cache.get(key)
        
        elapsed = time.perf_counter() - start
        total_ops = iterations * len(keys)
        
        print(f"\n=== Cache Get Benchmark (LRU) ===")
        print(f"Operations: {total_ops}")
        print(f"Total time: {elapsed:.3f}s")
        print(f"Ops per second: {total_ops/elapsed:.0f}")
        print(f"Average per op: {elapsed/total_ops*1000:.4f}ms")
        
        assert elapsed < 5, f"Cache get too slow: {elapsed:.2f}s"
    
    @pytest.mark.asyncio
    async def benchmark_cache_lru_vs_lfu(self):
        """Сравнение LRU и LFU стратегий."""
        iterations = 10
        sizes = [100, 500, 1000, 5000]
        
        print(f"\n=== LRU vs LFU Comparison ===")
        print(f"{'Size':<10} {'LRU (ms)':<15} {'LFU (ms)':<15} {'Winner':<10}")
        print("-" * 50)
        
        for size in sizes:
            test_data = self.generate_test_data(size)
            
            lru_times = []
            lfu_times = []
            
            for _ in range(iterations):
                cache_lru = InMemoryCache(max_size=size//2, default_ttl=60, strategy="lru")
                cache_lfu = InMemoryCache(max_size=size//2, default_ttl=60, strategy="lfu")
                
                for item in test_data:
                    await cache_lru.set(f"key:{item['id']}", item)
                    await cache_lfu.set(f"key:{item['id']}", item)
                
                access_pattern = [i % (size//2) for i in range(size)]
                
                start = time.perf_counter()
                for key_idx in access_pattern:
                    await cache_lru.get(f"key:{key_idx}")
                lru_time = time.perf_counter() - start
                lru_times.append(lru_time * 1000)
                
                start = time.perf_counter()
                for key_idx in access_pattern:
                    await cache_lfu.get(f"key:{key_idx}")
                lfu_time = time.perf_counter() - start
                lfu_times.append(lfu_time * 1000)
            
            avg_lru = sum(lru_times) / len(lru_times)
            avg_lfu = sum(lfu_times) / len(lfu_times)
            winner = "LFU" if avg_lfu < avg_lru else "LRU"
            
            print(f"{size:<10} {avg_lru:<15.2f} {avg_lfu:<15.2f} {winner:<10}")
    
    @pytest.mark.asyncio
    async def benchmark_cache_hit_rate(self):
        """Бенчмарк hit rate при разных паттернах доступа."""
        cache = InMemoryCache(max_size=100, default_ttl=300)
        
        test_data = self.generate_test_data(50)
        for i, item in enumerate(test_data):
            await cache.set(f"key:{i}", item)
        
        print(f"\n=== Cache Hit Rate Benchmark ===")
        
        popular_keys = [f"key:{i}" for i in range(10)]
        random_keys = [f"key:{i}" for i in range(50)]
        
        await cache.clear()
        for i, item in enumerate(test_data):
            await cache.set(f"key:{i}", item)
        
        for _ in range(100):
            for key in popular_keys:
                await cache.get(key)
        
        stats = await cache.get_stats()
        print(f"Popular keys (80/20 pattern): {stats['hit_rate_percent']:.1f}% hit rate")
        
        await cache.clear()
        for i, item in enumerate(test_data):
            await cache.set(f"key:{i}", item)
        
        for _ in range(100):
            for key in random_keys:
                await cache.get(key)
        
        stats = await cache.get_stats()
        print(f"Random keys pattern: {stats['hit_rate_percent']:.1f}% hit rate")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
