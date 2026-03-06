"""Graceful Shutdown для корректной остановки приложения."""

import signal
import asyncio
import time
from typing import Optional, Callable, Any, List
from contextlib import asynccontextmanager

from src.core.logging import get_logger
from src.core.elasticsearch import es_client
from src.core.circuit_breaker import es_circuit_breaker

logger = get_logger(__name__)


class GracefulShutdown:
    """
    Менеджер корректной остановки приложения.
    
    Обрабатывает:
    - Сигналы SIGTERM/SIGINT
    - Завершение текущих запросов
    - Закрытие соединений с ES
    - Остановку кэша и фоновых задач
    - Очистку ресурсов
    """
    
    def __init__(self, shutdown_timeout: int = 30):
        """
        Инициализация менеджера.
        
        Args:
            shutdown_timeout: Таймаут ожидания завершения запросов (сек)
        """
        self.shutdown_timeout = shutdown_timeout
        self._shutdown_event = asyncio.Event()
        self._is_shutting_down = False
        self._active_requests = 0
        self._background_tasks: List[asyncio.Task] = []
        self._cleanup_callbacks: List[Callable] = []
        
        # Регистрация обработчиков сигналов
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Настраивает обработчики сигналов SIGTERM и SIGINT."""
        try:
            # Регистрируем обработчики только в главном потоке
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
            logger.info("Обработчики сигналов SIGTERM/SIGINT зарегистрированы")
        except ValueError:
            # signal.signal не работает в неблокирующем потоке
            logger.warning("Не удалось зарегистрировать обработчики сигналов (не главный поток)")
        except Exception as e:
            logger.error(f"Ошибка регистрации обработчиков сигналов: {e}")
    
    def _signal_handler(self, signum, frame) -> None:
        """Обработчик сигналов."""
        signal_name = signal.Signals(signum).name
        logger.info(f"Получен сигнал {signal_name} (signum={signum})")
        
        # Запускаем асинхронный shutdown
        asyncio.create_task(self.shutdown(f"signal_{signal_name}"))
    
    def register_background_task(self, task: asyncio.Task) -> None:
        """
        Зарегистрировать фоновую задачу для последующей остановки.
        
        Args:
            task: Фоновая задача asyncio
        """
        self._background_tasks.append(task)
        logger.debug(f"Зарегистрирована фоновая задача: {task.get_name()}")
    
    def register_cleanup_callback(self, callback: Callable) -> None:
        """
        Зарегистрировать callback для очистки ресурсов.
        
        Args:
            callback: Функция очистки
        """
        self._cleanup_callbacks.append(callback)
        logger.debug(f"Зарегистрирован callback очистки: {callback.__name__}")
    
    def increment_active_requests(self) -> None:
        """Увеличить счётчик активных запросов."""
        self._active_requests += 1
    
    def decrement_active_requests(self) -> None:
        """Уменьшить счётчик активных запросов."""
        self._active_requests = max(0, self._active_requests - 1)
        
        # Если это был последний запрос и мы в shutdown, сигнализируем
        if self._active_requests == 0 and self._is_shutting_down:
            self._shutdown_event.set()
    
    @property
    def is_shutting_down(self) -> bool:
        """Проверить идёт ли shutdown."""
        return self._is_shutting_down
    
    @property
    def active_requests(self) -> int:
        """Получить количество активных запросов."""
        return self._active_requests
    
    async def shutdown(self, reason: str = "shutdown") -> None:
        """
        Корректная остановка приложения.
        
        Этапы:
        1. Установка флага shutdown (новые запросы отклоняются)
        2. Ожидание завершения текущих запросов (до timeout)
        3. Отмена фоновых задач
        4. Закрытие соединений с ES
        5. Остановка кэша
        6. Вызов cleanup callbacks
        7. Финальное логирование
        
        Args:
            reason: Причина shutdown (для логирования)
        """
        if self._is_shutting_down:
            logger.warning(f"Shutdown уже выполняется (повторный вызов: {reason})")
            return
        
        self._is_shutting_down = True
        start_time = time.time()
        
        logger.info(f"Начало graceful shutdown (причина: {reason})")
        logger.info(f"Активных запросов: {self._active_requests}")
        logger.info(f"Фоновых задач: {len(self._background_tasks)}")
        
        # Этап 1: Ожидание завершения текущих запросов
        if self._active_requests > 0:
            logger.info(f"Ожидание завершения {self._active_requests} запросов (timeout: {self.shutdown_timeout}s)")
            
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.shutdown_timeout
                )
                logger.info("Все запросы завершены")
            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout ожидания запросов ({self.shutdown_timeout}s). "
                    f"Осталось активных: {self._active_requests}"
                )
        else:
            logger.info("Нет активных запросов")
        
        # Этап 2: Отмена фоновых задач
        if self._background_tasks:
            logger.info(f"Отмена {len(self._background_tasks)} фоновых задач")
            
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
            
            # Ждём завершения задач
            results = await asyncio.gather(*self._background_tasks, return_exceptions=True)
            
            cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
            errors = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError))
            
            logger.info(f"Фоновые задачи завершены: отменено={cancelled}, ошибок={errors}")
        
        # Этап 3: Закрытие соединений с ES
        logger.info("Закрытие соединений с Elasticsearch")
        try:
            await es_client.disconnect()
            logger.info("Elasticsearch отключён")
        except Exception as e:
            logger.error(f"Ошибка отключения Elasticsearch: {e}")
        
        # Этап 4: Сброс circuit breaker
        logger.info("Сброс circuit breaker")
        es_circuit_breaker.reset()
        
        # Этап 5: Вызов cleanup callbacks
        if self._cleanup_callbacks:
            logger.info(f"Вызов {len(self._cleanup_callbacks)} cleanup callbacks")
            
            for callback in self._cleanup_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception as e:
                    logger.error(f"Ошибка cleanup callback {callback.__name__}: {e}")
        
        # Финальное логирование
        duration = time.time() - start_time
        logger.info(f"Graceful shutdown завершён за {duration:.2f}s")
        
        # Выход из приложения (если в главном потоке)
        # asyncio.get_event_loop().stop()


# Глобальный экземпляр
graceful_shutdown = GracefulShutdown(shutdown_timeout=30)


def get_graceful_shutdown() -> GracefulShutdown:
    """Получить глобальный экземпляр GracefulShutdown."""
    return graceful_shutdown


@asynccontextmanager
async def request_context():
    """
    Context manager для отслеживания активных запросов.
    
    Использование:
        async with request_context():
            # обработка запроса
    """
    graceful_shutdown.increment_active_requests()
    try:
        yield
    finally:
        graceful_shutdown.decrement_active_requests()


def check_shutdown() -> bool:
    """
    Проверить идёт ли shutdown.
    
    Returns:
        True если shutdown выполняется
    """
    return graceful_shutdown.is_shutting_down
