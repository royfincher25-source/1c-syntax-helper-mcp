from typing import Dict, Any


class SyntaxFormatter:
    """Форматтер для синтаксической информации."""
    
    @staticmethod
    def format_syntax_info(result: Dict[str, Any]) -> str:
        """Форматирует техническую справку."""
        text = f"🔧 **ТЕХНИЧЕСКАЯ СПРАВКА:** {result.get('name', '')}"
        
        if result.get('object'):
            text += f" ({result['object']})"
        
        text += "\n\n"
        
        if result.get('description'):
            text += f"📝 **Описание:**\n   {result['description']}\n\n"
        
        if result.get('syntax_ru'):
            text += f"🔤 **Синтаксис:**\n   `{result['syntax_ru']}`\n\n"
        
        parameters = result.get('parameters')
        if parameters and isinstance(parameters, list):
            text += "⚙️ **Параметры:**\n"
            for param in parameters:
                if isinstance(param, dict):
                    required = " (обязательный)" if param.get('required') else " (необязательный)"
                    text += f"   • {param.get('name', '')} ({param.get('type', '')}){required}"
                    if param.get('description'):
                        text += f" - {param['description']}"
                    text += "\n"
            text += "\n"
        
        if result.get('return_type'):
            text += f"↩️ **Возвращает:** {result['return_type']}\n\n"
        
        return text
    
    @staticmethod
    def format_quick_reference(result: Dict[str, Any]) -> str:
        """Форматирует краткую справку."""
        name = result.get('name', '')
        syntax = result.get('syntax_ru', '')
        description = result.get('description', '')
        
        text = "⚡ **КРАТКАЯ СПРАВКА**\n\n"
        
        if syntax:
            text += f"`{syntax}`\n"
        else:
            text += f"`{name}`\n"
        
        if description:
            desc = description.split('.')[0] + '.' if '.' in description else description
            desc = desc[:100] + "..." if len(desc) > 100 else desc
            text += f"└ {desc}"
        
        return text
