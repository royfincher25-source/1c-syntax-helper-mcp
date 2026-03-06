"""Тесты оптимизации Elasticsearch запросов."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.search.query_builder import QueryBuilder
from src.core.elasticsearch import ElasticsearchClient


class TestQueryBuilderFilters:
    """Тесты использования filter context."""

    def test_build_search_query_with_filters(self):
        """Проверка построения запроса с фильтрами."""
        builder = QueryBuilder()
        
        query = builder.build_search_query(
            query="СтрДлина",
            limit=5,
            filters={"type": "global_function"}
        )
        
        # Проверяем наличие filter context
        assert "query" in query
        assert "bool" in query["query"]
        assert "filter" in query["query"]["bool"]
        
        # Проверяем фильтр по типу
        filters = query["query"]["bool"]["filter"]
        assert any(
            f.get("term", {}).get("type") == "global_function"
            for f in filters
        )
        
        # Проверяем наличие should для scoring
        assert "should" in query["query"]["bool"]

    def test_build_search_query_with_multiple_filters(self):
        """Проверка построения запроса с несколькими фильтрами."""
        builder = QueryBuilder()
        
        query = builder.build_search_query(
            query="Добавить",
            limit=10,
            filters={
                "type": "object_function",
                "object": "ТаблицаЗначений"
            }
        )
        
        # Проверяем наличие всех фильтров
        filters = query["query"]["bool"]["filter"]
        filter_types = []
        for f in filters:
            if "term" in f:
                filter_types.extend(f["term"].keys())
        
        assert "type" in filter_types
        assert "object" in filter_types

    def test_build_search_query_without_filters(self):
        """Проверка построения запроса без фильтров."""
        builder = QueryBuilder()
        
        query = builder.build_search_query(
            query="СтрДлина",
            limit=5
        )
        
        # Filter context не должен быть пустым
        if "filter" in query["query"]["bool"]:
            assert len(query["query"]["bool"]["filter"]) > 0

    def test_build_exact_query_uses_filter(self):
        """Проверка что exact query использует filter context."""
        builder = QueryBuilder()
        
        query = builder.build_exact_query("СтрДлина")
        
        # Проверяем filter context для точных совпадений
        assert "filter" in query["query"]["bool"]
        filters = query["query"]["bool"]["filter"]
        
        # Должны быть term запросы для name.keyword и full_path
        filter_fields = []
        for f in filters:
            if "term" in f:
                filter_fields.extend(f["term"].keys())
        
        assert "name.keyword" in filter_fields
        assert "full_path" in filter_fields

    def test_build_object_query_uses_routing(self):
        """Проверка что object query использует routing."""
        builder = QueryBuilder()
        
        query = builder.build_object_query("ТаблицаЗначений", limit=50)
        
        # Проверяем routing
        assert "routing" in query
        assert query["routing"] == "ТаблицаЗначений"
        
        # Проверяем filter context для object
        assert "filter" in query["query"]["bool"]
        filters = query["query"]["bool"]["filter"]
        
        assert any(
            f.get("term", {}).get("object") == "ТаблицаЗначений"
            for f in filters
        )


class TestQueryBuilderOptimization:
    """Тесты оптимизации запросов."""

    def test_filter_context_not_affect_scoring(self):
        """Проверка что фильтры в filter context не влияют на scoring."""
        builder = QueryBuilder()
        
        query = builder.build_search_query(
            query="Тест",
            filters={"type": "global_function"}
        )
        
        # Фильтры должны быть отдельно от should/must
        bool_query = query["query"]["bool"]
        assert "filter" in bool_query
        
        # Filter не должен быть вложен в should
        for should_clause in bool_query.get("should", []):
            assert "filter" not in should_clause

    def test_minimum_should_match_set(self):
        """Проверка что minimum_should_match установлен."""
        builder = QueryBuilder()
        
        query = builder.build_search_query(
            query="Тест",
            search_type="exact"
        )
        
        assert "minimum_should_match" in query["query"]["bool"]
        assert query["query"]["bool"]["minimum_should_match"] == 1

    def test_build_filters_method(self):
        """Проверка метода построения фильтров."""
        builder = QueryBuilder()
        
        filters = builder._build_filters({
            "type": "global_function",
            "object": "ТаблицаЗначений",
            "version_from": "8.3.24",
            "return_type": "Число"
        })
        
        # Проверяем что все фильтры созданы
        assert len(filters) == 4
        
        # Проверяем типы фильтров
        filter_dict = {}
        for f in filters:
            if "term" in f:
                field = list(f["term"].keys())[0]
                filter_dict[field] = f["term"][field]
        
        assert filter_dict["type"] == "global_function"
        assert filter_dict["object"] == "ТаблицаЗначений"
        assert filter_dict["version_from"] == "8.3.24"
        assert filter_dict["return_type"] == "Число"


class TestElasticsearchMapping:
    """Тесты оптимизации mapping."""

    @pytest.mark.asyncio
    async def test_create_index_with_optimized_mapping(self):
        """Проверка создания индекса с оптимизированным mapping."""
        # Мокаем клиент
        mock_client = AsyncMock()
        mock_client.indices.create = AsyncMock(return_value=True)
        
        es_client = ElasticsearchClient()
        es_client._client = mock_client
        es_client._config = MagicMock()
        es_client._config.index_name = "test_index"
        
        # Создаем индекс
        result = await es_client.create_index()
        
        # Проверяем что create был вызван
        assert result is True
        assert mock_client.indices.create.called
        
        # Проверяем аргументы
        call_args = mock_client.indices.create.call_args
        index_config = call_args[1]["body"]
        
        # Проверяем оптимизации
        assert index_config["mappings"]["_all"]["enabled"] is False
        assert index_config["settings"]["refresh_interval"] == "30s"
        
        # Проверяем doc_values для keyword полей
        type_mapping = index_config["mappings"]["properties"]["type"]
        assert type_mapping["doc_values"] is True
        
        object_mapping = index_config["mappings"]["properties"]["object"]
        assert object_mapping["doc_values"] is True
        
        # Проверяем index: false для syntax полей
        syntax_ru_mapping = index_config["mappings"]["properties"]["syntax_ru"]
        assert syntax_ru_mapping["index"] is False

    @pytest.mark.asyncio
    async def test_optimize_index_settings(self):
        """Проверка оптимизации настроек индекса."""
        mock_client = AsyncMock()
        mock_client.indices.put_settings = AsyncMock()
        mock_client.indices.forcemerge = AsyncMock()
        
        es_client = ElasticsearchClient()
        es_client._client = mock_client
        es_client._config = MagicMock()
        es_client._config.index_name = "test_index"
        
        # Оптимизируем
        result = await es_client.optimize_index_settings()
        
        assert result is True
        
        # Проверяем что settings обновлены
        assert mock_client.indices.put_settings.called
        put_args = mock_client.indices.put_settings.call_args
        assert put_args[1]["body"]["refresh_interval"] == "1s"
        
        # Проверяем forcemerge
        assert mock_client.indices.forcemerge.called
        merge_args = mock_client.indices.forcemerge.call_args
        assert merge_args[1]["max_num_segments"] == 1


class TestSearchServiceFilters:
    """Тесты использования фильтров в search service."""

    @pytest.mark.asyncio
    async def test_find_help_by_query_with_filters(self):
        """Проверка поиска с фильтрами."""
        from src.search.search_service import SearchService
        
        # Мокаем зависимости
        with patch.object(SearchService, '__init__', lambda x: None):
            service = SearchService()
            service.query_builder = QueryBuilder()
            service.ranker = MagicMock()
            service.formatter = MagicMock()
            
            # Мокаем кэш и ES
            with patch('src.search.search_service.cache') as mock_cache, \
                 patch('src.search.search_service.es_client') as mock_es:
                
                mock_cache.get = AsyncMock(return_value=None)
                mock_cache.set = AsyncMock()
                mock_es.is_connected = AsyncMock(return_value=True)
                mock_es.search = AsyncMock(return_value={
                    "hits": {
                        "hits": [],
                        "total": {"value": 0}
                    }
                })
                
                # Выполняем поиск с фильтрами
                result = await service.find_help_by_query(
                    query="СтрДлина",
                    limit=5,
                    filters={"type": "global_function"}
                )
                
                # Проверяем что filters_applied установлен
                assert result.get("filters_applied") is True
                
                # Проверяем что ES запрос был выполнен
                assert mock_es.search.called


class TestPerformanceMetrics:
    """Тесты производительности (бенчмарки)."""

    def test_query_building_performance(self):
        """Тест скорости построения запросов."""
        import time
        
        builder = QueryBuilder()
        iterations = 1000
        
        start = time.time()
        for _ in range(iterations):
            builder.build_search_query(
                query="СтрДлина",
                limit=5,
                filters={"type": "global_function"}
            )
        end = time.time()
        
        avg_time_ms = (end - start) / iterations * 1000
        
        # Построение запроса должно быть < 1ms
        assert avg_time_ms < 1.0, f"Среднее время построения запроса: {avg_time_ms}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
