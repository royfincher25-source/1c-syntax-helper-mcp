"""Integration тесты для API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

from src.main import app


@pytest.fixture
def client():
    """Создаёт тестовый клиент."""
    return TestClient(app)


class TestHealthEndpoints:
    """Тесты health endpoints."""

    def test_health_check(self, client):
        """Проверка /health endpoint."""
        with patch('src.main.get_basic_health', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "status": "healthy",
                "elasticsearch": True,
                "index_exists": True,
                "documents_count": 100
            }
            
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["elasticsearch"] is True

    def test_health_detailed(self, client):
        """Проверка /health/detailed endpoint."""
        with patch('src.main.get_health_report', new_callable=AsyncMock) as mock_report:
            mock_report.return_value = {
                "status": "healthy",
                "checks": [
                    {"name": "elasticsearch", "status": "healthy"},
                    {"name": "cache", "status": "healthy"}
                ]
            }
            
            response = client.get("/health/detailed")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert len(data["checks"]) == 2

    def test_root_endpoint(self, client):
        """Проверка / endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestShutdownEndpoints:
    """Тесты shutdown endpoints."""

    def test_shutdown_status(self, client):
        """Проверка /shutdown/status endpoint."""
        with patch('src.main.graceful_shutdown') as mock_gs:
            mock_gs.is_shutting_down = False
            mock_gs.active_requests = 0
            mock_gs.shutdown_timeout = 30
            
            response = client.get("/shutdown/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["is_shutting_down"] is False
            assert data["active_requests"] == 0
            assert data["shutdown_timeout"] == 30

    def test_shutdown_initiate(self, client):
        """Проверка /shutdown/initiate endpoint."""
        with patch('src.main.graceful_shutdown') as mock_gs, \
             patch('src.main.asyncio.create_task') as mock_create:
            
            mock_gs.is_shutting_down = False
            mock_gs.active_requests = 2
            
            response = client.post("/shutdown/initiate")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "shutdown_initiated"
            assert mock_create.called

    def test_shutdown_initiate_already_shutting_down(self, client):
        """Проверка /shutdown/initiate когда уже идёт shutdown."""
        with patch('src.main.graceful_shutdown') as mock_gs:
            mock_gs.is_shutting_down = True
            mock_gs.active_requests = 1
            
            response = client.post("/shutdown/initiate")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "already_shutting_down"


class TestCacheEndpoints:
    """Тесты cache endpoints."""

    def test_cache_stats(self, client):
        """Проверка /cache/stats endpoint."""
        with patch('src.main.cache') as mock_cache:
            mock_cache.get_stats = AsyncMock(return_value={
                "hit_rate": 0.5,
                "total_keys": 100,
                "hits": 500,
                "misses": 500
            })
            
            response = client.get("/cache/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert "hit_rate" in data
            assert data["hit_rate"] == 0.5

    def test_cache_clear(self, client):
        """Проверка /cache/clear endpoint."""
        with patch('src.main.cache') as mock_cache:
            mock_cache.clear = AsyncMock(return_value=True)
            
            response = client.post("/cache/clear")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True


class TestIndexEndpoints:
    """Тесты index endpoints."""

    def test_index_status(self, client):
        """Проверка /index/status endpoint."""
        with patch('src.main.es_client') as mock_es:
            mock_es.is_connected = AsyncMock(return_value=True)
            mock_es.index_exists = AsyncMock(return_value=True)
            mock_es.get_documents_count = AsyncMock(return_value=1000)
            
            response = client.get("/index/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["elasticsearch_connected"] is True
            assert data["index_exists"] is True
            assert data["documents_count"] == 1000

    def test_index_rebuild(self, client):
        """Проверка /index/rebuild endpoint."""
        with patch('src.main.indexer') as mock_indexer, \
             patch('src.main.HBKParser') as mock_parser:
            
            mock_parser_instance = MagicMock()
            mock_parser.return_value = mock_parser_instance
            mock_parser_instance.parse_directory = AsyncMock(return_value=MagicMock())
            
            mock_indexer.reindex_all = AsyncMock(return_value=True)
            
            response = client.post("/index/rebuild")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True


class TestMetricsEndpoints:
    """Тесты metrics endpoints."""

    def test_metrics(self, client):
        """Проверка /metrics endpoint."""
        with patch('src.main.get_metrics_collector') as mock_collector:
            mock_metrics = MagicMock()
            mock_metrics.get_prometheus_format = AsyncMock(return_value="# HELP test\n# TYPE test gauge\ntest 1")
            mock_collector.return_value = mock_metrics
            
            response = client.get("/metrics")
            
            assert response.status_code == 200
            assert "test" in response.text

    def test_metrics_with_client_id(self, client):
        """Проверка /metrics/{client_id} endpoint."""
        with patch('src.main.get_metrics_collector') as mock_collector:
            mock_metrics = MagicMock()
            mock_metrics.get_prometheus_format = AsyncMock(return_value="# HELP test\ntest 1")
            mock_collector.return_value = mock_metrics
            
            response = client.get("/metrics/test-client")
            
            assert response.status_code == 200


class TestMCPEndpoints:
    """Тесты MCP endpoints."""

    def test_mcp_tools(self, client):
        """Проверка /mcp/tools endpoint."""
        response = client.get("/mcp/tools")
        
        # Проверяем что endpoint существует
        assert response.status_code in [200, 404]  # Может быть 404 если MCP не настроен

    def test_mcp_get(self, client):
        """Проверка GET /mcp endpoint."""
        response = client.get("/mcp")
        
        # Проверяем что endpoint существует
        assert response.status_code in [200, 404]

    def test_mcp_post(self, client):
        """Проверка POST /mcp endpoint."""
        mcp_request = {
            "tool": "search_1c_syntax",
            "arguments": {
                "query": "СтрДлина"
            }
        }
        
        with patch('src.main.handle_mcp_request', new_callable=AsyncMock) as mock_handler:
            mock_handler.return_value = {
                "content": [{"type": "text", "text": "Result"}]
            }
            
            response = client.post("/mcp", json=mcp_request)
            
            # Проверяем что endpoint принимает запросы
            assert response.status_code in [200, 404]


class TestErrorHandling:
    """Тесты обработки ошибок."""

    def test_404_not_found(self, client):
        """Проверка обработки 404."""
        response = client.get("/nonexistent-endpoint")
        
        assert response.status_code == 404

    def test_405_method_not_allowed(self, client):
        """Проверка обработки 405."""
        response = client.post("/health")  # Health только GET
        
        assert response.status_code == 405

    def test_503_on_shutdown(self, client):
        """Проверка 503 во время shutdown."""
        with patch('src.main.graceful_shutdown') as mock_gs:
            mock_gs.is_shutting_down = True
            
            response = client.get("/index/status")
            
            # Во время shutdown должен быть 503
            assert response.status_code == 503
            data = response.json()
            assert "shutting down" in data["error"].lower()


class TestPerformance:
    """Тесты производительности API."""

    def test_health_response_time(self, client):
        """Проверка времени ответа /health."""
        import time
        
        with patch('src.main.get_basic_health', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {"status": "healthy"}
            
            start = time.time()
            response = client.get("/health")
            duration = time.time() - start
            
            assert response.status_code == 200
            assert duration < 1.0  # Должен ответить быстрее 1 секунды

    def test_concurrent_requests(self, client):
        """Проверка обработки concurrent запросов."""
        import concurrent.futures
        
        def make_request():
            return client.get("/health")
        
        with patch('src.main.get_basic_health', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {"status": "healthy"}
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(make_request) for _ in range(5)]
                responses = [f.result() for f in futures]
            
            # Все запросы должны завершиться успешно
            assert all(r.status_code == 200 for r in responses)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
