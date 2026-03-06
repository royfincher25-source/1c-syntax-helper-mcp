"""Тесты connection pooling и retry logic для Elasticsearch."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from elasticsearch.exceptions import ConnectionError

from src.core.elasticsearch import (
    ElasticsearchClient,
    retry_with_backoff,
    ConnectionFailedError
)
from src.core.config import settings


class TestConnectionPooling:
    """Тесты connection pooling."""

    def test_config_pool_settings(self):
        """Проверка настроек пула из конфигурации."""
        es_config = settings.elasticsearch
        
        # Проверяем что настройки существуют
        assert hasattr(es_config, 'pool_maxsize')
        assert hasattr(es_config, 'pool_max_retries')
        assert hasattr(es_config, 'connect_timeout')
        assert hasattr(es_config, 'read_timeout')
        
        # Проверяем значения по умолчанию
        assert es_config.pool_maxsize == 10
        assert es_config.pool_max_retries == 3
        assert es_config.connect_timeout == 10
        assert es_config.read_timeout == 30

    def test_client_uses_pool_settings(self):
        """Проверка что клиент использует настройки пула."""
        client = ElasticsearchClient()
        
        # Проверяем что клиент инициализирован настройками
        assert client._pool_maxsize == settings.elasticsearch.pool_maxsize
        assert client._max_retries == settings.elasticsearch.pool_max_retries
        assert client._connect_timeout == settings.elasticsearch.connect_timeout
        assert client._read_timeout == settings.elasticsearch.read_timeout

    @pytest.mark.asyncio
    async def test_connect_logs_pool_settings(self):
        """Проверка что при подключении логируются настройки пула."""
        # Мокаем клиент
        mock_es_client = AsyncMock()
        mock_es_client.info = AsyncMock()
        
        client = ElasticsearchClient()
        client._client = mock_es_client
        
        # Патчим logger
        with patch('src.core.elasticsearch.logger') as mock_logger:
            # Патчим AsyncElasticsearch
            with patch('src.core.elasticsearch.AsyncElasticsearch', return_value=mock_es_client):
                result = await client.connect()
                
                assert result is True
                # Проверяем что лог содержит информацию о пуле
                assert mock_logger.info.called
                call_args = mock_logger.info.call_args[0][0]
                assert 'pool_size' in call_args
                assert 'max_retries' in call_args


class TestRetryLogic:
    """Тесты retry logic."""

    @pytest.mark.asyncio
    async def test_retry_decorator_retries_on_connection_error(self):
        """Проверка что decorator повторяет при ConnectionError."""
        call_count = 0
        
        @retry_with_backoff(max_retries=3, base_delay=0.01)  # Быстрая задержка для тестов
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Test connection error")
            return "success"
        
        result = await failing_function()
        
        # Функция должна быть вызвана 3 раза (2 неудачных + 1 успешный)
        assert call_count == 3
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_decorator_exhausts_retries(self):
        """Проверка что decorator исчерпывает попытки."""
        call_count = 0
        
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        async def always_failing_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Always fails")
        
        with pytest.raises(ConnectionError):
            await always_failing_function()
        
        # 1 первоначальная + 2 retry = 3 вызова
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_decorator_no_retry_on_success(self):
        """Проверка что нет retry при успешном выполнении."""
        call_count = 0
        
        @retry_with_backoff(max_retries=3, base_delay=0.01)
        async def success_function():
            nonlocal call_count
            call_count += 1
            return "immediate success"
        
        result = await success_function()
        
        # Только один вызов
        assert call_count == 1
        assert result == "immediate success"

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self):
        """Проверка экспоненциальной задержки."""
        import time
        
        delays = []
        call_times = []
        
        @retry_with_backoff(max_retries=3, base_delay=0.1)
        async def timing_function():
            call_times.append(time.time())
            if len(call_times) < 4:
                raise ConnectionError("Fail")
            return "success"
        
        await timing_function()
        
        # Вычисляем фактические задержки между вызовами
        for i in range(1, len(call_times)):
            delays.append(call_times[i] - call_times[i-1])
        
        # Проверяем что задержки возрастают экспоненциально
        # 0.1s, 0.2s, 0.4s (с некоторой погрешностью)
        assert len(delays) == 3
        assert delays[0] >= 0.08  # ~0.1s
        assert delays[1] >= 0.16  # ~0.2s
        assert delays[2] >= 0.32  # ~0.4s


class TestSearchWithRetry:
    """Тесты поиска с retry logic."""

    @pytest.mark.asyncio
    async def test_search_retries_on_connection_error(self):
        """Проверка что search повторяет при ConnectionError."""
        mock_es_client = AsyncMock()
        
        # Первые два вызова fail, третий success
        call_count = 0
        
        async def mock_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return {"hits": {"hits": [], "total": {"value": 0}}}
        
        mock_es_client.search = mock_search
        
        client = ElasticsearchClient()
        client._client = mock_es_client
        
        # Патчим logger чтобы избежать ошибок
        with patch('src.core.elasticsearch.logger'):
            result = await client.search({"query": {"match_all": {}}})
            
            # Search был вызван 3 раза
            assert call_count == 3
            assert result is not None

    @pytest.mark.asyncio
    async def test_search_returns_none_on_persistent_failure(self):
        """Проверка что search возвращает None после исчерпания попыток."""
        mock_es_client = AsyncMock()
        mock_es_client.search = AsyncMock(side_effect=ConnectionError("Always fails"))
        
        client = ElasticsearchClient()
        client._client = mock_es_client
        
        # Патчим logger
        with patch('src.core.elasticsearch.logger'):
            # Патчим retry_with_backoff чтобы уменьшить задержки
            with patch('src.core.elasticsearch.retry_with_backoff') as mock_retry:
                # Возвращаем оригинальный decorator но с быстрыми задержками
                from src.core.elasticsearch import retry_with_backoff as original_retry
                mock_retry.side_effect = lambda **kwargs: original_retry(
                    max_retries=kwargs.get('max_retries', 3),
                    base_delay=kwargs.get('base_delay', 0.01)
                )
                
                result = await client.search({"query": {"match_all": {}}})
                
                # После исчерпания попыток возвращает None
                assert result is None


class TestConcurrentRequests:
    """Тесты concurrent запросов."""

    @pytest.mark.asyncio
    async def test_concurrent_search_requests(self):
        """Проверка обработки concurrent запросов."""
        mock_es_client = AsyncMock()
        
        async def mock_search(*args, **kwargs):
            await asyncio.sleep(0.01)  # Имитация задержки
            return {"hits": {"hits": [], "total": {"value": 0}}}
        
        mock_es_client.search = mock_search
        
        client = ElasticsearchClient()
        client._client = mock_es_client
        
        # Создаем 10 concurrent запросов
        queries = [{"query": {"match_all": {}}} for _ in range(10)]
        
        with patch('src.core.elasticsearch.logger'):
            results = await asyncio.gather(*[
                client.search(query) for query in queries
            ])
        
        # Все запросы должны завершиться успешно
        assert len(results) == 10
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_connection_pool_handles_multiple_requests(self):
        """Проверка что пул обрабатывает множественные запросы."""
        mock_es_client = AsyncMock()
        request_count = 0
        
        async def mock_search(*args, **kwargs):
            nonlocal request_count
            request_count += 1
            return {"hits": {"hits": [{"_source": {"name": f"doc_{request_count}"}}], "total": {"value": 1}}}
        
        mock_es_client.search = mock_search
        
        client = ElasticsearchClient()
        client._client = mock_es_client
        
        with patch('src.core.elasticsearch.logger'):
            # Выполняем 20 запросов
            for _ in range(20):
                await client.search({"query": {"match_all": {}}})
        
        # Все запросы выполнены
        assert request_count == 20


class TestTimeoutSettings:
    """Тесты настроек таймаутов."""

    def test_timeout_configuration(self):
        """Проверка конфигурации таймаутов."""
        es_config = settings.elasticsearch
        
        # Проверяем что таймауты разумные
        assert es_config.connect_timeout > 0
        assert es_config.read_timeout > 0
        assert es_config.read_timeout >= es_config.connect_timeout
        
        # connect_timeout должен быть меньше read_timeout
        assert es_config.connect_timeout == 10
        assert es_config.read_timeout == 30

    def test_client_uses_timeout_settings(self):
        """Проверка что клиент использует настройки таймаутов."""
        client = ElasticsearchClient()
        
        # Проверяем что клиент инициализирован таймаутами
        assert client._connect_timeout == settings.elasticsearch.connect_timeout
        assert client._read_timeout == settings.elasticsearch.read_timeout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
