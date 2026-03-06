"""Система логирования."""

import logging
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from src.core.config import settings


# Контекстная переменная для request_id
class LogContext:
    """Контекст для хранения request_id."""
    _request_id: Optional[str] = None
    _client_ip: Optional[str] = None
    _start_time: Optional[float] = None

    @classmethod
    def set_request_id(cls, request_id: str) -> None:
        """Устанавливает request_id для текущего запроса."""
        cls._request_id = request_id

    @classmethod
    def get_request_id(cls) -> Optional[str]:
        """Получает текущий request_id."""
        return cls._request_id

    @classmethod
    def set_client_ip(cls, client_ip: str) -> None:
        """Устанавливает client_ip для текущего запроса."""
        cls._client_ip = client_ip

    @classmethod
    def get_client_ip(cls) -> Optional[str]:
        """Получает текущий client_ip."""
        return cls._client_ip

    @classmethod
    def set_start_time(cls, start_time: float) -> None:
        """Устанавливает время начала запроса."""
        cls._start_time = start_time

    @classmethod
    def get_start_time(cls) -> Optional[float]:
        """Получает время начала запроса."""
        return cls._start_time

    @classmethod
    def clear(cls) -> None:
        """Очищает контекст."""
        cls._request_id = None
        cls._client_ip = None
        cls._start_time = None


class JSONFormatter(logging.Formatter):
    """Форматтер для вывода логов в JSON формате."""

    def format(self, record: logging.LogRecord) -> str:
        """Форматирует запись лога в JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Добавляем request_id из контекста
        request_id = LogContext.get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        # Добавляем client_ip из контекста
        client_ip = LogContext.get_client_ip()
        if client_ip:
            log_data["client_ip"] = client_ip

        # Добавляем duration если есть start_time
        start_time = LogContext.get_start_time()
        if start_time:
            duration_ms = (datetime.now(timezone.utc).timestamp() - start_time) * 1000
            log_data["duration_ms"] = round(duration_ms, 2)

        # Добавляем исключение, если есть
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Добавляем дополнительные поля
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """Настраивает систему логирования."""
    
    # Создаем директорию для логов
    logs_dir = Path(settings.logs_directory)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Основной логгер
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # Очищаем существующие обработчики
    logger.handlers.clear()
    
    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    if settings.debug:
        # В режиме разработки - простой формат
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    else:
        # В продакшене - JSON формат
        console_formatter = JSONFormatter()
    
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Файловый обработчик
    file_handler = logging.FileHandler(
        logs_dir / "app.log", 
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    # Обработчик для ошибок
    error_handler = logging.FileHandler(
        logs_dir / "errors.log", 
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    logger.addHandler(error_handler)
    
    # Настраиваем уровни для внешних библиотек
    logging.getLogger("elasticsearch").setLevel(logging.WARNING)
    logging.getLogger("elastic_transport").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Получает логгер с указанным именем."""
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """
    Логирует сообщение с контекстом запроса.
    
    Args:
        logger: Логгер для использования
        level: Уровень логирования (info, warning, error, debug)
        message: Сообщение для логирования
        extra: Дополнительные данные для добавления в лог
    """
    extra_data = {"extra_data": extra or {}}
    
    if level == "info":
        logger.info(message, extra=extra_data)
    elif level == "warning":
        logger.warning(message, extra=extra_data)
    elif level == "error":
        logger.error(message, extra=extra_data)
    elif level == "debug":
        logger.debug(message, extra=extra_data)
    elif level == "critical":
        logger.critical(message, extra=extra_data)


# Инициализируем логирование при импорте модуля
setup_logging()
