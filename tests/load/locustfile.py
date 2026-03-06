"""
Load Testing сценарий для 1C Syntax Helper MCP Server (Locust)

Запуск:
    locust -f tests/load/locustfile.py --host=http://localhost:8000

Запуск без UI (headless):
    locust -f tests/load/locustfile.py --host=http://localhost:8000 --headless -u 50 -r 10 --run-time 10m

Soak тест (30 мин):
    locust -f tests/load/locustfile.py --host=http://localhost:8000 --headless -u 20 -r 2 --run-time 30m --csv=results/
"""

from locust import HttpUser, task, between, events
import random
import time
import json
from typing import Dict, Any


# =============================================================================
# Тестовые данные
# =============================================================================

SEARCH_QUERIES = [
    'СтрДлина',
    'СтрЗаменить',
    'ЧислоПрописью',
    'ТаблицаЗначений',
    'ТаблицаЗначений.Добавить',
    'Массив.Добавить',
    'Структура',
    'СообщениеПользователю',
    'Формат',
    'Попытка'
]

MCP_REQUESTS = [
    {
        "tool": "search_1c_syntax",
        "arguments": {"query": "СтрДлина"}
    },
    {
        "tool": "search_1c_syntax",
        "arguments": {"query": "ТаблицаЗначений.Добавить"}
    },
    {
        "tool": "get_1c_function_details",
        "arguments": {"element_name": "ЧислоПрописью"}
    },
    {
        "tool": "get_quick_reference",
        "arguments": {"element_name": "СтрДлина"}
    },
    {
        "tool": "search_by_context",
        "arguments": {"query": "Стр", "context": "global"}
    }
]


# =============================================================================
# Метрики
# =============================================================================

class Metrics:
    """Сборщик метрик."""
    
    def __init__(self):
        self.search_times = []
        self.health_times = []
        self.mcp_times = []
        self.errors = 0
        self.total_requests = 0
    
    def record_search(self, duration: float, success: bool):
        self.search_times.append(duration)
        self.total_requests += 1
        if not success:
            self.errors += 1
    
    def record_health(self, duration: float, success: bool):
        self.health_times.append(duration)
        self.total_requests += 1
        if not success:
            self.errors += 1
    
    def record_mcp(self, duration: float, success: bool):
        self.mcp_times.append(duration)
        self.total_requests += 1
        if not success:
            self.errors += 1
    
    def get_p95(self, times: list) -> float:
        if not times:
            return 0
        sorted_times = sorted(times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    def get_p99(self, times: list) -> float:
        if not times:
            return 0
        sorted_times = sorted(times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    def get_error_rate(self) -> float:
        if self.total_requests == 0:
            return 0
        return (self.errors / self.total_requests) * 100
    
    def get_report(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "errors": self.errors,
            "error_rate": f"{self.get_error_rate():.2f}%",
            "search_p95": f"{self.get_p95(self.search_times):.2f}ms",
            "search_p99": f"{self.get_p99(self.search_times):.2f}ms",
            "health_p95": f"{self.get_p95(self.health_times):.2f}ms",
            "mcp_p95": f"{self.get_p95(self.mcp_times):.2f}ms",
        }


metrics = Metrics()


# =============================================================================
# Locust пользователь
# =============================================================================

class MCPUser(HttpUser):
    """
    Пользователь для MCP сервера.
    
    Эмулирует поведение реального пользователя:
    - 60% запросов - поиск
    - 20% запросов - MCP инструменты
    - 15% запросов - health check
    - 5% запросов - detailed health
    """
    
    wait_time = between(0.5, 2)  # Пауза между запросами
    
    @task(6)
    def search_syntax(self):
        """Поиск по синтаксису 1С."""
        query = random.choice(SEARCH_QUERIES)
        
        start_time = time.time()
        
        with self.client.post(
            "/mcp",
            json={
                "tool": "search_1c_syntax",
                "arguments": {"query": query}
            },
            catch_response=True
        ) as response:
            duration = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "content" in data:
                        response.success()
                    else:
                        response.failure("No content in response")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Status code: {response.status_code}")
            
            metrics.record_search(duration, response.status_code == 200)
    
    @task(2)
    def mcp_tool_request(self):
        """MCP запрос к инструменту."""
        payload = random.choice(MCP_REQUESTS)
        
        start_time = time.time()
        
        with self.client.post(
            "/mcp",
            json=payload,
            catch_response=True
        ) as response:
            duration = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "content" in data:
                        response.success()
                    else:
                        response.failure("No content in response")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Status code: {response.status_code}")
            
            metrics.record_mcp(duration, response.status_code == 200)
    
    @task(1)
    def health_check(self):
        """Health check."""
        start_time = time.time()
        
        with self.client.get(
            "/health",
            catch_response=True
        ) as response:
            duration = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") == "healthy":
                        response.success()
                    else:
                        response.failure(f"Unhealthy status: {data.get('status')}")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Status code: {response.status_code}")
            
            metrics.record_health(duration, response.status_code == 200)
    
    @task(1)
    def health_detailed(self):
        """Detailed health check."""
        start_time = time.time()
        
        with self.client.get(
            "/health/detailed",
            catch_response=True
        ) as response:
            duration = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "checks" in data:
                        response.success()
                    else:
                        response.failure("No checks in response")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Status code: {response.status_code}")
            
            metrics.record_health(duration, response.status_code == 200)
    
    @task(1)
    def cache_stats(self):
        """Получение статистики кэша."""
        self.client.get("/cache/stats")
    
    @task(1)
    def index_status(self):
        """Получение статуса индексации."""
        self.client.get("/index/status")


# =============================================================================
# События
# =============================================================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Начало теста."""
    print("\n" + "="*60)
    print("LOAD TEST STARTED")
    print("="*60)
    print(f"Target host: {environment.host}")
    print(f"Users: {environment.runner.user_count if environment.runner else 'N/A'}")
    print("="*60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Окончание теста."""
    print("\n" + "="*60)
    print("LOAD TEST COMPLETED")
    print("="*60)
    
    report = metrics.get_report()
    print("\nMETRICS REPORT:")
    print("-" * 60)
    for key, value in report.items():
        print(f"  {key}: {value}")
    print("-" * 60)
    
    # Проверка пороговых значений
    print("\nTHRESHOLDS:")
    search_p95 = float(report["search_p95"].replace("ms", ""))
    print(f"  Search P95 < 300ms: {'✅' if search_p95 < 300 else '❌'} ({report['search_p95']})")
    
    error_rate = float(report["error_rate"].replace("%", ""))
    print(f"  Error Rate < 1%: {'✅' if error_rate < 1 else '❌'} ({report['error_rate']})")
    
    print("="*60 + "\n")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, 
               context, exception, start_time, url, **kwargs):
    """Логирование каждого запроса."""
    if exception:
        print(f"ERROR: {request_type} {name} - {exception}")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import os
    os.system("locust -f locustfile.py --host=http://localhost:8000")
