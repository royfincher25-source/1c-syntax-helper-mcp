"""Форматтер ответов MCP."""

from typing import Dict, List, Any
from src.search.formatter import SearchFormatter


class MCPResponseFormatter:
    """Класс для стандартизированного форматирования ответов MCP."""

    def __init__(self):
        self.search = SearchFormatter()

    @staticmethod
    def create_error_response(message: str, details: str = None) -> Dict[str, Any]:
        """Создаёт стандартизированный ответ с ошибкой."""
        error_text = message
        if details:
            error_text += f": {details}"
        return {"content": [], "error": error_text}

    @staticmethod
    def create_not_found_response(query: str, context: str = "") -> Dict[str, Any]:
        """Создаёт стандартизированный ответ для случая 'не найдено'."""
        if context:
            text = f"По запросу '{query}' в контексте '{context}' ничего не найдено."
        else:
            text = f"По запросу '{query}' ничего не найдено."

        return {"content": [{"type": "text", "text": text}]}

    @staticmethod
    def create_success_response(content: List[Dict[str, str]]) -> Dict[str, Any]:
        """Создаёт стандартизированный успешный ответ."""
        return {"content": content}
    
    def format_search_header(self, count: int, query: str) -> Dict[str, str]:
        """Форматирует заголовок результатов поиска."""
        return self.search.format_search_header(count, query)
    
    def format_search_result(self, result: Dict[str, Any], index: int) -> Dict[str, str]:
        """Форматирует отдельный результат поиска."""
        return self.search.format_search_result(result, index)
    
    def format_syntax_info(self, result: Dict[str, Any]) -> str:
        """Форматирует техническую справку."""
        return self.search.format_syntax_info(result)
    
    def format_quick_reference(self, result: Dict[str, Any]) -> str:
        """Форматирует краткую справку."""
        return self.search.format_quick_reference(result)
    
    def format_context_search(
        self, 
        search_results: List[Dict[str, Any]], 
        query: str, 
        context: str
    ) -> str:
        """Форматирует результаты контекстного поиска."""
        return self.search.format_context_search(search_results, query, context)
    
    def format_object_members_list(
        self, 
        object_name: str, 
        member_type: str, 
        methods: list, 
        properties: list, 
        events: list, 
        total: int
    ) -> str:
        """Форматирует список элементов объекта."""
        return self.search.format_object_members_list(
            object_name, member_type, methods, properties, events, total
        )


mcp_formatter = MCPResponseFormatter()
