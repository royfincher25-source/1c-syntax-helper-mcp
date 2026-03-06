from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.metrics.collector import MetricsCollector


class PrometheusFormatter:
    """Форматтер метрик в формат Prometheus."""

    @staticmethod
    def format(metrics: "MetricsCollector") -> str:
        """
        Экспорт метрик в формате Prometheus.
        
        Args:
            metrics: Экземпляр MetricsCollector
            
        Returns:
            Строка в формате Prometheus
        """
        lines = []
        
        counters = metrics.counters
        gauges = metrics.gauges
        timers = metrics.timers
        perf_stats = metrics.performance_stats
        
        lines.extend(PrometheusFormatter._format_counters(counters))
        lines.extend(PrometheusFormatter._format_gauges(gauges, counters, perf_stats))
        lines.extend(PrometheusFormatter._format_timers(timers))
        lines.extend(PrometheusFormatter._format_system_metrics(gauges))
        
        return "\n".join(lines) + "\n"
    
    @staticmethod
    def _format_counters(counters: Dict[str, float]) -> List[str]:
        """Форматирование счетчиков."""
        lines = []
        
        lines.append("# HELP mcp_requests_total Total number of MCP requests")
        lines.append("# TYPE mcp_requests_total counter")
        lines.append(f"mcp_requests_total {counters.get('mcp.requests', 0)}")
        
        lines.append("# HELP mcp_errors_total Total number of MCP errors")
        lines.append("# TYPE mcp_errors_total counter")
        lines.append(f"mcp_errors_total {counters.get('mcp.errors', 0)}")
        
        lines.append("# HELP mcp_cache_hits_total Total number of cache hits")
        lines.append("# TYPE mcp_cache_hits_total counter")
        lines.append(f"mcp_cache_hits_total {counters.get('cache.hits', 0)}")
        
        lines.append("# HELP mcp_cache_misses_total Total number of cache misses")
        lines.append("# TYPE mcp_cache_misses_total counter")
        lines.append(f"mcp_cache_misses_total {counters.get('cache.misses', 0)}")
        
        return lines
    
    @staticmethod
    def _format_gauges(gauges: Dict[str, float], counters: Dict[str, float], perf_stats) -> List[str]:
        """Форматирование gauge метрик."""
        lines = []
        
        lines.append("# HELP mcp_active_requests Current number of active requests")
        lines.append("# TYPE mcp_active_requests gauge")
        lines.append(f"mcp_active_requests {perf_stats.current_active_requests}")
        
        lines.append("# HELP mcp_cache_hit_rate Cache hit rate percentage")
        lines.append("# TYPE mcp_cache_hit_rate gauge")
        cache_total = counters.get('cache.hits', 0) + counters.get('cache.misses', 0)
        hit_rate = (counters.get('cache.hits', 0) / max(cache_total, 1)) * 100
        lines.append(f"mcp_cache_hit_rate {hit_rate}")
        
        lines.append("# HELP mcp_success_rate Success rate percentage")
        lines.append("# TYPE mcp_success_rate gauge")
        success_rate = (perf_stats.successful_requests / max(perf_stats.total_requests, 1)) * 100
        lines.append(f"mcp_success_rate {success_rate}")
        
        return lines
    
    @staticmethod
    def _format_timers(timers: Dict[str, List[float]]) -> List[str]:
        """Форматирование таймеров."""
        lines = []
        
        lines.append("# HELP mcp_request_duration_seconds Request duration in seconds")
        lines.append("# TYPE mcp_request_duration_seconds summary")
        
        if 'request.duration' in timers and timers['request.duration']:
            values = sorted(timers['request.duration'])
            count = len(values)
            lines.append(f"mcp_request_duration_seconds_count {count}")
            lines.append(f"mcp_request_duration_seconds_sum {sum(values) / 1000}")
            lines.append(f"mcp_request_duration_seconds{{quantile=\"0.5\"}} {values[count // 2] / 1000}")
            lines.append(f"mcp_request_duration_seconds{{quantile=\"0.9\"}} {values[int(count * 0.9)] / 1000}")
            lines.append(f"mcp_request_duration_seconds{{quantile=\"0.95\"}} {values[int(count * 0.95)] / 1000}")
            lines.append(f"mcp_request_duration_seconds{{quantile=\"0.99\"}} {values[min(int(count * 0.99), count - 1)] / 1000}")
        
        return lines
    
    @staticmethod
    def _format_system_metrics(gauges: Dict[str, float]) -> List[str]:
        """Форматирование системных метрик."""
        lines = []
        
        lines.append("# HELP mcp_system_cpu_usage_percent CPU usage percentage")
        lines.append("# TYPE mcp_system_cpu_usage_percent gauge")
        lines.append(f"mcp_system_cpu_usage_percent {gauges.get('system.cpu.usage_percent', 0)}")
        
        lines.append("# HELP mcp_system_memory_usage_percent Memory usage percentage")
        lines.append("# TYPE mcp_system_memory_usage_percent gauge")
        lines.append(f"mcp_system_memory_usage_percent {gauges.get('system.memory.usage_percent', 0)}")
        
        lines.append("# HELP mcp_system_disk_usage_percent Disk usage percentage")
        lines.append("# TYPE mcp_system_disk_usage_percent gauge")
        lines.append(f"mcp_system_disk_usage_percent {gauges.get('system.disk.usage_percent', 0)}")
        
        return lines
