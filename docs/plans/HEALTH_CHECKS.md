# 🏥 Health Checks зависимостей

**Дата:** 5 марта 2026  
**Задача:** 3.3 из плана оптимизации  
**Статус:** ✅ Выполнено

---

## 📋 Резюме

Детальный health check для мониторинга всех зависимостей системы: Elasticsearch, кэш, circuit breaker, дисковое пространство, память.

---

## ✅ Выполненные оптимизации

### 1. HealthChecker с 5 проверками

**Проверки:**
1. **Elasticsearch** - подключение, индекс, cluster health, circuit breaker state
2. **Кэш** - статус, hit rate, количество записей
3. **Circuit Breaker** - состояние, статистика отказов
4. **Дисковое пространство** - свободно/занято, процент использования
5. **Память** - доступная RAM, процент использования

**Статусы:**
- `HEALTHY` - все системы работают нормально
- `DEGRADED` - некоторые системы работают с деградацией
- `UNHEALTHY` - критические проблемы с зависимостями

---

### 2. Endpoint /health/detailed

**Базовый health check:**
```
GET /health
```

**Ответ:**
```json
{
  "status": "healthy",
  "elasticsearch": true,
  "index_exists": true,
  "documents_count": 1000
}
```

**Детальный health check:**
```
GET /health/detailed
```

**Ответ:**
```json
{
  "status": "healthy",
  "timestamp": 1709654400,
  "checks": [
    {
      "name": "elasticsearch",
      "status": "healthy",
      "message": "Elasticsearch работает нормально",
      "details": {
        "connected": true,
        "index_exists": true,
        "documents_count": 1000,
        "cluster_health": "green",
        "circuit_breaker_state": "closed"
      },
      "response_time_ms": 15.2
    },
    {
      "name": "cache",
      "status": "healthy",
      "message": "Кэш работает нормально (hit rate 45.2%)",
      "details": {
        "hit_rate": "45.20%",
        "total_keys": 150,
        "hits": 452,
        "misses": 548
      },
      "response_time_ms": 2.1
    },
    {
      "name": "circuit_breaker",
      "status": "healthy",
      "message": "Circuit breaker закрыт (нормальная работа)",
      "details": {
        "state": "closed",
        "failure_count": 0,
        "total_requests": 100
      },
      "response_time_ms": 1.0
    },
    {
      "name": "disk_space",
      "status": "healthy",
      "message": "Достаточно места на диске (60.0%)",
      "details": {
        "total_gb": 500.0,
        "free_gb": 300.0,
        "free_percent": "60.0%"
      },
      "response_time_ms": 3.5
    },
    {
      "name": "memory",
      "status": "healthy",
      "message": "Достаточно памяти (50.0%)",
      "details": {
        "total_gb": 16.0,
        "available_gb": 8.0,
        "available_percent": "50.0%"
      },
      "response_time_ms": 2.8
    }
  ],
  "summary": {
    "total_checks": 5,
    "healthy": 5,
    "degraded": 0,
    "unhealthy": 0,
    "message": "Все системы работают нормально"
  }
}
```

---

## 📁 Измененные файлы

### 1. `src/core/health.py` (новый)

**Классы:**
- `HealthStatus` - enum статусов (HEALTHY, DEGRADED, UNHEALTHY)
- `HealthCheck` - результат отдельной проверки
- `HealthChecker` - основной класс с проверками

**Методы HealthChecker:**
- `check_all()` - выполнить все проверки
- `check_elasticsearch()` - проверка ES
- `check_cache()` - проверка кэша
- `check_circuit_breaker()` - проверка circuit breaker
- `check_disk_space()` - проверка диска
- `check_memory()` - проверка памяти

**Функции:**
- `get_health_report()` - полный отчёт
- `get_basic_health()` - базовый health (для совместимости)

---

### 2. `src/main.py`

**Изменения:**
- Импорт `get_health_report`, `get_basic_health`
- Endpoint `/health` - базовый health check
- Endpoint `/health/detailed` - детальный health check

---

## 📊 Ожидаемые улучшения

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| **Видимость проблем** | Частичная | Полная | **100%** ✅ |
| **Время обнаружения** | 5+ мин | < 1 мин | **5x** ⚡ |
| **Мониторинг зависимостей** | 1 (ES) | 5 | **5x** 📈 |
| **Graceful degradation** | Не виден | Видно в health | **100%** ✅ |

---

## 🧪 Тестирование

### Тест 1: Базовый health check

```bash
curl http://localhost:8000/health
```

**Ожидаемый ответ:**
```json
{
  "status": "healthy",
  "elasticsearch": true,
  "index_exists": true
}
```

---

### Тест 2: Детальный health check

```bash
curl http://localhost:8000/health/detailed | jq
```

**Ожидаемый ответ:** См. пример выше

---

### Тест 3: Проверка при сбое ES

```bash
# Остановить Elasticsearch
docker-compose stop elasticsearch

# Через 1 минуту проверить health
curl http://localhost:8000/health/detailed | jq '.status'
# Ожидаемый ответ: "degraded" или "unhealthy"
```

---

## 🔗 Связанные документы

- [План оптимизации](./2026-03-05-optimization-roadmap.md)
- [Circuit Breaker](./CIRCUIT_BREAKER.md)

---

**Статус:** ✅ **Задача 3.3 завершена!**  
**Прогресс Фазы 3:** 50% (2/4 задач выполнено)  
**Следующая задача:** 3.4 Graceful Shutdown
