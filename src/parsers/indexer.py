"""Индексатор документации в Elasticsearch."""

import time
from typing import List, Dict, Any, Optional, Callable
import asyncio
from datetime import datetime
from dataclasses import dataclass, field

from src.models.doc_models import Documentation, ParsedHBK
from src.core.elasticsearch import es_client
from src.core.logging import get_logger
from src.core.cache import cache

logger = get_logger(__name__)


@dataclass
class IndexProgress:
    """Прогресс индексации."""
    total_docs: int = 0
    indexed_docs: int = 0
    failed_docs: int = 0
    current_batch: int = 0
    total_batches: int = 0
    elapsed_time: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    @property
    def percent_complete(self) -> float:
        if self.total_docs == 0:
            return 0.0
        return (self.indexed_docs / self.total_docs) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_docs": self.total_docs,
            "indexed_docs": self.indexed_docs,
            "failed_docs": self.failed_docs,
            "current_batch": self.current_batch,
            "total_batches": self.total_batches,
            "percent_complete": round(self.percent_complete, 1),
            "elapsed_time_seconds": round(self.elapsed_time, 2),
            "errors_count": len(self.errors)
        }


class IndexerMetrics:
    """Метрики индексации."""
    
    def __init__(self):
        self.total_docs = 0
        self.indexed_docs = 0
        self.failed_docs = 0
        self.retries = 0
        self.start_time: float = 0
        self.end_time: float = 0
    
    @property
    def success_rate(self) -> float:
        if self.total_docs == 0:
            return 0.0
        return (self.indexed_docs / self.total_docs) * 100
    
    @property
    def duration(self) -> float:
        if self.end_time == 0:
            return time.time() - self.start_time
        return self.end_time - self.start_time
    
    @property
    def docs_per_second(self) -> float:
        dur = self.duration
        if dur == 0:
            return 0.0
        return self.indexed_docs / dur
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_docs": self.total_docs,
            "indexed_docs": self.indexed_docs,
            "failed_docs": self.failed_docs,
            "retries": self.retries,
            "success_rate_percent": round(self.success_rate, 2),
            "duration_seconds": round(self.duration, 2),
            "docs_per_second": round(self.docs_per_second, 2)
        }


class ElasticsearchIndexer:
    """Индексатор документации в Elasticsearch."""
    
    def __init__(self):
        self.batch_size = 100
        self.max_retries = 3
        self.retry_delay = 1.0
        self._metrics = IndexerMetrics()
        self._progress = IndexProgress()
        self._progress_callback: Optional[Callable[[IndexProgress], None]] = None
    
    @property
    def metrics(self) -> IndexerMetrics:
        return self._metrics
    
    @property
    def progress(self) -> IndexProgress:
        return self._progress
    
    def set_progress_callback(self, callback: Callable[[IndexProgress], None]) -> None:
        """Устанавливает callback для обновления прогресса."""
        self._progress_callback = callback
    
    def _update_progress(
        self,
        indexed_docs: int = 0,
        failed_docs: int = 0,
        current_batch: int = 0,
        total_batches: int = 0,
        error: str = None
    ) -> None:
        """Обновляет прогресс и вызывает callback."""
        self._progress.indexed_docs = indexed_docs
        self._progress.failed_docs = failed_docs
        self._progress.current_batch = current_batch
        self._progress.total_batches = total_batches
        self._progress.elapsed_time = time.time() - self._metrics.start_time
        
        if error:
            self._progress.errors.append(error)
        
        if self._progress_callback:
            self._progress_callback(self._progress)
    
    async def index_documentation(
        self,
        parsed_hbk: ParsedHBK,
        progress_callback: Optional[Callable[[IndexProgress], None]] = None
    ) -> bool:
        """
        Индексирует документацию из ParsedHBK в Elasticsearch.
        
        Args:
            parsed_hbk: Распарсенные данные HBK
            progress_callback: Опциональный callback для обновления прогресса
            
        Использует оптимизированную пакетную индексацию с:
        - Увеличенным refresh_interval (30s) для скорости
        - Async translog для лучшей производительности
        - Последующей оптимизацией сегментов
        - Retry логикой для отдельных документов
        """
        if progress_callback:
            self._progress_callback = progress_callback
        
        if not await es_client.is_connected():
            logger.error("Нет подключения к Elasticsearch")
            return False

        self._metrics = IndexerMetrics()
        self._progress = IndexProgress()
        self._metrics.start_time = time.time()
        self._progress.total_docs = len(parsed_hbk.documentation)

        try:
            if not await es_client.index_exists():
                logger.info("Создаем индекс Elasticsearch")
                await es_client.create_index()

            total_docs = len(parsed_hbk.documentation)
            indexed_count = 0
            failed_count = 0
            total_batches = (total_docs + self.batch_size - 1) // self.batch_size

            self._metrics.total_docs = total_docs
            logger.info(f"Начало индексации {total_docs} документов ({total_batches} батчей)")

            for i in range(0, total_docs, self.batch_size):
                batch = parsed_hbk.documentation[i:i + self.batch_size]
                batch_num = (i // self.batch_size) + 1

                result = await self._index_batch_with_retry(batch)
                if result["success"]:
                    indexed_count += result["indexed"]
                else:
                    failed_count += result["failed"]
                    logger.warning(
                        f"Батч {batch_num}/{total_batches}: "
                        f"индексировано={result['indexed']}, ошибки={result['failed']}"
                    )

                self._update_progress(
                    indexed_docs=indexed_count,
                    failed_docs=failed_count,
                    current_batch=batch_num,
                    total_batches=total_batches
                )

                if batch_num % 10 == 0 or batch_num == total_batches:
                    logger.info(
                        f"Индексация прогресс: {batch_num}/{total_batches} батчей, "
                        f"успешно={indexed_count}, ошибки={failed_count}"
                    )

            self._metrics.indexed_docs = indexed_count
            self._metrics.failed_docs = failed_count
            self._metrics.end_time = time.time()

            logger.info("Оптимизация индекса после индексации...")
            await es_client.optimize_index_settings()
            await es_client.refresh_index()

            logger.info(
                f"Индексация завершена: {indexed_count}/{total_docs} документов "
                f"({self._metrics.docs_per_second:.1f} docs/sec)"
            )
            return indexed_count == total_docs

        except Exception as e:
            logger.error(f"Ошибка индексации документации: {e}")
            return False
    
    async def _index_batch_with_retry(self, documents: List[Documentation]) -> Dict[str, Any]:
        """Индексирует батч с retry логикой для отдельных документов."""
        if not documents:
            return {"success": True, "indexed": 0, "failed": 0}
        
        success_docs = []
        failed_docs = list(documents)
        
        for attempt in range(self.max_retries):
            if not failed_docs:
                break
            
            if attempt > 0:
                self._metrics.retries += 1
                await asyncio.sleep(self.retry_delay * attempt)
            
            result = await self._index_batch(failed_docs)
            
            if result:
                success_docs.extend(failed_docs)
                failed_docs = []
            else:
                logger.debug(f"Retry batch: attempt {attempt + 1}/{self.max_retries}")
        
        if failed_docs:
            logger.error(f"Не удалось проиндексировать {len(failed_docs)} документов после {self.max_retries} попыток")
            for doc in failed_docs:
                logger.error(f"  - Неудачный документ: {doc.id} ({doc.name})")
        
        return {
            "success": len(failed_docs) == 0,
            "indexed": len(success_docs),
            "failed": len(failed_docs)
        }
    
    async def _index_batch(self, documents: List[Documentation]) -> bool:
        """Индексирует батч документов."""
        if not documents:
            return True
        
        try:
            # Подготавливаем bulk запрос
            bulk_body = []
            
            for doc in documents:
                # Добавляем действие индексации
                bulk_body.append({
                    "index": {
                        "_index": es_client._config.index_name,
                        "_id": doc.id
                    }
                })
                
                # Добавляем сам документ
                bulk_body.append(self._prepare_document(doc))
            
            # Выполняем bulk запрос
            if es_client._client:
                response = await es_client._client.bulk(body=bulk_body)
                
                # Проверяем ошибки
                if response.get("errors"):
                    logger.warning("Есть ошибки в bulk запросе")
                    for item in response.get("items", []):
                        if "index" in item and "error" in item["index"]:
                            logger.error(f"Ошибка индексации документа: {item['index']['error']}")
                
                return not response.get("errors", True)
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка выполнения bulk запроса: {e}")
            return False
    
    def _prepare_document(self, doc: Documentation) -> Dict[str, Any]:
        """Подготавливает документ для индексации в Elasticsearch."""
        es_doc = {
            "id": doc.id,
            "type": doc.type.value,
            "name": doc.name,
            "object": doc.object,
            "syntax_ru": doc.syntax_ru,
            "syntax_en": doc.syntax_en,
            "description": doc.description,
            "parameters": [
                {
                    "name": param.name,
                    "type": param.type,
                    "description": param.description,
                    "required": param.required
                }
                for param in doc.parameters
            ],
            "return_type": doc.return_type,
            "version_from": doc.version_from,
            "examples": doc.examples,
            "source_file": doc.source_file,
            "full_path": doc.full_path,
            "indexed_at": datetime.now().isoformat()
        }
        
        return es_doc
    
    async def reindex_all(self, parsed_hbk: ParsedHBK) -> bool:
        """Переиндексирует всю документацию (удаляет старый индекс и создает новый)."""
        return await self.reindex_all_with_progress(parsed_hbk, progress_callback=None)

    async def reindex_all_with_progress(
        self,
        parsed_hbk: ParsedHBK,
        progress_callback: Optional[Callable[[IndexProgress], None]] = None
    ) -> bool:
        """
        Переиндексирует всю документацию с callback для обновления прогресса.
        
        Args:
            parsed_hbk: Распарсенные данные HBK
            progress_callback: Callback для обновления прогресса
            
        Returns:
            True если индексация успешна, False иначе
        """
        try:
            # Удаляем старый индекс если существует
            if await es_client.index_exists():
                if es_client._client:
                    await es_client._client.indices.delete(index=es_client._config.index_name)

            # Создаем новый индекс
            await es_client.create_index()

            # Инвалидируем кэш (переиндексация означает устаревание данных)
            await cache.clear()
            logger.info("Кэш инвалидирован после переиндексации")

            # Индексируем документы с прогрессом
            return await self.index_documentation(parsed_hbk, progress_callback=progress_callback)

        except Exception as e:
            logger.error(f"Ошибка переиндексации: {e}")
            return False
    
    async def get_index_stats(self) -> Optional[Dict[str, Any]]:
        """Получает статистику индекса."""
        try:
            if not await es_client.is_connected():
                return None
            
            if not await es_client.index_exists():
                return {"exists": False, "documents_count": 0}
            
            # Получаем статистику
            if es_client._client:
                stats_response = await es_client._client.indices.stats(
                    index=es_client._config.index_name
                )
                
                count_response = await es_client._client.count(
                    index=es_client._config.index_name
                )
                
                return {
                    "exists": True,
                    "documents_count": count_response.get("count", 0),
                    "size_in_bytes": stats_response["indices"][es_client._config.index_name]["total"]["store"]["size_in_bytes"],
                    "index_name": es_client._config.index_name
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики индекса: {e}")
            return None
    
    async def search_documents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Простой поиск документов для тестирования."""
        try:
            if not await es_client.is_connected():
                return []
            
            search_query = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["name^3", "full_path^2", "description", "syntax_ru"],
                        "type": "best_fields"
                    }
                },
                "size": limit,
                "sort": [
                    {"_score": {"order": "desc"}}
                ]
            }
            
            response = await es_client.search(search_query)
            
            if response and "hits" in response:
                return [hit["_source"] for hit in response["hits"]["hits"]]
            
            return []
            
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            return []


# Глобальный экземпляр индексатора
indexer = ElasticsearchIndexer()
