"""Клиент Elasticsearch с connection pooling и retry logic."""

import asyncio
import time
from typing import Optional, Dict, Any, List, Callable, TypeVar
from functools import wraps
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ConnectionError, NotFoundError, RequestError

from src.core.config import settings
from src.core.logging import get_logger
from src.core.constants import (
    ELASTICSEARCH_CONNECTION_TIMEOUT,
    ELASTICSEARCH_REQUEST_TIMEOUT,
    BATCH_SIZE
)
from src.core.circuit_breaker import es_circuit_breaker, CircuitOpenError

logger = get_logger(__name__)


class ElasticsearchError(Exception):
    """Базовое исключение для ошибок Elasticsearch."""
    pass


class ConnectionFailedError(ElasticsearchError):
    """Ошибка подключения к Elasticsearch."""
    pass


class IndexNotFoundError(ElasticsearchError):
    """Индекс не найден."""
    pass


F = TypeVar('F', bound=Callable)


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0) -> Callable[[F], F]:
    """
    Decorator для retry logic с экспоненциальной задержкой.

    Args:
        max_retries: Максимальное количество попыток
        base_delay: Базовая задержка в секундах (1s, 2s, 4s, 8s...)

    Returns:
        Декоратор для функций
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (ConnectionError, asyncio.TimeoutError) as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        # Экспоненциальная задержка: 1s, 2s, 4s, 8s
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Попытка {attempt + 1}/{max_retries} не удалась. "
                            f"Повтор через {delay}s: {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Все {max_retries + 1} попыток исчерпаны: {e}")
                        
            raise last_exception
        
        return wrapper
    return decorator


class ElasticsearchClient:
    """
    Клиент для работы с Elasticsearch с connection pooling и retry logic.
    
    Features:
    - Connection pooling с настраиваемым размером пула
    - Retry с экспоненциальной задержкой
    - Настраиваемые таймауты (connect/read)
    - Graceful degradation при недоступности ES
    """

    def __init__(self):
        self._client: Optional[AsyncElasticsearch] = None
        self._config = settings.elasticsearch
        # Используем настройки из конфигурации
        self._connect_timeout = self._config.connect_timeout
        self._read_timeout = self._config.read_timeout
        self._pool_maxsize = self._config.pool_maxsize
        self._max_retries = self._config.pool_max_retries
    
    async def connect(self) -> bool:
        """
        Подключается к Elasticsearch с connection pooling.

        Connection pool настройки:
        - max_retries: количество повторных попыток
        - retry_on_timeout: повтор при таймауте
        """
        try:
            self._client = AsyncElasticsearch(
                hosts=[self._config.url],
                # Таймауты
                request_timeout=self._read_timeout,
                # Connection pool настройки
                max_retries=self._max_retries,
                retry_on_timeout=True
            )

            # Проверяем подключение
            await self._client.info()
            logger.info(
                f"Подключено к Elasticsearch, "
                f"max_retries={self._max_retries}"
            )
            return True

        except ConnectionError as e:
            logger.error(f"Ошибка подключения к Elasticsearch: {e}")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при подключении к Elasticsearch: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Отключается от Elasticsearch."""
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"Ошибка при отключении от Elasticsearch: {e}")
            finally:
                self._client = None
    
    async def is_connected(self) -> bool:
        """Проверяет подключение к Elasticsearch."""
        if not self._client:
            return False
        
        try:
            await self._client.ping()
            return True
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Connection failed: {e}")
            return False
        except Exception as e:
            logger.exception(f"Elasticsearch ping failed: {e}")
            return False
    
    async def index_exists(self) -> bool:
        """Проверяет существование индекса."""
        if not self._client:
            raise ConnectionFailedError("No connection to Elasticsearch")
        
        try:
            return await self._client.indices.exists(index=self._config.index_name)
        except ConnectionError as e:
            raise ConnectionFailedError(f"Connection lost: {e}")
        except Exception as e:
            logger.error(f"Ошибка проверки индекса: {e}")
            raise ElasticsearchError(f"Failed to check index existence: {e}")
    
    async def create_index(self) -> bool:
        """
        Создает индекс с оптимизированной схемой.
        
        Оптимизации:
        - refresh_interval: 30s (уменьшает нагрузку при индексации)
        - number_of_replicas: 0 (для single-node установки)
        - _all отключен (экономит место, не нужен)
        - doc_values включены для всех keyword полей (быстрые filter/sort)
        - norms отключены для полей без scoring (экономит память)
        """
        if not self._client:
            raise ConnectionFailedError("No connection to Elasticsearch")

        # Оптимизированная схема индекса
        index_config = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                # Refresh interval увеличен для лучшей производительности записи
                "refresh_interval": "30s",
                # Транзакции для быстрой индексации
                "translog": {
                    "durability": "async",
                    "sync_interval": "5s"
                },
                # Merge policy для оптимизации
                "merge": {
                    "policy": {
                        "segments_per_tier": 10,
                        "deletes_pct_allowed": 33
                    }
                },
                "analysis": {
                    "analyzer": {
                        "russian": {
                            "tokenizer": "standard",
                            "filter": ["lowercase", "russian_stop", "russian_stemmer"]
                        }
                    },
                    "filter": {
                        "russian_stop": {"type": "stop", "stopwords": "_russian_"},
                        "russian_stemmer": {"type": "stemmer", "language": "russian"}
                    }
                }
            },
            "mappings": {
                "_all": {"enabled": False},  # Отключаем _all для экономии места
                "properties": {
                    "id": {
                        "type": "keyword",
                        "doc_values": True
                    },
                    "type": {
                        "type": "keyword",
                        "doc_values": True  # Оптимизация для filter context
                    },
                    "name": {
                        "type": "text",
                        "analyzer": "russian",
                        "fields": {
                            "keyword": {
                                "type": "keyword",
                                "doc_values": True,
                                "ignore_above": 256
                            }
                        }
                    },
                    "object": {
                        "type": "keyword",
                        "doc_values": True,  # Оптимизация для filter context
                        "null_value": "_none"
                    },
                    "syntax_ru": {
                        "type": "text",
                        "index": False  # Не индексируем, только хранение
                    },
                    "syntax_en": {
                        "type": "text",
                        "index": False  # Не индексируем, только хранение
                    },
                    "description": {
                        "type": "text",
                        "analyzer": "russian"
                    },
                    "parameters": {
                        "type": "nested",
                        "properties": {
                            "name": {"type": "text"},
                            "type": {
                                "type": "keyword",
                                "doc_values": True
                            },
                            "description": {"type": "text", "analyzer": "russian"},
                            "required": {"type": "boolean"}
                        }
                    },
                    "return_type": {
                        "type": "keyword",
                        "doc_values": True  # Оптимизация для filter context
                    },
                    "version_from": {
                        "type": "keyword",
                        "doc_values": True  # Оптимизация для filter context
                    },
                    "examples": {
                        "type": "text",
                        "analyzer": "russian",
                        "index_options": "docs"  # Минимальная индексация для экономии места
                    },
                    "source_file": {
                        "type": "keyword",
                        "doc_values": True
                    },
                    "full_path": {
                        "type": "keyword",
                        "doc_values": True  # Оптимизация для filter context
                    },
                    "indexed_at": {
                        "type": "date"
                    }
                }
            }
        }

        try:
            await self._client.indices.create(index=self._config.index_name, body=index_config)
            logger.info(f"Создан оптимизированный индекс '{self._config.index_name}'")
            return True
        except Exception as e:
            logger.error(f"Ошибка создания индекса: {e}")
            return False

    async def optimize_index_settings(self) -> bool:
        """
        Оптимизирует настройки индекса после завершения индексации.
        
        Применяется после полной индексации для улучшения производительности поиска.
        """
        if not self._client:
            return False

        try:
            # Возвращаем обычный refresh interval для лучшей актуальности данных
            await self._client.indices.put_settings(
                index=self._config.index_name,
                body={
                    "refresh_interval": "1s"
                }
            )

            # Принудительный merge для оптимизации сегментов
            await self._client.indices.forcemerge(
                index=self._config.index_name,
                max_num_segments=1
            )

            logger.info("Индекс оптимизирован для поиска")
            return True
        except Exception as e:
            logger.error(f"Ошибка оптимизации индекса: {e}")
            return False
    
    async def get_documents_count(self) -> Optional[int]:
        """Получает количество документов в индексе."""
        if not self._client:
            return None
        
        try:
            response = await self._client.count(index=self._config.index_name)
            return response["count"]
        except Exception as e:
            logger.error(f"Ошибка получения количества документов: {e}")
            return None
    
    async def refresh_index(self) -> bool:
        """Принудительно обновляет индекс для немедленного отражения изменений."""
        if not self._client:
            return False
        
        try:
            await self._client.indices.refresh(index=self._config.index_name)
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления индекса: {e}")
            return False
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    @es_circuit_breaker.call
    async def search(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Выполняет поиск в индексе с retry logic и circuit breaker.
        
        Circuit Breaker:
        - При 5 ошибках за 60с → circuit открывается
        - В открытом состоянии запросы отклоняются
        - Через 30с → попытка восстановления (half-open)
        
        Retry logic:
        - Максимум 3 попытки
        - Экспоненциальная задержка: 1s, 2s, 4s
        - Повтор при ConnectionError и Timeout
        
        Args:
            query: Elasticsearch запрос
            
        Returns:
            Результат поиска или None при ошибке
        """
        if not self._client:
            logger.error("Нет подключения к Elasticsearch")
            return None

        try:
            response = await self._client.search(
                index=self._config.index_name,
                body=query
            )
            return response
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            raise  # Перехватывается retry decorator и circuit breaker


# Глобальный экземпляр клиента
es_client = ElasticsearchClient()


# Публичные функции для работы с circuit breaker

def get_circuit_breaker_stats() -> Dict[str, Any]:
    """Получить статистику circuit breaker."""
    return es_circuit_breaker.get_stats()


def reset_circuit_breaker() -> None:
    """Сбросить circuit breaker."""
    es_circuit_breaker.reset()


def get_circuit_breaker_state() -> str:
    """Получить текущее состояние circuit breaker."""
    return es_circuit_breaker.state.value
