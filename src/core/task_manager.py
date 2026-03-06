"""Менеджер фоновых задач для асинхронных операций."""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional, Callable, Any, Coroutine
from dataclasses import dataclass, field

from src.models.doc_models import TaskStatus, IndexingTask
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BackgroundTask:
    """Представление фоновой задачи."""
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress_percent: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    _task: Optional[asyncio.Task] = None

    def to_indexing_task(self) -> IndexingTask:
        """Конвертирует в IndexingTask для API ответа."""
        return IndexingTask(
            task_id=self.task_id,
            status=self.status.value,
            created_at=self.created_at.isoformat(),
            started_at=self.started_at.isoformat() if self.started_at else None,
            completed_at=self.completed_at.isoformat() if self.completed_at else None,
            progress_percent=round(self.progress_percent, 2),
            indexed_docs=self.metadata.get("indexed_docs", 0),
            total_docs=self.metadata.get("total_docs", 0),
            failed_docs=self.metadata.get("failed_docs", 0),
            error_message=self.error_message,
            hbk_file=self.metadata.get("hbk_file")
        )


class BackgroundTaskManager:
    """
    Менеджер фоновых задач.

    Позволяет запускать долгие операции в фоне и отслеживать их прогресс.
    """

    def __init__(self, max_concurrent_tasks: int = 3):
        self._tasks: Dict[str, BackgroundTask] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._max_tasks = max_concurrent_tasks

    async def create_task(
        self,
        task_type: str,
        coroutine: Coroutine[Any, Any, Any],
        metadata: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[float, Dict[str, Any]], None]] = None
    ) -> str:
        """
        Создает и запускает фоновую задачу.

        Args:
            task_type: Тип задачи (например, "index_rebuild")
            coroutine: Асинхронная корутина для выполнения
            metadata: Дополнительные метаданные задачи
            progress_callback: Callback для обновления прогресса (progress_percent, metadata_delta)

        Returns:
            task_id: Уникальный идентификатор задачи
        """
        task_id = str(uuid.uuid4())

        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            metadata=metadata or {}
        )

        self._tasks[task_id] = task

        # Запускаем задачу в фоне
        async_task = asyncio.create_task(
            self._run_task(task, coroutine, progress_callback)
        )
        task._task = async_task

        logger.info(f"Создана фоновая задача {task_id} типа {task_type}")
        return task_id

    async def _run_task(
        self,
        task: BackgroundTask,
        coroutine: Coroutine[Any, Any, Any],
        progress_callback: Optional[Callable[[float, Dict[str, Any]], None]]
    ) -> None:
        """Выполняет фоновую задачу с обработкой ошибок."""
        async with self._semaphore:
            try:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                logger.info(f"Задача {task.task_id} запущена")

                # Обертываем корутину для перехвата прогресса
                result = await coroutine

                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                task.progress_percent = 100.0
                logger.info(f"Задача {task.task_id} завершена успешно")

            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                logger.warning(f"Задача {task.task_id} отменена")
                raise

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error_message = str(e)
                logger.error(f"Задача {task.task_id} failed: {e}")

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Получает задачу по ID."""
        return self._tasks.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[IndexingTask]:
        """Получает статус задачи в формате API ответа."""
        task = self._tasks.get(task_id)
        if task:
            return task.to_indexing_task()
        return None

    def list_tasks(self, limit: int = 20, status_filter: Optional[TaskStatus] = None) -> list[IndexingTask]:
        """
        Получает список последних задач.

        Args:
            limit: Максимальное количество задач
            status_filter: Фильтр по статусу (опционально)

        Returns:
            Список задач, отсортированных по времени создания (новые первые)
        """
        tasks = list(self._tasks.values())

        # Фильтруем по статусу если нужно
        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]

        # Сортируем по времени создания (новые первые)
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        # Возвращаем limit задач
        return [t.to_indexing_task() for t in tasks[:limit]]

    def cancel_task(self, task_id: str) -> bool:
        """
        Отменяет выполнение задачи.

        Args:
            task_id: ID задачи для отмены

        Returns:
            True если задача была отменена, False если задача не найдена или уже завершена
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            logger.warning(f"Невозможно отменить задачу {task_id} в статусе {task.status}")
            return False

        if task._task:
            task._task.cancel()
            logger.info(f"Задача {task_id} отменена пользователем")
            return True

        return False

    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Optional[IndexingTask]:
        """
        Ждет завершения задачи.

        Args:
            task_id: ID задачи
            timeout: Таймаут ожидания в секундах

        Returns:
            Статус задачи после завершения, None если задача не найдена
        """
        task = self._tasks.get(task_id)
        if not task or not task._task:
            return None

        try:
            await asyncio.wait_for(task._task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Таймаут ожидания задачи {task_id}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Ошибка ожидания задачи {task_id}: {e}")

        return task.to_indexing_task()

    def get_active_tasks_count(self) -> int:
        """Получает количество активных задач."""
        return sum(
            1 for t in self._tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        )

    def cleanup_completed(self, max_age_seconds: int = 3600) -> int:
        """
        Удаляет завершенные задачи старше указанного возраста.

        Args:
            max_age_seconds: Максимальный возраст задач в секундах

        Returns:
            Количество удаленных задач
        """
        now = datetime.now()
        to_remove = []

        for task_id, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                completed_at = task.completed_at or task.created_at
                age = (now - completed_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]

        if to_remove:
            logger.info(f"Удалено {len(to_remove)} завершенных задач")

        return len(to_remove)


# Глобальный экземпляр менеджера задач
task_manager = BackgroundTaskManager(max_concurrent_tasks=1)
