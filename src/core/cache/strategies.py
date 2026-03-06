from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.cache import CacheEntry


class EvictionStrategy(ABC):
    """Абстрактный класс стратегии вытеснения из кэша."""
    
    @abstractmethod
    def select_eviction_key(self, cache: dict) -> str:
        """Выбирает ключ для вытеснения."""
        pass
    
    @abstractmethod
    def on_access(self, cache: dict, key: str) -> None:
        """Вызывается при обращении к записи."""
        pass


class LRUStrategy(EvictionStrategy):
    """Стратегия вытеснения LRU (Least Recently Used)."""
    
    def select_eviction_key(self, cache: dict) -> str:
        """Выбирает наименее используемый ключ."""
        return next(iter(cache))
    
    def on_access(self, cache: dict, key: str) -> None:
        """Перемещает accessed ключ в конец (для OrderedDict)."""
        pass


class LFUStrategy(EvictionStrategy):
    """Стратегия вытеснения LFU (Least Frequently Used)."""
    
    def select_eviction_key(self, cache: dict) -> str:
        """Выбирает ключ с наименьшим количеством обращений."""
        min_access_count = float('inf')
        min_key = None
        
        for key, entry in cache.items():
            if entry.access_count < min_access_count:
                min_access_count = entry.access_count
                min_key = key
        
        return min_key
    
    def on_access(self, cache: dict, key: str) -> None:
        """Увеличивает счётчик обращений."""
        pass
