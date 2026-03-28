"""Модуль управления жизненным циклом приложения."""

import asyncio
from pathlib import Path
from typing import Optional, List, Callable, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.logging import get_logger
from src.core.elasticsearch import es_client
from src.core.cache import cache
from src.core.metrics import get_metrics_collector, get_system_monitor
from src.core.dependency_injection import setup_dependencies
from src.core.graceful_shutdown import graceful_shutdown
from src.parsers.hbk_parser_optimized import HBKParserOptimized
from src.parsers.indexer import indexer

logger = get_logger(__name__)


class LifespanManager:
    """
    Менеджер жизненного цикла приложения.

    Отвечает за:
    - Startup: инициализация всех сервисов
    - Shutdown: корректная остановка всех сервисов
    - Автоиндексация .hbk файлов при запуске
    """

    def __init__(
        self,
        hbk_directory: Optional[str] = None,
        auto_index: bool = True
    ):
        """
        Инициализация менеджера.

        Args:
            hbk_directory: Путь к директории с .hbk файлами
            auto_index: Автоматически индексировать при запуске
        """
        self.hbk_directory = hbk_directory
        self.auto_index = auto_index
        self._background_tasks: List[asyncio.Task] = []

    async def startup(self, app: FastAPI) -> None:
        """
        Выполняет startup инициализацию.

        Этапы:
        1. Настройка dependency injection
        2. Запуск системного мониторинга
        3. Запуск кэша
        4. Подключение к Elasticsearch
        5. Автоиндексация (если включена)
        """
        metrics = get_metrics_collector()
        monitor = get_system_monitor()

        logger.info("запуск MCP сервера синтаксис-помощника 1С")

        # Настройка dependency injection
        setup_dependencies()

        # Запуск мониторинга системы (если включено)
        import os
        monitor_enabled = os.getenv("SYSTEM_MONITORING", "true").lower() == "true"
        if monitor_enabled:
            await monitor.start_monitoring(interval=120)
            logger.info("System monitoring started (120s interval)")
        else:
            logger.info("System monitoring disabled")

        # Запуск кэша
        await cache.start()
        logger.info("Кэш запущен")

        # Подключаемся к Elasticsearch
        connected = await es_client.connect()
        if not connected:
            logger.error("Не удалось подключиться к Elasticsearch")
            await metrics.increment("startup.elasticsearch.connection_failed")
        else:
            logger.info("Успешно подключились к Elasticsearch")
            await metrics.increment("startup.elasticsearch.connection_success")

            # Проверяем наличие .hbk файла и запускаем автоиндексацию
            if self.auto_index:
                index_task = asyncio.create_task(
                    self._auto_index_on_startup(),
                    name="auto_index_task"
                )
                self._background_tasks.append(index_task)
                graceful_shutdown.register_background_task(index_task)

        # Инициализация хранилища SSE сессий
        app.state.sse_sessions = {}
        logger.info("SSE sessions storage initialized")

        # Регистрируем cleanup callbacks
        graceful_shutdown.register_cleanup_callback(monitor.stop_monitoring)
        graceful_shutdown.register_cleanup_callback(cache.stop)

        await metrics.increment("startup.completed")

    async def shutdown(self, app: FastAPI) -> None:
        """
        Выполняет shutdown очистку.

        Этапы:
        1. Очистка SSE сессий
        2. Ожидание фоновых задач
        3. Вызов cleanup callbacks (через graceful_shutdown)
        """
        logger.info("Starting shutdown cleanup...")

        # Очистка SSE сессий
        if hasattr(app.state, 'sse_sessions'):
            session_count = len(app.state.sse_sessions)
            if session_count > 0:
                logger.info(f"Cleaning up {session_count} SSE sessions")
                
                # Отправляем уведомление о закрытии всем сессиям
                shutdown_notification = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "result": {"shutdown": True}
                }
                
                for session_id, queue in list(app.state.sse_sessions.items()):
                    try:
                        queue.put_nowait(shutdown_notification)
                    except asyncio.QueueFull:
                        logger.debug(f"Queue full for session {session_id}, skipping notification")
                
                # Очищаем хранилище сессий
                app.state.sse_sessions.clear()
                logger.info(f"SSE sessions cleaned up: {session_count} sessions")

        logger.info("Lifespan shutdown завершён")

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """
        Context manager для управления жизненным циклом.

        Использование:
            app = FastAPI(lifespan=lifespan_manager.lifespan)
        """
        await self.startup(app)
        try:
            yield
        finally:
            await self.shutdown(app)

    async def _auto_index_on_startup(self) -> None:
        """
        Автоматическая индексация при запуске, если найден .hbk файл.

        Проверяет:
        - Существует ли директория с .hbk файлами
        - Есть ли .hbk файлы в директории
        - Пуст ли индекс Elasticsearch
        """
        try:
            if not self.hbk_directory:
                logger.warning("Директория .hbk файлов не указана")
                return

            hbk_dir = Path(self.hbk_directory)
            if not hbk_dir.exists():
                logger.warning(f"Директория .hbk файлов не найдена: {hbk_dir}")
                return

            hbk_files = list(hbk_dir.glob("*.hbk"))
            if not hbk_files:
                logger.info(f"Файлы .hbk не найдены в {hbk_dir}")
                return

            # Проверяем, нужна ли индексация
            index_exists = await es_client.index_exists()
            docs_count = await es_client.get_documents_count() if index_exists else 0

            if index_exists and docs_count and docs_count > 0:
                logger.info(f"Индекс существует с {docs_count} документами. Пропускаем автоиндексацию.")
                return

            # Запускаем индексацию первого найденного файла
            hbk_file = hbk_files[0]
            logger.info(f"Запускаем автоматическую индексацию файла: {hbk_file}")

            success = await self._index_hbk_file(str(hbk_file))
            if success:
                logger.info("Автоматическая индексация завершена успешно")
            else:
                logger.error("Ошибка автоматической индексации")

        except Exception as e:
            logger.error(f"Ошибка при автоматической индексации: {e}")

    async def _index_hbk_file(self, file_path: str) -> bool:
        """
        Индексирует .hbk файл в Elasticsearch.

        Args:
            file_path: Путь к .hbk файлу

        Returns:
            True если индексация успешна
        """
        try:
            logger.info(f"Начинаем индексацию файла: {file_path}")

            # Парсим .hbk файл оптимизированным парсером
            parser = HBKParserOptimized()
            parsed_hbk = await parser.parse_file_async(file_path)

            if not parsed_hbk:
                logger.error("Ошибка парсинга .hbk файла")
                return False

            if not parsed_hbk.documentation:
                logger.warning("В файле не найдена документация для индексации")
                return False

            logger.info(f"Найдено {len(parsed_hbk.documentation)} документов для индексации")

            # Индексируем в Elasticsearch
            success = await indexer.reindex_all(parsed_hbk)

            if success:
                docs_count = await es_client.get_documents_count()
                logger.info(f"Индексация завершена. Документов в индексе: {docs_count}")

            return success

        except Exception as e:
            logger.error(f"Ошибка индексации файла {file_path}: {e}")
            return False


# Глобальный экземпляр менеджера
_lifespan_manager: Optional[LifespanManager] = None


def get_lifespan_manager(
    hbk_directory: Optional[str] = None,
    auto_index: bool = True
) -> LifespanManager:
    """
    Получить глобальный экземпляр LifespanManager.

    Args:
        hbk_directory: Путь к директории с .hbk файлами
        auto_index: Автоматически индексировать при запуске

    Returns:
        Экземпляр LifespanManager
    """
    global _lifespan_manager

    if _lifespan_manager is None:
        _lifespan_manager = LifespanManager(
            hbk_directory=hbk_directory,
            auto_index=auto_index
        )

    return _lifespan_manager


def reset_lifespan_manager() -> None:
    """Сбросить глобальный экземпляр (для тестов)."""
    global _lifespan_manager
    _lifespan_manager = None
