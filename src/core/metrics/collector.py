import time
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from enum import Enum

from src.core.logging import get_logger
from src.core.metrics.prometheus_formatter import PrometheusFormatter

logger = get_logger(__name__)


class MetricType(Enum):
    """Типы метрик."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class MetricValue:
    """Значение метрики."""
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class PerformanceStats:
    """Статистика производительности."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    max_response_time: float = 0.0
    min_response_time: float = float('inf')
    current_active_requests: int = 0


class MetricsCollector:
    """Сборщик метрик."""
    
    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_size))
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        
        self.performance_stats = PerformanceStats()
        
        self._lock = asyncio.Lock()
    
    async def increment(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Увеличение счетчика."""
        async with self._lock:
            self._counters[name] += value
            
            metric_value = MetricValue(
                value=self._counters[name],
                timestamp=time.time(),
                labels=labels or {}
            )
            
            self._metrics[name].append(metric_value)
            logger.debug(f"Counter {name} incremented by {value}, total: {self._counters[name]}")
    
    async def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Установка значения gauge метрики."""
        async with self._lock:
            self._gauges[name] = value
            
            metric_value = MetricValue(
                value=value,
                timestamp=time.time(),
                labels=labels or {}
            )
            
            self._metrics[name].append(metric_value)
            logger.debug(f"Gauge {name} set to {value}")
    
    async def record_timer(self, name: str, duration: float, labels: Optional[Dict[str, str]] = None):
        """Запись времени выполнения."""
        async with self._lock:
            self._timers[name].append(duration)
            
            if len(self._timers[name]) > self.history_size:
                self._timers[name] = self._timers[name][-self.history_size:]
            
            metric_value = MetricValue(
                value=duration,
                timestamp=time.time(),
                labels=labels or {}
            )
            
            self._metrics[name].append(metric_value)
            logger.debug(f"Timer {name} recorded: {duration:.3f}s")
    
    @asynccontextmanager
    async def timer(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Контекстный менеджер для измерения времени выполнения."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            await self.record_timer(name, duration, labels)
    
    async def get_metric_stats(self, name: str) -> Dict[str, Any]:
        """Получение статистики по метрике."""
        async with self._lock:
            if name in self._counters:
                return {
                    'type': 'counter',
                    'value': self._counters[name],
                    'history_size': len(self._metrics[name])
                }
            
            if name in self._gauges:
                return {
                    'type': 'gauge',
                    'value': self._gauges[name],
                    'history_size': len(self._metrics[name])
                }
            
            if name in self._timers:
                timers = self._timers[name]
                if timers:
                    return {
                        'type': 'timer',
                        'count': len(timers),
                        'avg': sum(timers) / len(timers),
                        'min': min(timers),
                        'max': max(timers),
                        'last': timers[-1] if timers else 0
                    }
            
            return {'type': 'unknown', 'value': None}
    
    async def get_all_metrics(self) -> Dict[str, Any]:
        """Получение всех метрик."""
        async with self._lock:
            result = {
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'timers': {}
            }

            for name, timers in self._timers.items():
                if timers:
                    sorted_timers = sorted(timers)
                    count = len(timers)
                    result['timers'][name] = {
                        'count': count,
                        'avg': sum(timers) / count,
                        'min': min(timers),
                        'max': max(timers),
                        'p50': sorted_timers[count // 2],
                        'p90': sorted_timers[int(count * 0.9)],
                        'p95': sorted_timers[int(count * 0.95)],
                        'p99': sorted_timers[min(int(count * 0.99), count - 1)]
                    }

            return result
    
    async def update_performance_stats(self, success: bool, response_time: float):
        """Обновление статистики производительности."""
        async with self._lock:
            self.performance_stats.total_requests += 1
            
            if success:
                self.performance_stats.successful_requests += 1
            else:
                self.performance_stats.failed_requests += 1
            
            if response_time > self.performance_stats.max_response_time:
                self.performance_stats.max_response_time = response_time
            
            if response_time < self.performance_stats.min_response_time:
                self.performance_stats.min_response_time = response_time
            
            total_time = (self.performance_stats.avg_response_time * 
                         (self.performance_stats.total_requests - 1) + response_time)
            self.performance_stats.avg_response_time = total_time / self.performance_stats.total_requests

    @property
    def counters(self) -> Dict[str, float]:
        return dict(self._counters)
    
    @property
    def gauges(self) -> Dict[str, float]:
        return dict(self._gauges)
    
    @property
    def timers(self) -> Dict[str, List[float]]:
        return dict(self._timers)
    
    def get_prometheus_format(self) -> str:
        """Экспорт метрик в формате Prometheus."""
        return PrometheusFormatter.format(self)


# Глобальный экземпляр
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Получить глобальный экземпляр MetricsCollector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics_collector() -> None:
    """Сбросить глобальный экземпляр (для тестов)."""
    global _metrics_collector
    _metrics_collector = None
