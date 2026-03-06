"""Circuit Breaker паттерн для устойчивости к сбоям Elasticsearch."""

from typing import Optional, Callable, Any, Dict
from enum import Enum
import time
import asyncio
from functools import wraps

from src.core.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Состояния Circuit Breaker."""
    CLOSED = "closed"      # Нормальная работа, запросы проходят
    OPEN = "open"          # Сбой, запросы блокируются
    HALF_OPEN = "half_open"  # Пробный запрос для проверки восстановления


class CircuitBreakerError(Exception):
    """Базовое исключение Circuit Breaker."""
    pass


class CircuitOpenError(CircuitBreakerError):
    """Circuit открыт, запрос отклонён."""
    pass


class CircuitBreaker:
    """
    Circuit Breaker для защиты от каскадных сбоев.
    
    Состояния:
    - CLOSED: Нормальная работа. Запросы проходят, считаем ошибки.
    - OPEN: Сбой. Запросы блокируются, ждём timeout.
    - HALF_OPEN: Проверка. Один пробный запрос для проверки восстановления.
    
    Логика переходов:
    - CLOSED → OPEN: При превышении failure_threshold ошибок за failure_window
    - OPEN → HALF_OPEN: После recovery_timeout секунд
    - HALF_OPEN → CLOSED: При успешном запросе
    - HALF_OPEN → OPEN: При ошибке запроса
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        failure_window: int = 60,
        expected_exception: type = Exception
    ):
        """
        Инициализация Circuit Breaker.
        
        Args:
            name: Имя circuit breaker (для логирования)
            failure_threshold: Порог ошибок для открытия circuit
            recovery_timeout: Время ожидания перед попыткой восстановления (сек)
            failure_window: Окно времени для подсчёта ошибок (сек)
            expected_exception: Тип исключения для отслеживания
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_window = failure_window
        self.expected_exception = expected_exception
        
        # Состояние
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change_time: float = time.time()
        
        # Статистика
        self._total_requests = 0
        self._total_failures = 0
        self._total_successes = 0
        self._total_rejections = 0  # Отклонённые запросы (circuit open)

    @property
    def state(self) -> CircuitState:
        """Получить текущее состояние."""
        # Проверяем не пора ли перейти из OPEN в HALF_OPEN
        if self._state == CircuitState.OPEN:
            time_since_open = time.time() - self._last_state_change_time
            if time_since_open >= self.recovery_timeout:
                logger.info(
                    f"CircuitBreaker '{self.name}': переход из OPEN в HALF_OPEN "
                    f"(прошло {time_since_open:.1f}с)"
                )
                self._set_state(CircuitState.HALF_OPEN)
        
        return self._state

    @property
    def is_closed(self) -> bool:
        """Circuit закрыт (нормальная работа)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Circuit открыт (сбой)."""
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Circuit в полуоткрытом состоянии (проверка)."""
        return self._state == CircuitState.HALF_OPEN

    def _set_state(self, new_state: CircuitState) -> None:
        """Установить новое состояние."""
        old_state = self._state
        self._state = new_state
        self._last_state_change_time = time.time()
        
        logger.info(
            f"CircuitBreaker '{self.name}': {old_state.value} → {new_state.value}"
        )

    def _record_success(self) -> None:
        """Записать успешный запрос."""
        self._success_count += 1
        self._total_successes += 1
        self._total_requests += 1
        
        if self._state == CircuitState.HALF_OPEN:
            # Успех в HALF_OPEN → закрываем circuit
            logger.info(
                f"CircuitBreaker '{self.name}': успешный запрос в HALF_OPEN, "
                f"переход в CLOSED"
            )
            self._set_state(CircuitState.CLOSED)
            self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            # Уменьшаем счётчик ошибок (постепенное восстановление)
            if self._failure_count > 0:
                self._failure_count = max(0, self._failure_count - 1)

    def _record_failure(self) -> None:
        """Записать неудачный запрос."""
        self._failure_count += 1
        self._total_failures += 1
        self._total_requests += 1
        self._last_failure_time = time.time()
        
        if self._state == CircuitState.HALF_OPEN:
            # Ошибка в HALF_OPEN → снова открываем circuit
            logger.warning(
                f"CircuitBreaker '{self.name}': ошибка в HALF_OPEN, "
                f"переход в OPEN"
            )
            self._set_state(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            # Проверяем не превышен ли порог
            if self._failure_count >= self.failure_threshold:
                logger.error(
                    f"CircuitBreaker '{self.name}': превышен порог ошибок "
                    f"({self._failure_count}/{self.failure_threshold}), "
                    f"переход в OPEN"
                )
                self._set_state(CircuitState.OPEN)

    def _is_failure_window_expired(self) -> bool:
        """Проверить истекло ли окно ошибок."""
        if self._last_failure_time is None:
            return True
        
        return (time.time() - self._last_failure_time) > self.failure_window

    def call(self, func: Callable) -> Callable:
        """
        Decorator для защиты функции circuit breaker.
        
        Args:
            func: Функция для защиты
            
        Returns:
            Обёрнутая функция
        """
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Проверяем состояние
            current_state = self.state
            
            if current_state == CircuitState.OPEN:
                # Circuit открыт - отклоняем запрос
                self._total_rejections += 1
                logger.warning(
                    f"CircuitBreaker '{self.name}': запрос отклонён (circuit open)"
                )
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is open. "
                    f"Try again in {self.recovery_timeout}s"
                )
            
            try:
                # Выполняем запрос
                result = await func(*args, **kwargs)
                self._record_success()
                return result
                
            except self.expected_exception as e:
                # Ошибка типа expected_exception
                self._record_failure()
                raise
            except Exception as e:
                # Другие ошибки - тоже записываем как failure
                self._record_failure()
                raise
        
        return wrapper

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику работы circuit breaker."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_requests": self._total_requests,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "total_rejections": self._total_rejections,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self._last_failure_time,
            "last_state_change_time": self._last_state_change_time
        }

    def reset(self) -> None:
        """Сбросить circuit breaker в начальное состояние."""
        logger.info(f"CircuitBreaker '{self.name}': сброс")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._last_state_change_time = time.time()
        self._total_requests = 0
        self._total_failures = 0
        self._total_successes = 0
        self._total_rejections = 0


# Глобальный экземпляр для Elasticsearch
es_circuit_breaker = CircuitBreaker(
    name="elasticsearch",
    failure_threshold=5,
    recovery_timeout=30,
    failure_window=60,
    expected_exception=Exception
)
