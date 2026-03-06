"""Тесты lazy loading примеров."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.search.search_service import SearchService
from src.search.formatter import SearchFormatter


class TestIncludeExamplesParameter:
    """Тесты параметра include_examples."""

    @pytest.mark.asyncio
    async def test_find_help_without_examples_by_default(self):
        """Проверка что поиск по умолчанию не возвращает примеры."""
        service = SearchService()
        
        # Мокаем зависимости
        with patch.object(service, '_SearchService__setup_deps', return_value=None):
            with patch('src.search.search_service.es_client') as mock_es, \
                 patch('src.search.search_service.cache') as mock_cache:
                
                # Настраиваем моки
                mock_cache.get = AsyncMock(return_value=None)
                mock_cache.set = AsyncMock()
                mock_es.is_connected = AsyncMock(return_value=True)
                mock_es.search = AsyncMock(return_value={
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "name": "СтрДлина",
                                    "type": "global_function",
                                    "examples": ["Пример 1", "Пример 2"]
                                }
                            }
                        ],
                        "total": {"value": 1}
                    }
                })
                
                # Выполняем поиск (без include_examples)
                result = await service.find_help_by_query("СтрДлина")
                
                # Проверяем что примеры не включены
                assert result['examples_included'] is False
                
                # Проверяем что formatter был вызван с include_examples=False
                # (это проверяется через результат - примеры не должны быть включены)
                for r in result['results']:
                    # Примеры не должны быть в результате или пустые
                    assert 'examples' not in r or len(r.get('examples', [])) == 0

    @pytest.mark.asyncio
    async def test_find_help_with_examples(self):
        """Проверка что поиск с include_examples=True возвращает примеры."""
        service = SearchService()
        
        with patch('src.search.search_service.es_client') as mock_es, \
             patch('src.search.search_service.cache') as mock_cache:
            
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_es.is_connected = AsyncMock(return_value=True)
            mock_es.search = AsyncMock(return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "name": "СтрДлина",
                                "type": "global_function",
                                "examples": ["Пример 1", "Пример 2"]
                            }
                        }
                    ],
                    "total": {"value": 1}
                }
            })
            
            # Выполняем поиск с include_examples=True
            result = await service.find_help_by_query(
                "СтрДлина",
                include_examples=True
            )
            
            # Проверяем что примеры включены
            assert result['examples_included'] is True

    @pytest.mark.asyncio
    async def test_cache_key_includes_examples_flag(self):
        """Проверка что cache key включает флаг include_examples."""
        service = SearchService()
        
        with patch('src.search.search_service.es_client') as mock_es, \
             patch('src.search.search_service.cache') as mock_cache:
            
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_es.is_connected = AsyncMock(return_value=True)
            mock_es.search = AsyncMock(return_value={
                "hits": {"hits": [], "total": {"value": 0}}
            })
            
            # Поиск без примеров
            await service.find_help_by_query("СтрДлина", include_examples=False)
            
            # Поиск с примерами
            await service.find_help_by_query("СтрДлина", include_examples=True)
            
            # Проверяем что cache.set был вызван с разными ключами
            calls = mock_cache.set.call_args_list
            assert len(calls) >= 2
            
            # Ключи должны быть разными
            key1 = calls[0][0][0]
            key2 = calls[1][0][0]
            assert key1 != key2
            assert 'False' in key1 or 'False' in key2
            assert 'True' in key1 or 'True' in key2


class TestGetExamplesForElement:
    """Тесты отдельного получения примеров."""

    @pytest.mark.asyncio
    async def test_get_examples_for_global_function(self):
        """Проверка получения примеров для глобальной функции."""
        service = SearchService()
        
        with patch('src.search.search_service.es_client') as mock_es, \
             patch('src.search.search_service.cache') as mock_cache:
            
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_es.is_connected = AsyncMock(return_value=True)
            mock_es.search = AsyncMock(return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "name": "СтрДлина",
                                "examples": [
                                    "Длина = СтрДлина(\"Пример\");",
                                    "Если СтрДлина(Текст) > 10 Тогда ..."
                                ]
                            }
                        }
                    ],
                    "total": {"value": 1}
                }
            })
            
            # Получаем примеры
            result = await service.get_examples_for_element("СтрДлина")
            
            # Проверяем результат
            assert result['element'] == "СтрДлина"
            assert result['object'] is None
            assert len(result['examples']) > 0
            assert result['total'] > 0

    @pytest.mark.asyncio
    async def test_get_examples_for_object_method(self):
        """Проверка получения примеров для метода объекта."""
        service = SearchService()
        
        with patch('src.search.search_service.es_client') as mock_es, \
             patch('src.search.search_service.cache') as mock_cache:
            
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_es.is_connected = AsyncMock(return_value=True)
            mock_es.search = AsyncMock(return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "name": "Добавить",
                                "object": "ТаблицаЗначений",
                                "examples": [
                                    "НоваяСтрока = Таблица.Добавить();"
                                ]
                            }
                        }
                    ],
                    "total": {"value": 1}
                }
            })
            
            # Получаем примеры для метода объекта
            result = await service.get_examples_for_element(
                "Добавить",
                object_name="ТаблицаЗначений"
            )
            
            # Проверяем результат
            assert result['element'] == "Добавить"
            assert result['object'] == "ТаблицаЗначений"
            assert len(result['examples']) > 0

    @pytest.mark.asyncio
    async def test_get_examples_from_cache(self):
        """Проверка получения примеров из кэша."""
        service = SearchService()
        
        with patch('src.search.search_service.es_client') as mock_es, \
             patch('src.search.search_service.cache') as mock_cache:
            
            # Кэш возвращает примеры
            mock_cache.get = AsyncMock(return_value={
                "element": "СтрДлина",
                "examples": ["Кэшированный пример"],
                "total": 1
            })
            mock_cache.set = AsyncMock()
            
            # Получаем примеры
            result = await service.get_examples_for_element("СтрДлина")
            
            # Проверяем что кэш был использован
            assert mock_cache.get.called
            # ES не должен быть запрошен
            assert not mock_es.search.called
            
            # Проверяем результат из кэша
            assert result['examples'] == ["Кэшированный пример"]

    @pytest.mark.asyncio
    async def test_get_examples_element_not_found(self):
        """Проверка обработки случая когда элемент не найден."""
        service = SearchService()
        
        with patch('src.search.search_service.es_client') as mock_es, \
             patch('src.search.search_service.cache') as mock_cache:
            
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_es.is_connected = AsyncMock(return_value=True)
            mock_es.search = AsyncMock(return_value={
                "hits": {"hits": [], "total": {"value": 0}}
            })
            
            # Получаем примеры
            result = await service.get_examples_for_element("НесуществующаяФункция")
            
            # Проверяем результат
            assert result['element'] == "НесуществующаяФункция"
            assert result['examples'] == []
            assert result['total'] == 0
            assert 'error' in result

    @pytest.mark.asyncio
    async def test_get_examples_limits_results(self):
        """Проверка что результаты ограничены limit."""
        service = SearchService()
        
        with patch('src.search.search_service.es_client') as mock_es, \
             patch('src.search.search_service.cache') as mock_cache:
            
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_es.is_connected = AsyncMock(return_value=True)
            mock_es.search = AsyncMock(return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "name": "СтрДлина",
                                "examples": [f"Пример {i}" for i in range(20)]
                            }
                        }
                    ],
                    "total": {"value": 1}
                }
            })
            
            # Получаем примеры с limit=5
            result = await service.get_examples_for_element(
                "СтрДлина",
                limit=5
            )
            
            # Проверяем что количество примеров ограничено
            assert len(result['examples']) <= 5


class TestSearchFormatterExamples:
    """Тесты formatter с include_examples."""

    def test_format_without_examples_by_default(self):
        """Проверка что formatter по умолчанию не включает примеры."""
        formatter = SearchFormatter()
        
        doc = {
            "name": "СтрДлина",
            "type": "global_function",
            "examples": ["Пример 1", "Пример 2"]
        }
        
        # Форматируем без указания include_examples
        result = formatter.format_search_results([{"document": doc, "score": 1.0}])
        
        # Проверяем что примеры не включены
        for r in result:
            assert 'examples' not in r or len(r.get('examples', [])) == 0

    def test_format_with_examples(self):
        """Проверка что formatter включает примеры когда запрошено."""
        formatter = SearchFormatter()
        
        doc = {
            "name": "СтрДлина",
            "type": "global_function",
            "examples": ["Пример 1", "Пример 2"]
        }
        
        # Форматируем с include_examples=True
        result = formatter.format_search_results(
            [{"document": doc, "score": 1.0}],
            include_examples=True
        )
        
        # Проверяем что примеры включены
        for r in result:
            assert 'examples' in r
            assert len(r['examples']) > 0

    def test_format_document_respects_include_examples(self):
        """Проверка что _format_document уважает флаг include_examples."""
        formatter = SearchFormatter()
        
        doc = {
            "name": "СтрДлина",
            "examples": ["Пример"]
        }
        
        # Без примеров
        result_without = formatter._format_document(doc, include_examples=False)
        assert 'examples' not in result_without
        
        # С примерами
        result_with = formatter._format_document(doc, include_examples=True)
        assert 'examples' in result_with
        assert len(result_with['examples']) > 0


class TestLazyLoadingIntegration:
    """Интеграционные тесты lazy loading."""

    @pytest.mark.asyncio
    async def test_two_step_search_pattern(self):
        """Проверка паттерна: сначала поиск, потом примеры."""
        service = SearchService()
        
        with patch('src.search.search_service.es_client') as mock_es, \
             patch('src.search.search_service.cache') as mock_cache:
            
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_es.is_connected = AsyncMock(return_value=True)
            
            # Первый запрос: базовая информация
            mock_es.search = AsyncMock(return_value={
                "hits": {
                    "hits": [{
                        "_source": {
                            "name": "СтрДлина",
                            "type": "global_function",
                            "examples": ["Пример"]  # Не вернётся без include_examples
                        }
                    }],
                    "total": {"value": 1}
                }
            })
            
            basic_result = await service.find_help_by_query("СтрДлина")
            
            # Второй запрос: примеры
            mock_es.search = AsyncMock(return_value={
                "hits": {
                    "hits": [{
                        "_source": {
                            "name": "СтрДлина",
                            "examples": ["Пример 1", "Пример 2"]
                        }
                    }],
                    "total": {"value": 1}
                }
            })
            
            examples_result = await service.get_examples_for_element("СтрДлина")
            
            # Проверяем паттерн
            assert basic_result['examples_included'] is False
            assert len(examples_result['examples']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
