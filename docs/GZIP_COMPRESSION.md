# 🗜️ Gzip Компрессия Ответов

## 📊 Обзор

Middleware для автоматической Gzip компрессии HTTP ответов, уменьшающий размер передаваемых данных на 50-80%.

---

## 🎯 Возможности

### 1. Автоматическое сжатие
- Сжатие ответов больше 1KB
- Прозрачное добавление заголовка `Content-Encoding: gzip`
- Сохранение оригинальных заголовков

### 2. Умные исключения
- Не сжимает ответы < 1KB
- Не сжимает изображения, видео, аудио
- Не сжимает уже сжатые форматы (PDF, ZIP)
- Не сжимает ответы с ошибками (4xx, 5xx)

### 3. Настраиваемые уровни
- Регулируемый уровень сжатия (1-9)
- Настройка минимального размера
- Исключение типов контента

---

## 📁 Архитектура

```
src/core/gzip_middleware.py
└── GzipMiddleware
    ├── __init__(min_size, compress_level, exclude_types)
    ├── dispatch(request, call_next)
    └── _should_compress(response)
```

---

## 🔧 Использование

### Базовая настройка

```python
from fastapi import FastAPI
from src.core.gzip_middleware import GzipMiddleware

app = FastAPI()

# Добавляем middleware
app.add_middleware(GzipMiddleware, min_size=1024, compress_level=6)
```

### Конфигурация

```python
app.add_middleware(
    GzipMiddleware,
    min_size=1024,              # Минимальный размер: 1KB
    compress_level=6,           # Уровень сжатия: 1-9
    exclude_content_types=[     # Исключения
        "image/",
        "video/",
        "audio/",
        "application/pdf",
    ]
)
```

---

## 📊 Параметры

### min_size (int)

Минимальный размер ответа в байтах для сжатия.

**По умолчанию:** 1024 (1KB)

```python
# Сжимать ответы больше 500 байт
app.add_middleware(GzipMiddleware, min_size=500)
```

### compress_level (int)

Уровень сжатия gzip (1-9).

| Уровень | Скорость | Степень сжатия | Использование |
|---------|----------|----------------|---------------|
| 1-3 | Быстро | Низкая | Редко |
| 4-6 | Средне | Средняя | **Рекомендуется** |
| 7-9 | Медленно | Высокая | Для статических данных |

**По умолчанию:** 6 (оптимальный баланс)

### exclude_content_types (List[str])

Список типов контента для исключения из сжатия.

**По умолчанию:**
```python
[
    "image/",
    "video/",
    "audio/",
    "application/pdf",
    "application/zip",
    "application/x-tar",
]
```

---

## 📈 Эффект сжатия

### Примеры для JSON ответов:

| Размер оригинала | Размер сжатого | Степень сжатия |
|------------------|----------------|----------------|
| 1KB | 600B | 40% ↓ |
| 10KB | 2KB | 80% ↓ |
| 100KB | 15KB | 85% ↓ |
| 1MB | 100KB | 90% ↓ |

### Для MCP ответов:

```
Запрос: search_1c_syntax("СтрДлина")
Оригинал: 2.5KB
Сжатый: 1.2KB
Экономия: 52%
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
python tests/test_gzip.py
```

### Ручная проверка

```bash
# Запрос с принятием сжатия
curl -H "Accept-Encoding: gzip" http://localhost:8002/health

# Проверка заголовков
curl -I http://localhost:8002/cache/stats

# Должно появиться:
# Content-Encoding: gzip
```

---

## 🔍 Логи

### Пример логов

```json
{
  "timestamp": "2026-03-05T16:00:00.000Z",
  "level": "DEBUG",
  "message": "Gzip сжатие: POST /mcp",
  "original_size": 5120,
  "compressed_size": 1536,
  "compression_ratio_percent": 70.0
}
```

---

## 🎓 Лучшие практики

### ✅ Делайте

- Используйте уровень сжатия 6 для баланса
- Устанавливайте min_size 1KB для избежания накладных расходов
- Исключайте уже сжатые форматы
- Мониторьте степень сжатия в логах

### ❌ Не делайте

- Не используйте уровень 9 для динамических ответов
- Не сжимайте ответы < 500 байт
- Не сжимайте изображения (они уже сжаты)
- Не сжимайте ответы с ошибками

---

## 📊 Мониторинг

### Метрики для отслеживания

| Метрика | Описание | Target |
|---------|----------|--------|
| **Compression Ratio** | Средний % сжатия | > 50% |
| **Saved Traffic** | Сэкономленный трафик | > 40% |
| **CPU Overhead** | Накладные расходы CPU | < 5% |

### Команды для мониторинга

```bash
# Проверка заголовков
curl -I http://localhost:8002/health

# Поиск логов сжатия
grep "Gzip сжатие" data/logs/app.log | jq

# Статистика сжатия
grep "compression_ratio" data/logs/app.log | \
  jq -s '[.[].compression_ratio_percent] | add / length'
```

---

## 🔗 Взаимодействие с другими middleware

### Порядок middleware:

```
Request
  ↓
[GzipMiddleware] ← проверяет ответ
  ↓
[RequestLoggingMiddleware] ← логирует с request_id
  ↓
[RateLimitMiddleware] ← проверяет лимиты
  ↓
[FastAPI Router]
  ↓
Response
  ↓
[GzipMiddleware] ← сжимает если нужно
```

### Совместимость:

- ✅ RequestLoggingMiddleware
- ✅ RateLimitMiddleware
- ✅ CORSMiddleware
- ✅ CacheMiddleware

---

## 🛠️ Расширенные возможности

### Проверка эффективности сжатия

```python
# В middleware
if len(compressed_body) >= len(body):
    # Сжатие неэффективно, возвращаем оригинал
    return Response(body, ...)
```

### Динамическое исключение

```python
# Не сжимать если запрос от internal сервиса
if request.headers.get("X-Internal-Request"):
    return response  # без сжатия
```

---

## 📊 Ожидаемые улучшения

| Метрика | До компрессии | После компрессии | Улучшение |
|---------|---------------|------------------|-----------|
| **Размер ответов** | 100% | 40-60% | **↓ 40-60%** 📉 |
| **Время загрузки** | 100ms | 60ms | **1.7x** ⚡ |
| **Трафик** | 1GB/день | 500MB/день | **↓ 50%** 📉 |

---

## 🔗 Ссылки

- [gzip_middleware.py](../src/core/gzip_middleware.py)
- [test_gzip.py](../tests/test_gzip.py)
- [Structured Logging](./STRUCTURED_LOGGING.md)
- [In-memory Cache](./IN_MEMORY_CACHE.md)

---

**Обновлено:** 5 марта 2026  
**Версия:** 1.0 (Gzip Компрессия)
