"""Тестовый MCP клиент для проверки SSE подключения."""

import asyncio
import aiohttp
import json

async def test_sse_connection():
    """Тестирует SSE подключение к MCP серверу."""
    
    async with aiohttp.ClientSession() as session:
        # Шаг 1: GET /sse для получения session_id
        print("Шаг 1: Подключение к SSE endpoint...")
        async with session.get("http://localhost:8002/sse") as response:
            print(f"Status: {response.status}")
            print(f"Headers: {dict(response.headers)}")
            
            # Читаем первые несколько событий
            event_count = 0
            async for line in response.content:
                line = line.decode('utf-8').strip()
                print(f"SSE: {line}")
                event_count += 1
                
                if event_count >= 5:  # Прочитать 5 событий
                    break
        
        # Шаг 2: POST initialize запрос
        print("\nШаг 2: Отправка initialize запроса...")
        async with session.post(
            "http://localhost:8002/sse",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        ) as response:
            result = await response.json()
            print(f"Response: {json.dumps(result, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    asyncio.run(test_sse_connection())
