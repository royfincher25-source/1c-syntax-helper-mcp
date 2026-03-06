"""Построитель запросов для Elasticsearch с оптимизацией производительности."""

from typing import Dict, Any, List, Optional


class QueryBuilder:
    """
    Оптимизированный построитель Elasticsearch запросов для поиска по документации 1С.
    
    Использует:
    - Filter context для фильтров (кэшируется, не влияет на scoring)
    - Query context только для полнотекстового поиска
    - Routing для уменьшения количества проверяемых шардов
    - Оптимизированные boost коэффициенты
    """

    def build_search_query(
        self,
        query: str,
        limit: int = 10,
        search_type: str = "auto",
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Строит оптимизированный поисковый запрос.

        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            search_type: Тип поиска (auto, exact, fuzzy, semantic)
            filters: Опциональные фильтры (type, object, version_from)

        Returns:
            Elasticsearch запрос
        """
        # Определяем тип поиска автоматически
        if search_type == "auto":
            search_type = self._detect_search_type(query)

        if search_type == "exact":
            return self._build_exact_search(query, limit, filters)
        elif search_type == "fuzzy":
            return self._build_fuzzy_search(query, limit, filters)
        elif search_type == "semantic":
            return self._build_semantic_search(query, limit, filters)
        else:
            return self._build_multi_match_search(query, limit, filters)

    def build_exact_query(self, function_name: str) -> Dict[str, Any]:
        """
        Строит точный запрос по имени функции с использованием filter context.

        Оптимизация:
        - term запросы в filter context для точных совпадений по name
        - wildcard для full_path (чтобы находить Объект.Имя, Имя.Метод, и просто Имя)
        - match_phrase только для ранжирования
        """
        return {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"name.keyword": function_name}}
                    ],
                    "should": [
                        {"term": {"full_path": {"value": function_name, "boost": 3.0}}},
                        {"wildcard": {"full_path": {"value": f"*{function_name}*", "boost": 2.0}}},
                        {"match_phrase": {"name": {"query": function_name, "boost": 2.0}}},
                        {"match_phrase": {"syntax_ru": {"query": function_name, "boost": 1.5}}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": 5,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }

    def build_object_query(self, object_name: str, limit: int = 50) -> Dict[str, Any]:
        """
        Строит запрос для поиска всех элементов объекта с routing.
        
        Оптимизация:
        - object в filter context (кэшируется)
        - routing по object для уменьшения шардов
        """
        return {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"object": object_name}}
                    ],
                    "should": [
                        {"prefix": {"full_path": {"value": f"{object_name}.", "boost": 2.0}}},
                        {"match": {"full_path": {"query": object_name, "boost": 1.5}}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": limit,
            "sort": [
                {"type": {"order": "asc"}},
                {"name.keyword": {"order": "asc"}}
            ],
            "routing": object_name  # Routing для уменьшения шардов
        }
    
    def _detect_search_type(self, query: str) -> str:
        """Автоматически определяет тип поиска по запросу."""
        # Точный поиск - если запрос содержит точку (метод объекта)
        if "." in query and len(query.split(".")) == 2:
            return "exact"
        
        # Точный поиск - если запрос короткий и не содержит пробелов
        if len(query.split()) == 1 and len(query) < 30:
            return "exact"
        
        # Семантический поиск - если запрос длинный или содержит много слов
        if len(query.split()) > 3 or len(query) > 50:
            return "semantic"
        
        # По умолчанию - обычный поиск
        return "multi_match"
    
    def _build_exact_search(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Строит точный поиск с filter context.
        
        Оптимизация:
        - match_phrase в should для ранжирования
        - filters в filter context для кэширования
        """
        # Базовая структура запроса
        es_query: Dict[str, Any] = {
            "query": {
                "bool": {
                    "should": [
                        {"match_phrase": {"name": {"query": query, "boost": 5.0}}},
                        {"match_phrase": {"full_path": {"query": query, "boost": 4.0}}},
                        {"match_phrase": {"syntax_ru": {"query": query, "boost": 3.0}}},
                        {"match_phrase": {"syntax_en": {"query": query, "boost": 3.0}}},
                        {"match": {"description": {"query": query, "boost": 2.0}}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }

        # Добавляем фильтры в filter context (кэшируются)
        if filters:
            es_query["query"]["bool"]["filter"] = self._build_filters(filters)

        return es_query

    def _build_multi_match_search(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Строит оптимизированный multi-match поиск.
        
        Оптимизация:
        - multi_match в must для scoring
        - filters в filter context для кэширования
        - Упрощенные поля для скорости
        """
        es_query: Dict[str, Any] = {
            "query": {
                "bool": {
                    "must": {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "name^5",
                                "full_path^4",
                                "syntax_ru^3",
                                "syntax_en^3",
                                "description^2"
                            ],
                            "type": "best_fields",
                            "fuzziness": "AUTO"
                        }
                    },
                    "should": [
                        {"match_phrase": {"name": {"query": query, "boost": 2.0}}},
                        {"prefix": {"name": {"value": query, "boost": 1.5}}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }

        # Добавляем фильтры в filter context (кэшируются)
        if filters:
            es_query["query"]["bool"]["filter"] = self._build_filters(filters)

        return es_query

    def _build_fuzzy_search(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Строит нечеткий поиск с оптимизацией.
        
        Оптимизация:
        - wildcard только для name.keyword (быстрее)
        - filters в filter context
        """
        es_query: Dict[str, Any] = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "name^3",
                                    "full_path^2",
                                    "description^1"
                                ],
                                "fuzziness": 2,
                                "type": "best_fields"
                            }
                        },
                        {
                            "wildcard": {
                                "name.keyword": {
                                    "value": f"*{query}*",
                                    "boost": 1.5
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }

        # Добавляем фильтры в filter context (кэшируются)
        if filters:
            es_query["query"]["bool"]["filter"] = self._build_filters(filters)

        return es_query

    def _build_semantic_search(
        self,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Строит семантический поиск с оптимизацией.
        
        Оптимизация:
        - most_fields для описания (лучше для семантики)
        - filters в filter context
        """
        es_query: Dict[str, Any] = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "description^3",
                                    "name^2",
                                    "full_path^2",
                                    "syntax_ru^1.5"
                                ],
                                "type": "most_fields",
                                "minimum_should_match": "50%"
                            }
                        },
                        {
                            "match_phrase": {
                                "description": {
                                    "query": query,
                                    "boost": 2.0,
                                    "slop": 3
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }

        # Добавляем фильтры в filter context (кэшируются)
        if filters:
            es_query["query"]["bool"]["filter"] = self._build_filters(filters)

        return es_query

    def _build_filters(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Строит filter context из переданных фильтров.
        
        Args:
            filters: Словарь фильтров {field: value}
        
        Returns:
            Список filter запросов
        """
        filter_list = []

        # Фильтр по типу документа
        if "type" in filters:
            filter_list.append({"term": {"type": filters["type"]}})

        # Фильтр по объекту
        if "object" in filters:
            filter_list.append({"term": {"object": filters["object"]}})

        # Фильтр по версии
        if "version_from" in filters:
            filter_list.append({"term": {"version_from": filters["version_from"]}})

        # Фильтр по return_type
        if "return_type" in filters:
            filter_list.append({"term": {"return_type": filters["return_type"]}})

        return filter_list
