# 📊 Load Testing

**Дата:** 5 марта 2026  
**Задача:** 4.3 из плана оптимизации  
**Статус:** ✅ Выполнено

---

## 📋 Резюме

Load testing сценарии для проверки производительности под нагрузкой с использованием k6 и locust.

---

## ✅ Выполненные оптимизации

### 1. k6 Сценарии

**Файл:** `tests/load/k6_load_test.js`

**Характеристики:**
- 4 этапа нагрузки (разогрев, нагрузка, пик, остывание)
- Кастомные метрики (search_duration, health_duration, error_rate)
- Thresholds для автоматической проверки
- Автоматический отчёт

**Запуск:**
```bash
# Обычный тест (10 мин)
k6 run --duration 10m --vus 20 tests/load/k6_load_test.js

# Стресс тест (50 пользователей)
k6 run --duration 5m --vus 50 tests/load/k6_load_test.js

# Soak тест (30 мин)
k6 run --duration 30m --vus 20 tests/load/k6_load_test.js
```

**Метрики:**
- `http_req_duration` - время всех запросов
- `search_duration` - время поиска
- `health_duration` - время health checks
- `errors` - процент ошибок

**Thresholds:**
- p95 < 500ms для всех запросов
- p95 < 300ms для поиска
- p95 < 100ms для health checks
- error rate < 10%

---

### 2. Locust Сценарии

**Файл:** `tests/load/locustfile.py`

**Характеристики:**
- Web UI для мониторинга
- Распределение нагрузки (60% поиск, 20% MCP, 15% health, 5% detailed)
- Сбор метрик (p95, p99, error rate)
- Автоматический отчёт после теста

**Запуск:**
```bash
# Web UI
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Headless (20 пользователей, 30 мин)
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
  --headless -u 20 -r 2 --run-time 30m --csv=results/

# Стресс тест (100 пользователей)
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
  --headless -u 100 -r 10 --run-time 10m
```

**Метрики:**
- Total requests
- Errors
- Error rate
- Search P95/P99
- Health P95
- MCP P95

---

## 📊 Ожидаемые результаты

| Метрика | Target | Ожидаемое |
|---------|--------|-----------|
| **p95 (все запросы)** | < 500ms | 200-300ms |
| **p95 (поиск)** | < 300ms | 100-200ms |
| **p99 (поиск)** | < 500ms | 200-300ms |
| **p95 (health)** | < 100ms | 20-50ms |
| **Error rate** | < 1% | < 0.5% |
| **Concurrent users** | 50+ | 50-100 |

---

## 📁 Файлы

| Файл | Описание | Строк |
|------|----------|-------|
| `tests/load/k6_load_test.js` | k6 сценарий | ~250 |
| `tests/load/locustfile.py` | Locust сценарий | ~300 |
| `docs/plans/LOAD_TESTING.md` | Документация | ~200 |

---

## 🧪 Примеры использования

### Пример 1: Быстрый тест производительности

```bash
# 5 минут, 10 пользователей
k6 run --duration 5m --vus 10 tests/load/k6_load_test.js
```

**Ожидаемый результат:**
```
execution summary:
  total requests: 5000
  avg duration: 150ms
  p(95) duration: 250ms ✅
  p(99) duration: 350ms ✅
  error rate: 0.2% ✅
```

---

### Пример 2: Стресс тест

```bash
# 10 минут, 100 пользователей
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
  --headless -u 100 -r 10 --run-time 10m
```

**Ожидаемый результат:**
```
METRICS REPORT:
  total_requests: 50000
  errors: 250
  error_rate: 0.50%
  search_p95: 280ms
  search_p99: 380ms
  health_p95: 45ms
  mcp_p95: 250ms

THRESHOLDS:
  Search P95 < 300ms: ✅ (280ms)
  Error Rate < 1%: ✅ (0.50%)
```

---

### Пример 3: Soak тест (30 мин)

```bash
# 30 минут, 20 пользователей
k6 run --duration 30m --vus 20 tests/load/k6_load_test.js
```

**Цель:** Проверка на утечки памяти и стабильность

**Ожидаемый результат:**
- Нет деградации производительности со временем
- Error rate остаётся низким
- Memory usage стабильный

---

## 📈 Интерпретация результатов

### Отлично ✅
- p95 < 200ms
- p99 < 400ms
- error rate < 0.5%
- CPU < 50%
- Memory < 70%

### Хорошо ⚠️
- p95 < 400ms
- p99 < 600ms
- error rate < 2%
- CPU < 70%
- Memory < 85%

### Плохо ❌
- p95 > 500ms
- p99 > 1000ms
- error rate > 5%
- CPU > 90%
- Memory > 90%

---

## 🔗 Связанные документы

- [План оптимизации](./2026-03-05-optimization-roadmap.md)
- [CI/CD Pipeline](./CI_CD_PIPELINE.md)
- [Integration Tests](./INTEGRATION_TESTS.md)

---

**Статус:** ✅ **Задача 4.3 завершена!**  
**Прогресс Фазы 4:** 75% (3/4 задач выполнено)  
**Следующая задача:** 4.4 Мониторинг и метрики
