from typing import Dict, List, Any


class SearchFormatter:
    """Форматтер для результатов поиска."""
    
    @staticmethod
    def format_search_header(count: int, query: str) -> Dict[str, str]:
        """Форматирует заголовок результатов поиска."""
        return {
            "type": "text",
            "text": f"📋 **Найдено:** {count} элементов по запросу \"{query}\"\n"
        }
    
    @staticmethod
    def format_search_result(result: Dict[str, Any], index: int) -> Dict[str, str]:
        """Форматирует отдельный результат поиска."""
        name = result.get("name", "")
        obj = result.get("object", "")
        description = result.get("description", "")
        
        text = f"{index}. **{name}**"
        if obj:
            text += f" ({obj} → Метод)" if obj != "Global context" else " (Глобальная функция)"
        
        if description:
            desc = description[:100] + "..." if len(description) > 100 else description
            text += f"\n   └ {desc}"
        
        return {"type": "text", "text": text + "\n"}
    
    @staticmethod
    def format_context_search(
        search_results: List[Dict[str, Any]], 
        query: str, 
        context: str
    ) -> str:
        """Форматирует результаты контекстного поиска."""
        if context == "object":
            objects = {}
            for result in search_results:
                obj = result.get("object", "Неизвестно")
                if obj not in objects:
                    objects[obj] = []
                objects[obj].append(result)
            
            text = f"🎯 **ПОИСК В КОНТЕКСТЕ:** {context}\n\n"
            text += f"Найдено {len(search_results)} элементов по запросу \"{query}\"\n\n"
            
            for obj, items in list(objects.items())[:5]:
                text += f"📦 **{obj}:**\n"
                for item in items[:3]:
                    name = item.get("name", "")
                    syntax = item.get("syntax_ru", "")
                    desc = item.get("description", "")
                    
                    text += f"   • {name}"
                    if syntax:
                        text += f" - `{syntax}`"
                    if desc:
                        short_desc = desc[:50] + "..." if len(desc) > 50 else desc
                        text += f"\n     {short_desc}"
                    text += "\n"
                text += "\n"
        else:
            text = f"🔍 **ПОИСК В КОНТЕКСТЕ:** {context}\n\n"
            text += f"Найдено {len(search_results)} элементов\n\n"
            
            for i, result in enumerate(search_results[:8], 1):
                name = result.get("name", "")
                syntax = result.get("syntax_ru", "")
                text += f"{i}. **{name}**"
                if syntax:
                    text += f" - `{syntax}`"
                text += "\n"
        
        return text
