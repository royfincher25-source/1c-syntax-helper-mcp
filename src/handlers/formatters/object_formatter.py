from typing import List, Dict, Any


class ObjectFormatter:
    """Форматтер для информации об объектах."""
    
    @staticmethod
    def format_object_members_list(
        object_name: str, 
        member_type: str, 
        methods: list, 
        properties: list, 
        events: list, 
        total: int
    ) -> str:
        """Форматирует список элементов объекта."""
        text = f"📦 **ОБЪЕКТ:** {object_name}\n\n"
        
        if member_type in ["all", "methods"] and methods:
            text += f"🔨 **Методы ({len(methods)}):**\n"
            for method in methods[:20]:
                name = method.get("name", "")
                syntax = method.get("syntax_ru", "")
                desc = method.get("description", "")
                
                text += f"   • **{name}**"
                if syntax:
                    text += f" - `{syntax}`"
                if desc:
                    short_desc = desc[:80] + "..." if len(desc) > 80 else desc
                    text += f"\n     {short_desc}"
                text += "\n"
            text += "\n"
        
        if member_type in ["all", "properties"] and properties:
            text += f"📋 **Свойства ({len(properties)}):**\n"
            for prop in properties[:15]:
                name = prop.get("name", "")
                desc = prop.get("description", "")
                
                text += f"   • **{name}**"
                if desc:
                    short_desc = desc[:60] + "..." if len(desc) > 60 else desc
                    text += f" - {short_desc}"
                text += "\n"
            text += "\n"
        
        if member_type in ["all", "events"] and events:
            text += f"⚡ **События ({len(events)}):**\n"
            for event in events[:10]:
                name = event.get("name", "")
                desc = event.get("description", "")
                
                text += f"   • **{name}**"
                if desc:
                    short_desc = desc[:60] + "..." if len(desc) > 60 else desc
                    text += f" - {short_desc}"
                text += "\n"
        
        return text
