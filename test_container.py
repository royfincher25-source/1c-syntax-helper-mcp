"""Тест для проверки list_object_members внутри контейнера."""

import asyncio
import logging
import sys

# Включаем DEBUG логирование
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(message)s',
    stream=sys.stdout
)

async def test_object_members():
    """Проверяет работу ObjectMembersService."""
    from src.core.elasticsearch import es_client
    from src.search.object_members_service import object_members_service
    
    print("=" * 60)
    print("ТЕСТ 1: Проверка подключения к Elasticsearch")
    print("=" * 60)
    
    connected = await es_client.is_connected()
    print(f"Подключено: {connected}")
    
    if not connected:
        print("Попытка подключения...")
        connected = await es_client.connect()
        print(f"Подключено после connect(): {connected}")
    
    print("\n" + "=" * 60)
    print("ТЕСТ 2: Прямой запрос к Elasticsearch")
    print("=" * 60)
    
    query = {
        "query": {"term": {"object.keyword": "ЧтениеТекста"}},
        "size": 3
    }
    print(f"Запрос: {query}")
    
    response = await es_client.search(query)
    if response:
        total = response.get('hits', {}).get('total', {}).get('value', 0)
        print(f"Результатов: {total}")
        if total > 0:
            doc = response['hits']['hits'][0]['_source']
            print(f"Пример: object={doc.get('object')}, type={doc.get('type')}, name={doc.get('name')}")
    else:
        print("Ответ: None")
    
    print("\n" + "=" * 60)
    print("ТЕСТ 3: Вызов object_members_service.get_object_members_list")
    print("=" * 60)
    
    result = await object_members_service.get_object_members_list("ЧтениеТекста", "all", 50)
    print(f"Total: {result.get('total')}")
    print(f"Methods: {len(result.get('methods', []))}")
    print(f"Properties: {len(result.get('properties', []))}")
    print(f"Events: {len(result.get('events', []))}")
    
    if result.get('error'):
        print(f"Ошибка: {result['error']}")
    
    print("\n" + "=" * 60)
    print("ТЕСТ 4: Проверка search_service.members")
    print("=" * 60)
    
    from src.search.search_service import search_service
    from src.search.object_members_service import object_members_service as oms_global
    
    print(f"search_service.members is object_members_service: {search_service.members is oms_global}")
    
    result2 = await search_service.get_object_members_list("ЧтениеТекста", "all", 50)
    print(f"search_service result - Total: {result2.get('total')}")


if __name__ == "__main__":
    asyncio.run(test_object_members())
