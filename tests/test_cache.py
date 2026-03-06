#!/usr/bin/env python3
"""Тесты для InMemoryCache."""

import asyncio
import sys
import time
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.cache import InMemoryCache, CacheEntry, CacheStats


async def test_basic_set_get():
    """Тест базовой установки и получения."""
    print("\n=== Тест 1: Базовая установка и получение ===")
    
    cache = InMemoryCache(max_size=10, default_ttl=60)
    await cache.start()
    
    # Установка значения
    await cache.set("key1", "value1")
    
    # Получение значения
    result = await cache.get("key1")
    assert result == "value1", f"Ожидалось 'value1', получено {result}"
    
    print("✅ Базовая установка и получение работает")
    
    await cache.stop()


async def test_ttl_expiration():
    """Тест истечения TTL."""
    print("\n=== Тест 2: Истечение TTL ===")
    
    cache = InMemoryCache(max_size=10, default_ttl=1)  # 1 секунда TTL
    await cache.start()
    
    # Установка значения с коротким TTL
    await cache.set("key_ttl", "value_ttl", ttl=1)
    
    # Сразу должно работать
    result = await cache.get("key_ttl")
    assert result == "value_ttl", f"Ожидалось 'value_ttl', получено {result}"
    print("✅ Значение найдено до истечения TTL")
    
    # Ждём истечения TTL
    print("⏳ Ожидание истечения TTL (1 секунда)...")
    await asyncio.sleep(1.5)
    
    # Должно вернуть None
    result = await cache.get("key_ttl")
    assert result is None, f"Ожидалось None (истёк TTL), получено {result}"
    print("✅ TTL истёк корректно")
    
    await cache.stop()


async def test_lru_eviction():
    """Тест LRU eviction при переполнении."""
    print("\n=== Тест 3: LRU Eviction ===")
    
    cache = InMemoryCache(max_size=3, default_ttl=60)
    await cache.start()
    
    # Заполняем кэш
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")
    
    # Добавляем ещё один, должен вытеснить oldest (key1)
    await cache.set("key4", "value4")
    
    # key1 должен быть вытеснен
    result = await cache.get("key1")
    assert result is None, f"Ожидалось None (LRU eviction), получено {result}"
    print("✅ LRU eviction работает (key1 вытеснен)")
    
    # Остальные ключи должны быть доступны
    assert await cache.get("key2") == "value2"
    assert await cache.get("key3") == "value3"
    assert await cache.get("key4") == "value4"
    print("✅ Остальные ключи доступны")
    
    await cache.stop()


async def test_cache_stats():
    """Тест статистики кэша."""
    print("\n=== Тест 4: Статистика кэша ===")
    
    cache = InMemoryCache(max_size=10, default_ttl=60)
    await cache.start()
    
    # Несколько запросов
    await cache.set("key1", "value1")
    await cache.get("key1")  # hit
    await cache.get("key1")  # hit
    await cache.get("key2")  # miss
    
    stats = await cache.get_stats()
    
    print(f"Статистика: {stats}")
    
    assert stats["hits"] == 2, f"Ожидалось 2 hits, получено {stats['hits']}"
    assert stats["misses"] == 1, f"Ожидался 1 miss, получено {stats['misses']}"
    assert stats["hit_rate_percent"] > 60, f"Ожидался hit rate > 60%, получено {stats['hit_rate_percent']}"
    
    print(f"✅ Статистика корректна (hit rate: {stats['hit_rate_percent']}%)")
    
    await cache.stop()


async def test_delete_and_clear():
    """Тест удаления и очистки кэша."""
    print("\n=== Тест 5: Удаление и очистка ===")
    
    cache = InMemoryCache(max_size=10, default_ttl=60)
    await cache.start()
    
    # Установка нескольких значений
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")
    
    # Удаление одного ключа
    deleted = await cache.delete("key2")
    assert deleted is True, "Ожидалось True (ключ удалён)"
    
    result = await cache.get("key2")
    assert result is None, "Ожидалось None (ключ удалён)"
    print("✅ Удаление ключа работает")
    
    # Очистка всего кэша
    await cache.clear()
    
    stats = await cache.get_stats()
    assert stats["size"] == 0, f"Ожидался размер 0, получено {stats['size']}"
    print("✅ Очистка кэша работает")
    
    await cache.stop()


async def test_concurrent_access():
    """Тест конкурентного доступа."""
    print("\n=== Тест 6: Конкурентный доступ ===")
    
    cache = InMemoryCache(max_size=100, default_ttl=60)
    await cache.start()
    
    async def worker(worker_id: int):
        for i in range(10):
            key = f"worker{worker_id}:key{i}"
            await cache.set(key, f"value{i}")
            await cache.get(key)
            await asyncio.sleep(0.01)
    
    # Запускаем 5 воркеров параллельно
    tasks = [worker(i) for i in range(5)]
    await asyncio.gather(*tasks)
    
    stats = await cache.get_stats()
    print(f"Статистика после конкурентного доступа: {stats}")
    
    assert stats["size"] == 50, f"Ожидался размер 50, получено {stats['size']}"
    print("✅ Конкурентный доступ корректен")
    
    await cache.stop()


async def test_exists():
    """Тест проверки существования ключа."""
    print("\n=== Тест 7: Проверка существования ===")
    
    cache = InMemoryCache(max_size=10, default_ttl=1)
    await cache.start()
    
    await cache.set("key_exists", "value")
    
    exists = await cache.exists("key_exists")
    assert exists is True, "Ожидалось True (ключ существует)"
    print("✅ exists() работает для существующего ключа")
    
    exists = await cache.exists("key_not_exists")
    assert exists is False, "Ожидалось False (ключ не существует)"
    print("✅ exists() работает для несуществующего ключа")
    
    # Ждём истечения TTL
    await asyncio.sleep(1.5)
    
    exists = await cache.exists("key_exists")
    assert exists is False, "Ожидалось False (TTL истёк)"
    print("✅ exists() корректно обрабатывает истёкший TTL")
    
    await cache.stop()


async def main():
    """Запускает все тесты."""
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ InMemoryCache")
    print("="*60)
    
    await test_basic_set_get()
    await test_ttl_expiration()
    await test_lru_eviction()
    await test_cache_stats()
    await test_delete_and_clear()
    await test_concurrent_access()
    await test_exists()
    
    print("\n" + "="*60)
    print("ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ ✅")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
