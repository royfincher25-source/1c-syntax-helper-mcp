"""Модуль административных маршрутов."""

import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from src.core.cache import cache
from src.core.graceful_shutdown import graceful_shutdown, get_graceful_shutdown
from src.core.task_manager import task_manager
from src.models.doc_models import TaskStatus

router = APIRouter(prefix="", tags=["admin"])


@router.get("/index/status")
async def index_status():
    """Получение статуса индекса Elasticsearch."""
    from src.core.elasticsearch import es_client
    
    index_exists = await es_client.index_exists()
    docs_count = await es_client.get_documents_count() if index_exists else 0
    
    return {
        "index_exists": index_exists,
        "documents_count": docs_count,
        "status": "ready" if index_exists and docs_count > 0 else "empty"
    }


@router.get("/cache/stats")
async def cache_stats():
    """Получение статистики кэша."""
    stats = cache.get_stats()
    return stats


@router.get("/shutdown/status")
async def shutdown_status():
    """Получение статуса процесса выключения."""
    return {
        "is_shutting_down": graceful_shutdown.is_shutting_down,
        "active_requests": graceful_shutdown.active_requests,
        "shutdown_timeout": graceful_shutdown.shutdown_timeout
    }


@router.post("/shutdown/initiate")
async def initiate_shutdown():
    """Инициировать graceful shutdown."""
    if graceful_shutdown.is_shutting_down:
        raise HTTPException(status_code=400, detail="Shutdown already in progress")
    
    asyncio.create_task(graceful_shutdown.shutdown("admin_request"))
    
    return {
        "message": f"Graceful shutdown started. Active requests: {graceful_shutdown.active_requests}"
    }


@router.post("/cache/clear")
async def clear_cache():
    """Очистка кэша."""
    await cache.clear()
    return {"message": "Cache cleared successfully"}


@router.post("/index/rebuild")
async def rebuild_index():
    """
    Запускает фоновую задачу переиндексации.
    
    Возвращает task_id для отслеживания прогресса через /index/task/{task_id}.
    Переиндексация может занимать несколько минут в зависимости от размера HBK-файлов.
    """
    from pathlib import Path
    from src.core.config import settings
    from src.core.elasticsearch import es_client
    from src.parsers.hbk_parser_optimized import HBKParserOptimized
    from src.parsers.indexer import indexer
    from src.parsers.indexer import IndexProgress

    hbk_dir = Path(settings.data.hbk_directory)
    if not hbk_dir.exists():
        raise HTTPException(status_code=404, detail="HBK directory not found")

    hbk_files = list(hbk_dir.glob("*.hbk"))
    if not hbk_files:
        raise HTTPException(status_code=404, detail="No HBK files found")

    hbk_file_path = hbk_files[0]

    # Проверяем, есть ли активные задачи индексации
    if task_manager.get_active_tasks_count() > 0:
        raise HTTPException(
            status_code=409,
            detail="Another indexing task is already running. Please wait for it to complete."
        )

    async def indexing_coroutine():
        """Корутина для фоновой индексации."""
        # Удаляем старый индекс
        if await es_client.index_exists():
            await es_client.delete_index()

        # Парсим и индексируем оптимизированным парсером
        parser = HBKParserOptimized()
        parsed_hbk = await parser.parse_file_async(hbk_file_path)

        if not parsed_hbk or not parsed_hbk.documentation:
            raise RuntimeError("Failed to parse HBK file")

        # Callback для обновления прогресса
        def progress_callback(progress: IndexProgress):
            task = task_manager.get_task(task_id)
            if task:
                task.progress_percent = progress.percent_complete
                task.metadata.update({
                    "indexed_docs": progress.indexed_docs,
                    "total_docs": progress.total_docs,
                    "failed_docs": progress.failed_docs,
                    "current_batch": progress.current_batch,
                    "total_batches": progress.total_batches
                })

        success = await indexer.reindex_all_with_progress(parsed_hbk, progress_callback)

        if not success:
            raise RuntimeError("Failed to rebuild index")

        # Очищаем кэш после успешной переиндексации
        from src.core.cache import cache
        await cache.clear()

        return indexer.metrics.to_dict()

    # Создаем фоновую задачу
    task_id = await task_manager.create_task(
        task_type="index_rebuild",
        coroutine=indexing_coroutine(),
        metadata={
            "hbk_file": hbk_file_path,
            "total_docs": 0,
            "indexed_docs": 0,
            "failed_docs": 0
        }
    )

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Index rebuild task started. Use /index/task/{task_id} to check progress."
    }


@router.get("/index/task/{task_id}")
async def get_index_task_status(task_id: str):
    """
    Получает статус задачи индексации.

    Возвращает прогресс в процентах и метрики.
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status.value,
        "progress_percent": task.progress_percent,
        "created_at": task.created_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "metadata": task.metadata
    }


@router.get("/parse/progress")
async def get_parse_progress():
    """
    Получает прогресс текущего парсинга.

    Возвращает статистику оптимизированного парсера.
    """
    from src.parsers.hbk_parser_optimized import HBKParserOptimized
    
    parser = HBKParserOptimized()
    return parser.get_parse_status()


@router.get("/index/tasks")
async def list_index_tasks(
    limit: int = Query(default=20, ge=1, le=100, description="Максимальное количество задач"),
    status: Optional[str] = Query(default=None, description="Фильтр по статусу")
):
    """Получение списка задач индексации."""
    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Valid values: pending, running, completed, failed, cancelled"
            )
    
    tasks = task_manager.list_tasks(limit=limit, status_filter=status_filter)
    return {"tasks": tasks, "count": len(tasks)}


@router.post("/index/task/{task_id}/cancel")
async def cancel_index_task(task_id: str):
    """Отмена задачи индексации."""
    success = task_manager.cancel_task(task_id)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task {task_id}. It may not exist or already completed."
        )
    
    return {"message": f"Task {task_id} cancellation requested"}
