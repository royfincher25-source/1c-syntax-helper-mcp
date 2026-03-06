"""In-memory кэш с TTL для оптимизации запросов."""

import asyncio
import time
from typing import Any, Optional, Dict, Generic, TypeVar
from dataclasses import dataclass, field
from collections import OrderedDict

from src.core.logging import get_logger
from src.core.cache.strategies import EvictionStrategy, LRUStrategy, LFUStrategy

logger = get_logger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """Запись кэша с метаданными."""
    value: T
    expires_at: float
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Проверяет, истёк ли срок действия записи."""
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Обновляет время последнего доступа."""
        self.last_accessed = time.time()
        self.access_count += 1


class CacheStats:
    """Статистика кэша."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

    @property
    def hit_rate(self) -> float:
        """Возвращает процент попаданий в кэш."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total * 100

    def to_dict(self) -> Dict[str, Any]:
        """Возвращает статистику как словарь."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "hit_rate_percent": round(self.hit_rate, 2),
            "total_requests": self.hits + self.misses
        }

    def reset(self) -> None:
        """Сбрасывает статистику."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0


class InMemoryCache:
    """
    In-memory кэш с TTL и поддержкой стратегий вытеснения.

    Особенности:
    - TTL (Time To Live) для каждой записи
    - Стратегии вытеснения: LRU, LFU
    - Статистика попаданий/промахов
    - Асинхронная очистка устаревших записей
    - Потокобезопасность через asyncio.Lock
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
        cleanup_interval: int = 60,
        strategy: str = "lru"
    ):
        """
        Инициализирует кэш.

        Args:
            max_size: Максимальное количество записей в кэше
            default_ttl: TTL по умолчанию в секундах
            cleanup_interval: Интервал автоматической очистки в секундах
            strategy: Стратегия вытеснения ('lru' или 'lfu')
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._stats = CacheStats()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None

        self._eviction_strategy: EvictionStrategy = self._create_strategy(strategy)

        logger.info(
            "InMemoryCache инициализирован",
            extra={
                "extra_data": {
                    "max_size": max_size,
                    "default_ttl": default_ttl,
                    "cleanup_interval": cleanup_interval,
                    "strategy": strategy
                }
            }
        )

    def _create_strategy(self, strategy: str) -> EvictionStrategy:
        """Создаёт стратегию вытеснения."""
        if strategy.lower() == "lfu":
            return LFUStrategy()
        return LRUStrategy()

    async def start(self) -> None:
        """Запускает фоновую задачу очистки кэша."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Запущена фоновая очистка кэша")

    async def stop(self) -> None:
        """Останавливает фоновую задачу очистки кэша."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Остановлена фоновая очистка кэша")

    async def _cleanup_loop(self) -> None:
        """Фоновый цикл очистки устаревших записей."""
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
        except asyncio.CancelledError:
            pass

    async def _cleanup_expired(self) -> None:
        """Очищает устаревшие записи."""
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
                self._stats.expirations += 1

            if expired_keys:
                logger.debug(
                    f"Очищено {len(expired_keys)} устаревших записей",
                    extra={"extra_data": {"expired_count": len(expired_keys)}}
                )

    async def get(self, key: str) -> Optional[Any]:
        """
        Получает значение из кэша.

        Args:
            key: Ключ кэша

        Returns:
            Значение или None, если ключ не найден или истёк
        """
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._stats.expirations += 1
                self._stats.misses += 1
                return None

            # Обновляем статистику доступа
            entry.touch()

            # Перемещаем в конец для LRU
            self._cache.move_to_end(key)

            self._stats.hits += 1

            logger.debug(
                f"Cache hit: {key}",
                extra={
                    "extra_data": {
                        "access_count": entry.access_count,
                        "age_seconds": round(time.time() - entry.created_at, 2)
                    }
                }
            )

            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """
        Устанавливает значение в кэш.

        Args:
            key: Ключ кэша
            value: Значение
            ttl: Время жизни в секундах (по умолчанию default_ttl)
        """
        async with self._lock:
            # Если ключ уже существует, обновляем его
            if key in self._cache:
                old_entry = self._cache[key]
                del self._cache[key]
                logger.debug(f"Обновлена запись кэша: {key}")

            # Проверяем размер и удаляем старые записи при необходимости
            while len(self._cache) >= self._max_size:
                eviction_key = self._eviction_strategy.select_eviction_key(self._cache)
                del self._cache[eviction_key]
                self._stats.evictions += 1
                logger.debug(f"Eviction: {eviction_key}")

            # Создаём новую запись
            now = time.time()
            entry_ttl = ttl if ttl is not None else self._default_ttl

            self._cache[key] = CacheEntry(
                value=value,
                expires_at=now + entry_ttl,
                created_at=now
            )

            logger.debug(
                f"Cache set: {key} (TTL: {entry_ttl}s)",
                extra={"extra_data": {"ttl": entry_ttl}}
            )

    async def delete(self, key: str) -> bool:
        """
        Удаляет запись из кэша.

        Args:
            key: Ключ кэша

        Returns:
            True если запись удалена, False если не найдена
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache delete: {key}")
                return True
            return False

    async def clear(self) -> None:
        """Очищает весь кэш."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Кэш очищен: {count} записей удалено")

    async def exists(self, key: str) -> bool:
        """
        Проверяет существование ключа в кэше.

        Args:
            key: Ключ кэша

        Returns:
            True если ключ существует и не истёк
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                self._stats.expirations += 1
                return False
            return True

    async def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кэша."""
        async with self._lock:
            stats = self._stats.to_dict()
            stats["size"] = len(self._cache)
            stats["max_size"] = self._max_size
            stats["utilization_percent"] = round(
                len(self._cache) / self._max_size * 100, 2
            )
            return stats

    def reset_stats(self) -> None:
        """Сбрасывает статистику кэша."""
        self._stats.reset()
        logger.info("Статистика кэша сброшена")


# Глобальный экземпляр кэша
cache = InMemoryCache(
    max_size=1000,
    default_ttl=300,
    cleanup_interval=60
)


def cached(
    ttl: int = 300,
    key_prefix: str = "",
    key_generator: callable = None,
    condition: callable = None
):
    """
    Декоратор для кэширования результатов асинхронных функций.

    Args:
        ttl: Время жизни кэша в секундах
        key_prefix: Префикс для ключа кэша
        key_generator: Функция для генерации ключа (func, args, kwargs) -> str
        condition: Функция для проверки условия кэширования результата

    Example:
        @cached(ttl=600, key_prefix="search")
        async def search(query: str) -> Dict:
            ...

        @cached(key_generator=lambda f, a, k: f"{k.get('query')}:{k.get('lang')}")
        async def search(query: str, lang: str) -> Dict:
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            if key_generator:
                cache_key = key_generator(func, args, kwargs)
            else:
                key_parts = [key_prefix, func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = ":".join(key_parts)

            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            result = await func(*args, **kwargs)

            should_cache = condition is None or condition(result)
            if should_cache:
                await cache.set(cache_key, result, ttl)

            return result

        return wrapper
    return decorator


__all__ = [
    'EvictionStrategy',
    'LRUStrategy',
    'LFUStrategy',
    'InMemoryCache',
    'CacheEntry',
    'CacheStats',
    'cache',
    'cached'
]
