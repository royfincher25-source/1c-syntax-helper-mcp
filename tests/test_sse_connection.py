"""Тест SSE подключения к MCP серверу."""

import asyncio
import httpx
import json
import time


async def test_sse_connection():
    """Тестирует SSE endpoint для MCP протокола."""
    print("=" * 60)
    print("Тестирование SSE подключения к MCP серверу")
    print("=" * 60)
    
    base_url = "http://localhost:8002"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Шаг 1: Проверяем доступность сервера
            print("\n[1] Проверка доступности сервера...")
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print(f"✅ Сервер доступен: {response.json()}")
            else:
                print(f"❌ Сервер недоступен: {response.status_code}")
                return
            
            # Шаг 2: Проверяем SSE endpoint
            print("\n[2] Проверка SSE endpoint (/mcp GET)...")
            session_id = None
            endpoint_url = None
            
            try:
                async with client.stream(
                    "GET",
                    f"{base_url}/mcp",
                    headers={"Accept": "text/event-stream"}
                ) as response:
                    print(f"✅ SSE соединение установлено, статус: {response.status_code}")
                    
                    # Читаем первые события
                    event_count = 0
                    async for line in response.aiter_lines():
                        event_count += 1
                        print(f"   Событие {event_count}: {line}")
                        
                        if line.startswith("event: endpoint"):
                            # Следующая строка должна содержать URL
                            pass
                        elif line.startswith("data: /mcp?session_id="):
                            session_id = line.split("session_id=")[1]
                            endpoint_url = line.split("data: ")[1]
                            print(f"✅ Получен session_id: {session_id}")
                            print(f"✅ Endpoint URL: {endpoint_url}")
                            break
                        
                        if event_count > 10:  # Ограничиваем количество событий
                            break
                            
            except Exception as e:
                print(f"❌ Ошибка SSE соединения: {e}")
                return
            
            if not session_id:
                print("❌ Не удалось получить session_id")
                return
            
            # Шаг 3: Отправляем JSON-RPC запрос через POST с session_id
            print(f"\n[3] Отправка JSON-RPC запроса через POST /mcp?session_id={session_id}...")
            
            jsonrpc_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
            
            response = await client.post(
                f"{base_url}/mcp?session_id={session_id}",
                json=jsonrpc_request
            )
            
            print(f"   Статус ответа: {response.status_code}")
            print(f"   Ответ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
            
            # Шаг 4: Проверяем прямой POST запрос (без SSE)
            print("\n[4] Проверка прямого POST запроса (без SSE)...")
            
            direct_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "find_1c_help",
                    "arguments": {"query": "СтрДлина", "limit": 2}
                }
            }
            
            response = await client.post(
                f"{base_url}/mcp",
                json=direct_request
            )
            
            print(f"   Статус ответа: {response.status_code}")
            result = response.json()
            if "result" in result:
                print(f"   ✅ Прямой POST работает")
                # Показываем сокращённый ответ
                content = result["result"].get("content", [])
                if content:
                    print(f"   Найдено элементов: {len(content)}")
            else:
                print(f"   Ответ: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}")
            
            # Шаг 5: Проверяем WebSocket endpoint
            print("\n[5] Проверка WebSocket endpoint (/mcp/ws)...")
            try:
                async with client.websocket_connect(f"{base_url}/mcp/ws") as websocket:
                    print("✅ WebSocket соединение установлено")
                    
                    # Отправляем тестовое сообщение
                    test_message = {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/list",
                        "params": {}
                    }
                    await websocket.send_json(test_message)
                    
                    # Получаем ответ
                    response = await websocket.receive_json()
                    print(f"   ✅ Получен ответ через WebSocket")
                    print(f"   Ответ: {json.dumps(response, indent=2, ensure_ascii=False)[:300]}")
                    
            except Exception as e:
                print(f"⚠️ WebSocket недоступен: {e}")
            
            print("\n" + "=" * 60)
            print("✅ Тестирование завершено")
            print("=" * 60)
            
        except httpx.ConnectError as e:
            print(f"\n❌ Не удалось подключиться к серверу: {e}")
            print("   Убедитесь, что сервер запущен на http://localhost:8002")
        except Exception as e:
            print(f"\n❌ Ошибка тестирования: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_sse_connection())
