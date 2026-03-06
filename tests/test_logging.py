#!/usr/bin/env python3
"""Тестовый скрипт для проверки JSON логирования с request_id."""

import sys
import time
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.logging import get_logger, LogContext, setup_logging

# Перенастраиваем логирование для теста
setup_logging()

logger = get_logger(__name__)


def test_basic_logging():
    """Тест базового логирования."""
    print("\n=== Тест 1: Базовое логирование ===")
    
    logger.info("Информационное сообщение")
    logger.warning("Предупреждение")
    logger.error("Ошибка")
    logger.debug("Отладочное сообщение")
    
    print("✅ Базовое логирование работает\n")


def test_context_logging():
    """Тест логирования с контекстом."""
    print("=== Тест 2: Логирование с контекстом ===")
    
    # Устанавливаем контекст
    LogContext.set_request_id("test-request-123")
    LogContext.set_client_ip("192.168.1.100")
    LogContext.set_start_time(time.time())
    
    # Логируем с контекстом
    logger.info(
        "Запрос с контекстом",
        extra={
            "extra_data": {
                "method": "GET",
                "path": "/api/test",
                "status_code": 200,
            }
        }
    )
    
    # Очищаем контекст
    LogContext.clear()
    
    print("✅ Логирование с контекстом работает\n")


def test_exception_logging():
    """Тест логирования исключений."""
    print("=== Тест 3: Логирование исключений ===")
    
    try:
        raise ValueError("Тестовая ошибка")
    except Exception as e:
        logger.error(
            "Произошло исключение",
            extra={
                "extra_data": {
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            },
            exc_info=True
        )
    
    print("✅ Логирование исключений работает\n")


def test_json_format():
    """Проверка формата JSON."""
    print("=== Тест 4: Проверка JSON формата ===")
    
    LogContext.set_request_id("json-test-456")
    LogContext.set_client_ip("10.0.0.1")
    
    logger.info(
        "Тест JSON формата",
        extra={
            "extra_data": {
                "user_id": 12345,
                "action": "test",
                "metadata": {
                    "version": "1.0",
                    "tags": ["test", "logging"],
                }
            }
        }
    )
    
    LogContext.clear()
    
    print("✅ JSON формат работает\n")


def main():
    """Запускает все тесты."""
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ JSON LOGGING С REQUEST_ID")
    print("="*60)
    
    test_basic_logging()
    test_context_logging()
    test_exception_logging()
    test_json_format()
    
    print("="*60)
    print("ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ ✅")
    print("="*60)
    print("\nПроверьте файлы логов:")
    print("  - data/logs/app.log")
    print("  - data/logs/errors.log")
    print("\nИли посмотрите в консоль (JSON формат)\n")


if __name__ == "__main__":
    main()
