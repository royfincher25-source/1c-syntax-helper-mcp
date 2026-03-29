"""Модуль Health Checks для мониторинга зависимостей."""

from typing import Dict, Any, Optional, List
from enum import Enum
import time
import psutil
import os

from src.core.logging import get_logger
from src.core.elasticsearch import es_client, get_circuit_breaker_state, get_circuit_breaker_stats
from src.core.cache import cache

logger = get_logger(__name__)


class HealthStatus(str, Enum):
    """Статусы health check."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheck:
    """Результат отдельной проверки."""
    
    def __init__(
        self,
        name: str,
        status: HealthStatus,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        response_time_ms: Optional[float] = None
    ):
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}
        self.response_time_ms = response_time_ms
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь."""
        result = {
            "name": self.name,
            "status": self.status.value,
            "message": self.message
        }
        
        if self.details:
            result["details"] = self.details
        
        if self.response_time_ms is not None:
            result["response_time_ms"] = round(self.response_time_ms, 2)
        
        return result


class HealthChecker:
    """
    Комплексный health checker зависимостей.
    
    Проверяет:
    - Elasticsearch (подключение, индекс, cluster health)
    - Кэш (статус, hit rate)
    - Circuit Breaker (состояние)
    - Дисковое пространство
    - Использование памяти
    """
    
    def __init__(self):
        self.checks: List[HealthCheck] = []
    
    async def check_all(self) -> Dict[str, Any]:
        """
        Выполнить все проверки.
        
        Returns:
            Полный отчёт о здоровье системы
        """
        self.checks = []
        
        # Выполняем все проверки
        await self.check_elasticsearch()
        await self.check_cache()
        await self.check_circuit_breaker()
        await self.check_disk_space()
        await self.check_memory()
        
        # Определяем общий статус
        overall_status = self._calculate_overall_status()
        
        # Формируем отчёт
        return {
            "status": overall_status.value,
            "timestamp": time.time(),
            "checks": [check.to_dict() for check in self.checks],
            "summary": self._generate_summary(overall_status)
        }
    
    def _calculate_overall_status(self) -> HealthStatus:
        """Вычислить общий статус по результатам проверок."""
        has_unhealthy = any(c.status == HealthStatus.UNHEALTHY for c in self.checks)
        has_degraded = any(c.status == HealthStatus.DEGRADED for c in self.checks)
        
        if has_unhealthy:
            return HealthStatus.UNHEALTHY
        elif has_degraded:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY
    
    def _generate_summary(self, overall_status: HealthStatus) -> Dict[str, Any]:
        """Сгенерировать сводку по проверкам."""
        total_checks = len(self.checks)
        healthy_checks = sum(1 for c in self.checks if c.status == HealthStatus.HEALTHY)
        degraded_checks = sum(1 for c in self.checks if c.status == HealthStatus.DEGRADED)
        unhealthy_checks = sum(1 for c in self.checks if c.status == HealthStatus.UNHEALTHY)
        
        return {
            "total_checks": total_checks,
            "healthy": healthy_checks,
            "degraded": degraded_checks,
            "unhealthy": unhealthy_checks,
            "message": self._get_status_message(overall_status)
        }
    
    def _get_status_message(self, status: HealthStatus) -> str:
        """Получить сообщение статуса."""
        messages = {
            HealthStatus.HEALTHY: "Все системы работают нормально",
            HealthStatus.DEGRADED: "Некоторые системы работают с деградацией",
            HealthStatus.UNHEALTHY: "Критические проблемы с зависимостями"
        }
        return messages.get(status, "Неизвестный статус")
    
    async def check_elasticsearch(self) -> HealthCheck:
        """
        Проверка Elasticsearch.
        
        Проверяет:
        - Подключение
        - Наличие индекса
        - Cluster health
        - Circuit breaker состояние
        """
        start_time = time.time()
        
        try:
            # Проверка подключения
            connected = await es_client.is_connected()
            
            if not connected:
                check = HealthCheck(
                    name="elasticsearch",
                    status=HealthStatus.UNHEALTHY,
                    message="Elasticsearch недоступен",
                    response_time_ms=(time.time() - start_time) * 1000
                )
                self.checks.append(check)
                return check
            
            # Проверка индекса
            index_exists = await es_client.index_exists()
            
            if not index_exists:
                check = HealthCheck(
                    name="elasticsearch",
                    status=HealthStatus.DEGRADED,
                    message="Elasticsearch подключён, но индекс не существует",
                    details={"connected": True, "index_exists": False},
                    response_time_ms=(time.time() - start_time) * 1000
                )
                self.checks.append(check)
                return check
            
            # Получаем статистику
            docs_count = await es_client.get_documents_count()
            circuit_state = get_circuit_breaker_state()
            
            # Получаем cluster health (если доступно)
            cluster_health = "unknown"
            client = es_client.client
            if client:
                try:
                    health_response = await client.cluster.health()
                    cluster_health = health_response.get("status", "unknown")
                except (ConnectionError, TimeoutError) as e:
                    logger.warning(f"Cluster health check failed: {e}")
                except Exception as e:
                    logger.exception(f"Unexpected error getting cluster health: {e}")
            
            check = HealthCheck(
                name="elasticsearch",
                status=HealthStatus.HEALTHY,
                message="Elasticsearch работает нормально",
                details={
                    "connected": True,
                    "index_exists": True,
                    "documents_count": docs_count,
                    "cluster_health": cluster_health,
                    "circuit_breaker_state": circuit_state
                },
                response_time_ms=(time.time() - start_time) * 1000
            )
            
            self.checks.append(check)
            return check
            
        except Exception as e:
            check = HealthCheck(
                name="elasticsearch",
                status=HealthStatus.UNHEALTHY,
                message=f"Ошибка проверки Elasticsearch: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
            self.checks.append(check)
            return check
    
    async def check_cache(self) -> HealthCheck:
        """
        Проверка кэша.
        
        Проверяет:
        - Статус кэша
        - Hit rate
        - Количество записей
        """
        start_time = time.time()
        
        try:
            # Получаем статистику кэша
            stats = await cache.get_stats()
            
            hit_rate = stats.get("hit_rate", 0)
            total_keys = stats.get("total_keys", 0)
            
            # Определяем статус
            if hit_rate < 0.1 and total_keys == 0:
                status = HealthStatus.DEGRADED
                message = "Кэш работает, но пуст (hit rate 0%)"
            elif hit_rate < 0.3:
                status = HealthStatus.DEGRADED
                message = f"Кэш работает, но низкий hit rate ({hit_rate:.1%})"
            else:
                status = HealthStatus.HEALTHY
                message = f"Кэш работает нормально (hit rate {hit_rate:.1%})"
            
            check = HealthCheck(
                name="cache",
                status=status,
                message=message,
                details={
                    "enabled": True,
                    "hit_rate": f"{hit_rate:.2%}",
                    "total_keys": total_keys,
                    "hits": stats.get("hits", 0),
                    "misses": stats.get("misses", 0),
                    "evictions": stats.get("evictions", 0)
                },
                response_time_ms=(time.time() - start_time) * 1000
            )
            
            self.checks.append(check)
            return check
            
        except Exception as e:
            check = HealthCheck(
                name="cache",
                status=HealthStatus.UNHEALTHY,
                message=f"Ошибка проверки кэша: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
            self.checks.append(check)
            return check
    
    async def check_circuit_breaker(self) -> HealthCheck:
        """
        Проверка Circuit Breaker.
        
        Проверяет:
        - Текущее состояние
        - Статистика отказов
        """
        start_time = time.time()
        
        try:
            state = get_circuit_breaker_state()
            stats = get_circuit_breaker_stats()
            
            # Определяем статус
            if state == "open":
                status = HealthStatus.DEGRADED
                message = "Circuit breaker открыт (ES недоступен)"
            elif state == "half_open":
                status = HealthStatus.DEGRADED
                message = "Circuit breaker в режиме восстановления"
            else:
                status = HealthStatus.HEALTHY
                message = "Circuit breaker закрыт (нормальная работа)"
            
            check = HealthCheck(
                name="circuit_breaker",
                status=status,
                message=message,
                details={
                    "state": state,
                    "failure_count": stats.get("failure_count", 0),
                    "total_failures": stats.get("total_failures", 0),
                    "total_successes": stats.get("total_successes", 0),
                    "total_requests": stats.get("total_requests", 0),
                    "total_rejections": stats.get("total_rejections", 0)
                },
                response_time_ms=(time.time() - start_time) * 1000
            )
            
            self.checks.append(check)
            return check
            
        except Exception as e:
            check = HealthCheck(
                name="circuit_breaker",
                status=HealthStatus.UNHEALTHY,
                message=f"Ошибка проверки circuit breaker: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
            self.checks.append(check)
            return check
    
    async def check_disk_space(self) -> HealthCheck:
        """
        Проверка дискового пространства.
        
        Проверяет:
        - Свободное место
        - Процент использования
        """
        start_time = time.time()
        
        try:
            # Получаем информацию о диске
            disk = psutil.disk_usage('/')
            
            free_percent = (disk.free / disk.total) * 100
            free_gb = disk.free / (1024 ** 3)
            
            # Определяем статус
            if free_percent < 5:
                status = HealthStatus.UNHEALTHY
                message = f"Критически мало места на диске ({free_percent:.1f}%)"
            elif free_percent < 15:
                status = HealthStatus.DEGRADED
                message = f"Мало места на диске ({free_percent:.1f}%)"
            else:
                status = HealthStatus.HEALTHY
                message = f"Достаточно места на диске ({free_percent:.1f}%)"
            
            check = HealthCheck(
                name="disk_space",
                status=status,
                message=message,
                details={
                    "total_gb": round(disk.total / (1024 ** 3), 2),
                    "used_gb": round(disk.used / (1024 ** 3), 2),
                    "free_gb": round(free_gb, 2),
                    "free_percent": f"{free_percent:.1f}%",
                    "usage_percent": f"{disk.percent:.1f}%"
                },
                response_time_ms=(time.time() - start_time) * 1000
            )
            
            self.checks.append(check)
            return check
            
        except Exception as e:
            check = HealthCheck(
                name="disk_space",
                status=HealthStatus.UNHEALTHY,
                message=f"Ошибка проверки диска: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
            self.checks.append(check)
            return check
    
    async def check_memory(self) -> HealthCheck:
        """
        Проверка использования памяти.
        
        Проверяет:
        - Использование RAM
        - Доступная память
        """
        start_time = time.time()
        
        try:
            # Получаем информацию о памяти
            memory = psutil.virtual_memory()
            
            available_percent = memory.available / memory.total * 100
            available_gb = memory.available / (1024 ** 3)
            
            # Определяем статус
            if available_percent < 5:
                status = HealthStatus.UNHEALTHY
                message = f"Критически мало памяти ({available_percent:.1f}%)"
            elif available_percent < 15:
                status = HealthStatus.DEGRADED
                message = f"Мало памяти ({available_percent:.1f}%)"
            else:
                status = HealthStatus.HEALTHY
                message = f"Достаточно памяти ({available_percent:.1f}%)"
            
            check = HealthCheck(
                name="memory",
                status=status,
                message=message,
                details={
                    "total_gb": round(memory.total / (1024 ** 3), 2),
                    "available_gb": round(available_gb, 2),
                    "used_percent": f"{memory.percent:.1f}%",
                    "available_percent": f"{available_percent:.1f}%"
                },
                response_time_ms=(time.time() - start_time) * 1000
            )
            
            self.checks.append(check)
            return check
            
        except Exception as e:
            check = HealthCheck(
                name="memory",
                status=HealthStatus.UNHEALTHY,
                message=f"Ошибка проверки памяти: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
            self.checks.append(check)
            return check


# Глобальный экземпляр
health_checker = HealthChecker()


async def get_health_report() -> Dict[str, Any]:
    """Получить полный отчёт о здоровье системы."""
    return await health_checker.check_all()


async def get_basic_health() -> Dict[str, Any]:
    """Получить базовый health check (для совместимости)."""
    es_connected = await es_client.is_connected()
    index_exists = await es_client.index_exists() if es_connected else False
    docs_count = await es_client.get_documents_count() if index_exists else None
    
    return {
        "status": "healthy",
        "elasticsearch": es_connected,
        "index_exists": bool(index_exists) if index_exists else False,
        "documents_count": docs_count
    }
