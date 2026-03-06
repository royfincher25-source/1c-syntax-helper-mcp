import asyncio
from typing import Optional

import psutil

from src.core.logging import get_logger
from src.core.metrics.collector import MetricsCollector

logger = get_logger(__name__)


class SystemMonitor:
    """Монитор системных ресурсов."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def start_monitoring(self, interval: int = 30):
        """Запуск мониторинга системных ресурсов."""
        if self._monitoring:
            logger.warning("System monitoring already started")
            return
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        logger.info(f"System monitoring started with {interval}s interval")
    
    async def stop_monitoring(self):
        """Остановка мониторинга."""
        self._monitoring = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("System monitoring stopped")
    
    async def _monitor_loop(self, interval: int):
        """Основной цикл мониторинга."""
        while self._monitoring:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)
    
    async def _collect_system_metrics(self):
        """Сбор системных метрик."""
        try:
            cpu_percent = psutil.cpu_percent()
            await self.metrics.set_gauge('system.cpu.usage_percent', cpu_percent)
            
            memory = psutil.virtual_memory()
            await self.metrics.set_gauge('system.memory.usage_percent', memory.percent)
            await self.metrics.set_gauge('system.memory.used_mb', memory.used / 1024 / 1024)
            await self.metrics.set_gauge('system.memory.available_mb', memory.available / 1024 / 1024)
            
            disk = psutil.disk_usage('/')
            await self.metrics.set_gauge('system.disk.usage_percent', 
                                       (disk.used / disk.total) * 100)
            await self.metrics.set_gauge('system.disk.free_gb', disk.free / 1024 / 1024 / 1024)
            
            try:
                network = psutil.net_io_counters()
                await self.metrics.set_gauge('system.network.bytes_sent', network.bytes_sent)
                await self.metrics.set_gauge('system.network.bytes_recv', network.bytes_recv)
            except Exception:
                pass
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
