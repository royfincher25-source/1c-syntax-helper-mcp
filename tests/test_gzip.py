#!/usr/bin/env python3
"""Тесты для GzipMiddleware."""

import asyncio
import gzip
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from src.core.gzip_middleware import GzipMiddleware


def test_gzip_compression():
    """Тест сжатия больших ответов."""
    print("\n=== Тест 1: Сжатие больших ответов ===")
    
    app = FastAPI()
    app.add_middleware(GzipMiddleware, min_size=1024)
    
    @app.get("/large")
    def large_response():
        # Создаём ответ > 1KB
        return {"data": "x" * 2000}
    
    client = TestClient(app)
    response = client.get("/large")
    
    # Проверяем заголовок сжатия
    assert response.headers.get("Content-Encoding") == "gzip", \
        f"Ожидался заголовок 'gzip', получено {response.headers.get('Content-Encoding')}"
    print("✅ Заголовок Content-Encoding: gzip добавлен")
    
    # Проверяем, что данные сжаты
    decompressed = gzip.decompress(response.content)
    assert len(decompressed) > len(response.content), \
        "Сжатые данные должны быть меньше оригинала"
    print(f"✅ Степень сжатия: {len(response.content) / len(decompressed) * 100:.1f}%")
    
    # Проверяем целостность данных
    import json
    original_data = json.loads(decompressed)
    assert original_data["data"] == "x" * 2000
    print("✅ Данные восстановлены корректно")


def test_no_gzip_small_response():
    """Тест отсутствия сжатия для маленьких ответов."""
    print("\n=== Тест 2: Отсутствие сжатия для маленьких ответов ===")
    
    app = FastAPI()
    app.add_middleware(GzipMiddleware, min_size=1024)
    
    @app.get("/small")
    def small_response():
        # Создаём ответ < 1KB
        return {"data": "small"}
    
    client = TestClient(app)
    response = client.get("/small")
    
    # Проверяем отсутствие заголовка сжатия
    assert response.headers.get("Content-Encoding") != "gzip", \
        f"Не ожидался заголовок 'gzip' для маленького ответа"
    print("✅ Маленькие ответы не сжимаются")


def test_no_gzip_excluded_types():
    """Тест исключения типов контента из сжатия."""
    print("\n=== Тест 3: Исключение типов контента ===")
    
    app = FastAPI()
    app.add_middleware(GzipMiddleware, min_size=1024)
    
    @app.get("/image")
    def image_response():
        # Имитируем изображение
        return Response(
            content=b"fake_image_data" * 100,
            media_type="image/png"
        )
    
    client = TestClient(app)
    response = client.get("/image")
    
    # Проверяем отсутствие сжатия для изображений
    assert response.headers.get("Content-Encoding") != "gzip", \
        f"Не ожидался заголовок 'gzip' для изображений"
    print("✅ Изображения не сжимаются")


def test_gzip_json_response():
    """Тест сжатия JSON ответов."""
    print("\n=== Тест 4: Сжатие JSON ответов ===")
    
    app = FastAPI()
    app.add_middleware(GzipMiddleware, min_size=1024)
    
    @app.get("/api/data")
    def api_data():
        # JSON ответ > 1KB
        return {
            "results": [{"id": i, "name": f"item_{i}"} for i in range(100)],
            "total": 100
        }
    
    client = TestClient(app)
    response = client.get("/api/data")
    
    # Проверяем сжатие
    assert response.headers.get("Content-Encoding") == "gzip"
    
    # Проверяем, что JSON корректно восстанавливается
    decompressed = gzip.decompress(response.content)
    import json
    data = json.loads(decompressed)
    assert data["total"] == 100
    assert len(data["results"]) == 100
    print("✅ JSON ответы сжимаются и восстанавливаются корректно")


def test_gzip_compression_levels():
    """Тест различных уровней сжатия."""
    print("\n=== Тест 5: Уровни сжатия ===")
    
    test_data = {"data": "x" * 5000}
    
    for level in [1, 6, 9]:
        app = FastAPI()
        app.add_middleware(GzipMiddleware, min_size=1024, compress_level=level)
        
        @app.get("/test")
        def test_response():
            return test_data
        
        client = TestClient(app)
        response = client.get("/test")
        
        compressed_size = len(response.content)
        print(f"  Уровень {level}: {compressed_size} байт")
    
    # Проверяем, что уровень 9 сжимает лучше чем уровень 1
    app1 = FastAPI()
    app1.add_middleware(GzipMiddleware, min_size=1024, compress_level=1)
    app9 = FastAPI()
    app9.add_middleware(GzipMiddleware, min_size=1024, compress_level=9)
    
    @app1.get("/test")
    def test1():
        return test_data
    
    @app9.get("/test")
    def test9():
        return test_data
    
    client1 = TestClient(app1)
    client9 = TestClient(app9)
    
    response1 = client1.get("/test")
    response9 = client9.get("/test")
    
    assert len(response9.content) <= len(response1.content), \
        "Уровень 9 должен сжимать лучше уровня 1"
    print("✅ Уровни сжатия работают корректно")


def test_gzip_error_response():
    """Тест отсутствия сжатия для ошибок."""
    print("\n=== Тест 6: Отсутствие сжатия для ошибок ===")
    
    app = FastAPI()
    app.add_middleware(GzipMiddleware, min_size=1024)
    
    @app.get("/error")
    def error_response():
        return Response(
            content=b"Error: " + b"x" * 2000,
            status_code=500
        )
    
    client = TestClient(app)
    response = client.get("/error")
    
    # Проверяем отсутствие сжатия для ошибок
    assert response.headers.get("Content-Encoding") != "gzip", \
        f"Не ожидался заголовок 'gzip' для ошибок"
    print("✅ Ответы с ошибками не сжимаются")


def main():
    """Запускает все тесты."""
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ GzipMiddleware")
    print("="*60)
    
    test_gzip_compression()
    test_no_gzip_small_response()
    test_no_gzip_excluded_types()
    test_gzip_json_response()
    test_gzip_compression_levels()
    test_gzip_error_response()
    
    print("\n" + "="*60)
    print("ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ ✅")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
