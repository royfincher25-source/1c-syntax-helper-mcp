"""Тесты Health Checks."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.health import (
    HealthChecker,
    HealthStatus,
    HealthCheck,
    get_health_report,
    get_basic_health
)


class TestHealthStatus:
    """Тесты статусов Health."""

    def test_health_status_values(self):
        """Проверка значений статусов."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


class TestHealthCheck:
    """Тесты отдельной проверки."""

    def test_health_check_to_dict(self):
        """Проверка преобразования в словарь."""
        check = HealthCheck(
            name="test",
            status=HealthStatus.HEALTHY,
            message="All good",
            details={"key": "value"},
            response_time_ms=10.5
        )
        
        result = check.to_dict()
        
        assert result["name"] == "test"
        assert result["status"] == "healthy"
        assert result["message"] == "All good"
        assert result["details"]["key"] == "value"
        assert result["response_time_ms"] == 10.5

    def test_health_check_without_optional_fields(self):
        """Проверка без опциональных полей."""
        check = HealthCheck(
            name="test",
            status=HealthStatus.HEALTHY
        )
        
        result = check.to_dict()
        
        assert result["name"] == "test"
        assert result["status"] == "healthy"
        assert "details" not in result
        assert "response_time_ms" not in result


class TestHealthChecker:
    """Тесты HealthChecker."""

    @pytest.mark.asyncio
    async def test_check_all_returns_report(self):
        """Проверка что check_all возвращает отчёт."""
        checker = HealthChecker()
        
        # Мокаем все проверки
        with patch.object(checker, 'check_elasticsearch', new_callable=AsyncMock) as mock_es, \
             patch.object(checker, 'check_cache', new_callable=AsyncMock) as mock_cache, \
             patch.object(checker, 'check_circuit_breaker', new_callable=AsyncMock) as mock_cb, \
             patch.object(checker, 'check_disk_space', new_callable=AsyncMock) as mock_disk, \
             patch.object(checker, 'check_memory', new_callable=AsyncMock) as mock_memory:
            
            # Настраиваем возврат здоровых статусов
            for mock in [mock_es, mock_cache, mock_cb, mock_disk, mock_memory]:
                mock.return_value = HealthCheck("test", HealthStatus.HEALTHY)
            
            report = await checker.check_all()
            
            assert "status" in report
            assert "timestamp" in report
            assert "checks" in report
            assert "summary" in report

    def test_calculate_overall_status_healthy(self):
        """Проверка расчёта общего статуса (healthy)."""
        checker = HealthChecker()
        checker.checks = [
            HealthCheck("test1", HealthStatus.HEALTHY),
            HealthCheck("test2", HealthStatus.HEALTHY)
        ]
        
        status = checker._calculate_overall_status()
        assert status == HealthStatus.HEALTHY

    def test_calculate_overall_status_degraded(self):
        """Проверка расчёта общего статуса (degraded)."""
        checker = HealthChecker()
        checker.checks = [
            HealthCheck("test1", HealthStatus.HEALTHY),
            HealthCheck("test2", HealthStatus.DEGRADED)
        ]
        
        status = checker._calculate_overall_status()
        assert status == HealthStatus.DEGRADED

    def test_calculate_overall_status_unhealthy(self):
        """Проверка расчёта общего статуса (unhealthy)."""
        checker = HealthChecker()
        checker.checks = [
            HealthCheck("test1", HealthStatus.HEALTHY),
            HealthCheck("test2", HealthStatus.UNHEALTHY)
        ]
        
        status = checker._calculate_overall_status()
        assert status == HealthStatus.UNHEALTHY


class TestElasticsearchHealthCheck:
    """Тесты health check Elasticsearch."""

    @pytest.mark.asyncio
    async def test_es_connected_and_index_exists(self):
        """Проверка ES подключён и индекс существует."""
        checker = HealthChecker()
        
        with patch('src.core.health.es_client') as mock_es_client:
            mock_es_client.is_connected = AsyncMock(return_value=True)
            mock_es_client.index_exists = AsyncMock(return_value=True)
            mock_es_client.get_documents_count = AsyncMock(return_value=1000)
            
            with patch('src.core.health.get_circuit_breaker_state', return_value="closed"):
                check = await checker.check_elasticsearch()
                
                assert check.name == "elasticsearch"
                assert check.status == HealthStatus.HEALTHY
                assert check.details["connected"] is True
                assert check.details["index_exists"] is True
                assert check.details["documents_count"] == 1000

    @pytest.mark.asyncio
    async def test_es_not_connected(self):
        """Проверка ES не подключён."""
        checker = HealthChecker()
        
        with patch('src.core.health.es_client') as mock_es_client:
            mock_es_client.is_connected = AsyncMock(return_value=False)
            
            check = await checker.check_elasticsearch()
            
            assert check.status == HealthStatus.UNHEALTHY
            assert "недоступен" in check.message

    @pytest.mark.asyncio
    async def test_es_connected_but_no_index(self):
        """Проверка ES подключён но индекс не существует."""
        checker = HealthChecker()
        
        with patch('src.core.health.es_client') as mock_es_client:
            mock_es_client.is_connected = AsyncMock(return_value=True)
            mock_es_client.index_exists = AsyncMock(return_value=False)
            
            check = await checker.check_elasticsearch()
            
            assert check.status == HealthStatus.DEGRADED
            assert check.details["connected"] is True
            assert check.details["index_exists"] is False


class TestCacheHealthCheck:
    """Тесты health check кэша."""

    @pytest.mark.asyncio
    async def test_cache_healthy_with_good_hit_rate(self):
        """Проверка кэш здоров с хорошим hit rate."""
        checker = HealthChecker()
        
        with patch('src.core.health.cache') as mock_cache:
            mock_cache.get_stats = AsyncMock(return_value={
                "hit_rate": 0.5,
                "total_keys": 100,
                "hits": 500,
                "misses": 500,
                "evictions": 0
            })
            
            check = await checker.check_cache()
            
            assert check.status == HealthStatus.HEALTHY
            assert "hit rate" in check.message

    @pytest.mark.asyncio
    async def test_cache_degraded_with_low_hit_rate(self):
        """Проверка кэш деградировал с низким hit rate."""
        checker = HealthChecker()
        
        with patch('src.core.health.cache') as mock_cache:
            mock_cache.get_stats = AsyncMock(return_value={
                "hit_rate": 0.1,
                "total_keys": 10,
                "hits": 10,
                "misses": 90,
                "evictions": 0
            })
            
            check = await checker.check_cache()
            
            assert check.status == HealthStatus.DEGRADED
            assert "низкий hit rate" in check.message or "пуст" in check.message


class TestCircuitBreakerHealthCheck:
    """Тесты health check circuit breaker."""

    @pytest.mark.asyncio
    async def test_cb_closed_healthy(self):
        """Проверка circuit breaker закрыт (здоров)."""
        checker = HealthChecker()
        
        with patch('src.core.health.get_circuit_breaker_state', return_value="closed"), \
             patch('src.core.health.get_circuit_breaker_stats', return_value={
                 "failure_count": 0,
                 "total_failures": 5,
                 "total_successes": 95,
                 "total_requests": 100,
                 "total_rejections": 0
             }):
            
            check = await checker.check_circuit_breaker()
            
            assert check.status == HealthStatus.HEALTHY
            assert "закрыт" in check.message

    @pytest.mark.asyncio
    async def test_cb_open_degraded(self):
        """Проверка circuit breaker открыт (деградация)."""
        checker = HealthChecker()
        
        with patch('src.core.health.get_circuit_breaker_state', return_value="open"), \
             patch('src.core.health.get_circuit_breaker_stats', return_value={
                 "failure_count": 5,
                 "total_failures": 10,
                 "total_successes": 90,
                 "total_requests": 100,
                 "total_rejections": 5
             }):
            
            check = await checker.check_circuit_breaker()
            
            assert check.status == HealthStatus.DEGRADED
            assert "открыт" in check.message


class TestDiskSpaceHealthCheck:
    """Тесты health check дискового пространства."""

    @pytest.mark.asyncio
    async def test_disk_healthy(self):
        """Проверка достаточно места на диске."""
        checker = HealthChecker()
        
        mock_disk = MagicMock()
        mock_disk.total = 500 * (1024 ** 3)  # 500 GB
        mock_disk.used = 200 * (1024 ** 3)   # 200 GB
        mock_disk.free = 300 * (1024 ** 3)   # 300 GB
        mock_disk.percent = 40.0
        
        with patch('src.core.health.psutil.disk_usage', return_value=mock_disk):
            check = await checker.check_disk_space()
            
            assert check.status == HealthStatus.HEALTHY
            assert check.details["free_percent"] == "60.0%"

    @pytest.mark.asyncio
    async def test_disk_low_space(self):
        """Проверка мало места на диске."""
        checker = HealthChecker()
        
        mock_disk = MagicMock()
        mock_disk.total = 500 * (1024 ** 3)  # 500 GB
        mock_disk.used = 450 * (1024 ** 3)   # 450 GB
        mock_disk.free = 50 * (1024 ** 3)    # 50 GB (10%)
        mock_disk.percent = 90.0
        
        with patch('src.core.health.psutil.disk_usage', return_value=mock_disk):
            check = await checker.check_disk_space()
            
            assert check.status == HealthStatus.DEGRADED
            assert "Мало места" in check.message

    @pytest.mark.asyncio
    async def test_disk_critical_space(self):
        """Проверка критически мало места на диске."""
        checker = HealthChecker()
        
        mock_disk = MagicMock()
        mock_disk.total = 500 * (1024 ** 3)  # 500 GB
        mock_disk.used = 490 * (1024 ** 3)   # 490 GB
        mock_disk.free = 10 * (1024 ** 3)    # 10 GB (2%)
        mock_disk.percent = 98.0
        
        with patch('src.core.health.psutil.disk_usage', return_value=mock_disk):
            check = await checker.check_disk_space()
            
            assert check.status == HealthStatus.UNHEALTHY
            assert "Критически мало" in check.message


class TestMemoryHealthCheck:
    """Тесты health check памяти."""

    @pytest.mark.asyncio
    async def test_memory_healthy(self):
        """Проверка достаточно памяти."""
        checker = HealthChecker()
        
        mock_memory = MagicMock()
        mock_memory.total = 16 * (1024 ** 3)    # 16 GB
        mock_memory.available = 8 * (1024 ** 3) # 8 GB (50%)
        mock_memory.percent = 50.0
        
        with patch('src.core.health.psutil.virtual_memory', return_value=mock_memory):
            check = await checker.check_memory()
            
            assert check.status == HealthStatus.HEALTHY
            assert check.details["available_percent"] == "50.0%"


class TestGlobalFunctions:
    """Тесты глобальных функций."""

    @pytest.mark.asyncio
    async def test_get_health_report(self):
        """Проверка get_health_report."""
        with patch('src.core.health.health_checker.check_all', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"status": "healthy"}
            
            report = await get_health_report()
            
            assert report == {"status": "healthy"}
            assert mock_check.called

    @pytest.mark.asyncio
    async def test_get_basic_health(self):
        """Проверка get_basic_health."""
        with patch('src.core.health.es_client') as mock_es:
            mock_es.is_connected = AsyncMock(return_value=True)
            mock_es.index_exists = AsyncMock(return_value=True)
            mock_es.get_documents_count = AsyncMock(return_value=100)
            
            report = await get_basic_health()
            
            assert report["status"] == "healthy"
            assert report["elasticsearch"] is True
            assert report["index_exists"] is True
            assert report["documents_count"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
