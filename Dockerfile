# =============================================================================
# Multi-stage Dockerfile для 1C Syntax Helper MCP Server
# =============================================================================
# Этапы:
#   1. builder - сборка и установка зависимостей
#   2. production - минимальный runtime образ
# =============================================================================

# -----------------------------------------------------------------------------
# Этап 1: Builder - установка зависимостей
# -----------------------------------------------------------------------------
FROM python:3.11-slim as builder

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y \
    curl \
    p7zip-full \
    unzip \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Создание виртуального окружения для изоляции зависимостей
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копирование requirements и установка зависимостей
# Разделяем production и dev зависимости для оптимизации
COPY requirements.txt .

# Установка зависимостей с кэшированием wheel для ускорения сборки
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Этап 2: Production - минимальный runtime образ
# -----------------------------------------------------------------------------
FROM python:3.11-slim as production

# Метаданные образа
LABEL maintainer="1C Syntax Helper Team"
LABEL version="1.0.0"
LABEL description="MCP сервер для поиска по синтаксису 1С"

# Создание не-root пользователя для безопасности
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Установка только runtime зависимостей (без build инструментов)
RUN apt-get update && apt-get install -y \
    curl \
    p7zip-full \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Создание рабочей директории
WORKDIR /app

# Копирование виртуального окружения из builder этапа
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копирование исходного кода
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup requirements.txt .

# Создание директорий для данных и логов
RUN mkdir -p /app/data/hbk /app/logs && \
    chown -R appuser:appgroup /app

# Установка переменных окружения
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Переключение на не-root пользователя
USER appuser

# Открытие порта
EXPOSE 8000

# Health check для проверки работоспособности
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Команда запуска приложения
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# Этап 3: Development - образ для разработки (опционально)
# =============================================================================
# Для использования: docker build --target development -t myapp:dev .
# =============================================================================
FROM production as development

# Переключение на root для установки dev инструментов
USER root

# Установка dev зависимостей
RUN apt-get update && apt-get install -y \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Копирование dev зависимостей и установка
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt || echo "Dev dependencies installation failed"

# Переключение обратно на appuser
USER appuser

# Dev команда запуска (с auto-reload)
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
