"""Тесты Circuit Breaker для Elasticsearch."""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch

from src.core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    CircuitBreakerError
)


class TestCircuitBreakerStates:
    """Тесты состояний Circuit Breaker."""

    def test_initial_state_is_closed(self):
        """Проверка что начальное состояние CLOSED."""
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False
        assert cb.is_half_open is False

    def test_state_transitions_to_open_after_failures(self):
        """Проверка перехода в OPEN после превышения порога ошибок."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        
        # Имитируем ошибки
        for i in range(3):
            cb._record_failure()
        
        # Circuit должен открыться
        assert cb.state == CircuitState.OPEN
        assert cb.is_open is True

    def test_state_transitions_to_half_open_after_timeout(self):
        """Проверка перехода в HALF_OPEN после recovery_timeout."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=1)
        
        # Открываем circuit
        cb._record_failure()
        assert cb.state == CircuitState.OPEN
        
        # Ждём timeout
        time.sleep(1.1)
        
        # Проверяем что перешёл в HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_half_open is True

    def test_half_open_to_closed_on_success(self):
        """Проверка перехода из HALF_OPEN в CLOSED при успехе."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.1)
        
        # Открываем circuit
        cb._record_failure()
        assert cb.state == CircuitState.OPEN
        
        # Ждём timeout
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN
        
        # Записываем успех
        cb._record_success()
        
        # Circuit должен закрыться
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Проверка перехода из HALF_OPEN в OPEN при ошибке."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.1)
        
        # Открываем circuit
        cb._record_failure()
        
        # Ждём timeout
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN
        
        # Записываем ошибку
        cb._record_failure()
        
        # Circuit должен снова открыться
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerCall:
    """Тесты decorator call."""

    @pytest.mark.asyncio
    async def test_call_succeeds_when_closed(self):
        """Проверка что вызов проходит когда circuit закрыт."""
        cb = CircuitBreaker(name="test")
        
        @cb.call
        async def success_func():
            return "success"
        
        result = await success_func()
        assert result == "success"
        assert cb._total_successes == 1

    @pytest.mark.asyncio
    async def test_call_raises_when_open(self):
        """Проверка что вызов отклоняется когда circuit открыт."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=10)
        
        # Открываем circuit
        cb._record_failure()
        assert cb.is_open
        
        @cb.call
        async def any_func():
            return "should not reach"
        
        # Вызов должен выбросить CircuitOpenError
        with pytest.raises(CircuitOpenError):
            await any_func()
        
        # Статистика: запрос отклонён
        assert cb._total_rejections == 1

    @pytest.mark.asyncio
    async def test_call_records_failure(self):
        """Проверка что ошибка записывается."""
        cb = CircuitBreaker(name="test")
        
        @cb.call
        async def failing_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await failing_func()
        
        assert cb._total_failures == 1
        assert cb._failure_count == 1

    @pytest.mark.asyncio
    async def test_call_with_expected_exception(self):
        """Проверка что только expected_exception отслеживается."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=1,
            expected_exception=ValueError
        )
        
        @cb.call
        async def failing_func():
            raise ValueError("Expected error")
        
        # Ошибка должна выбрасываться и записываться
        with pytest.raises(ValueError):
            await failing_func()
        
        assert cb._total_failures == 1


class TestCircuitBreakerStats:
    """Тесты статистики Circuit Breaker."""

    def test_get_stats(self):
        """Проверка получения статистики."""
        cb = CircuitBreaker(name="test_es")
        
        # Имитируем несколько запросов
        cb._record_success()
        cb._record_success()
        cb._record_failure()
        
        stats = cb.get_stats()
        
        assert stats["name"] == "test_es"
        assert stats["state"] == "closed"
        assert stats["total_requests"] == 3
        assert stats["total_successes"] == 2
        assert stats["total_failures"] == 1
        assert stats["failure_count"] == 1

    def test_reset(self):
        """Проверка сброса circuit breaker."""
        cb = CircuitBreaker(name="test")
        
        # Имитируем состояние
        cb._record_failure()
        cb._record_failure()
        cb._total_requests = 10
        
        # Сбрасываем
        cb.reset()
        
        # Проверяем что сброшено
        assert cb._state == CircuitState.CLOSED
        assert cb._failure_count == 0
        assert cb._total_requests == 0
        stats = cb.get_stats()
        assert stats["total_failures"] == 0


class TestCircuitBreakerFailureWindow:
    """Тесты окна ошибок."""

    def test_failure_count_decreases_after_window(self):
        """Проверка что счётчик ошибок уменьшается после окна."""
        cb = CircuitBreaker(name="test", failure_threshold=5, failure_window=1)
        
        # Записываем ошибки
        for _ in range(3):
            cb._record_failure()
        
        assert cb._failure_count == 3
        
        # Ждём истечения окна
        time.sleep(1.1)
        
        # Записываем успех (должен уменьшить счётчик)
        cb._record_success()
        
        # Счётчик должен уменьшиться
        assert cb._failure_count == 2


class TestCircuitBreakerIntegration:
    """Интеграционные тесты Circuit Breaker."""

    @pytest.mark.asyncio
    async def test_circuit_opens_after_multiple_failures(self):
        """Проверка что circuit открывается после нескольких ошибок."""
        cb = CircuitBreaker(name="es_test", failure_threshold=3, recovery_timeout=0.5)
        
        call_count = 0
        
        @cb.call
        async def flaky_service():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Service unavailable")
        
        # Вызываем пока circuit не откроется
        for i in range(5):
            try:
                await flaky_service()
            except (ConnectionError, CircuitOpenError):
                pass
        
        # Circuit должен открыться после 3 ошибок
        assert cb.state == CircuitState.OPEN
        assert call_count == 3  # Третья ошибка открыла circuit

    @pytest.mark.asyncio
    async def test_circuit_recovers_after_timeout(self):
        """Проверка что circuit восстанавливается после timeout."""
        cb = CircuitBreaker(name="es_test", failure_threshold=1, recovery_timeout=0.5)
        
        success_after_recovery = False
        
        @cb.call
        async def service():
            nonlocal success_after_recovery
            if cb.state == CircuitState.HALF_OPEN:
                success_after_recovery = True
                return "recovered"
            raise ConnectionError("Down")
        
        # Открываем circuit
        try:
            await service()
        except ConnectionError:
            pass
        
        assert cb.is_open
        
        # Ждём восстановления
        await asyncio.sleep(0.6)
        
        # Пробуем снова
        result = await service()
        
        assert result == "recovered"
        assert success_after_recovery is True
        assert cb.is_closed


class TestElasticsearchCircuitBreaker:
    """Тесты глобального circuit breaker для Elasticsearch."""

    @pytest.mark.asyncio
    async def test_es_circuit_breaker_exists(self):
        """Проверка что глобальный circuit breaker существует."""
        from src.core.circuit_breaker import es_circuit_breaker
        
        assert es_circuit_breaker is not None
        assert es_circuit_breaker.name == "elasticsearch"
        assert es_circuit_breaker.failure_threshold == 5
        assert es_circuit_breaker.recovery_timeout == 30

    @pytest.mark.asyncio
    async def test_es_circuit_breaker_helpers(self):
        """Проверка вспомогательных функций."""
        from src.core.elasticsearch import (
            get_circuit_breaker_stats,
            get_circuit_breaker_state,
            reset_circuit_breaker
        )
        
        # Получаем состояние
        state = get_circuit_breaker_state()
        assert state in ["closed", "open", "half_open"]
        
        # Получаем статистику
        stats = get_circuit_breaker_stats()
        assert "name" in stats
        assert "state" in stats
        
        # Сбрасываем
        reset_circuit_breaker()
        new_state = get_circuit_breaker_state()
        assert new_state == "closed"


class TestFallbackPattern:
    """Тесты fallback паттерна при открытом circuit."""

    @pytest.mark.asyncio
    async def test_fallback_when_circuit_open(self):
        """Проверка fallback логики когда circuit открыт."""
        from src.core.circuit_breaker import es_circuit_breaker, CircuitOpenError
        
        # Открываем circuit вручную для теста
        es_circuit_breaker._state = CircuitState.OPEN
        
        try:
            @es_circuit_breaker.call
            async def es_search():
                return {"results": []}
            
            # Вызов должен выбросить CircuitOpenError
            with pytest.raises(CircuitOpenError):
                await es_search()
        
        finally:
            # Сбрасываем circuit
            es_circuit_breaker.reset()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
