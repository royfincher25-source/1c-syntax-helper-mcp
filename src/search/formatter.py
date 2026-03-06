"""Форматирование результатов поиска для MCP протокола."""

from typing import List, Dict, Any, Optional


class SearchFormatter:
    """Форматировщик результатов поиска для MCP протокола."""

    def format_search_results(
        self,
        ranked_results: List[Dict[str, Any]],
        include_examples: bool = False  # По умолчанию примеры не включаем
    ) -> List[Dict[str, Any]]:
        """
        Форматирует результаты поиска для MCP.

        Args:
            ranked_results: Отранжированные результаты поиска
            include_examples: Включать примеры кода (по умолчанию False для экономии трафика)

        Returns:
            Список отформатированных результатов
        """
        formatted_results = []

        for result in ranked_results:
            doc = result["document"]
            formatted_doc = self._format_document(doc, include_examples=include_examples)

            # Добавляем метаинформацию о ранжировании
            formatted_doc["_score"] = round(result["score"], 3)
            formatted_doc["_relevance"] = self._calculate_relevance_level(result["score"])

            formatted_results.append(formatted_doc)

        return formatted_results

    def format_function_details(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Форматирует подробную информацию о функции."""
        formatted = self._format_document(doc)
        
        # Добавляем дополнительные детали для функции
        formatted["details"] = {
            "full_syntax": {
                "russian": doc.get("syntax_ru", ""),
                "english": doc.get("syntax_en", "")
            },
            "parameters_detailed": self._format_parameters_detailed(doc.get("parameters", [])),
            "usage_examples": doc.get("examples", []),
            "return_value": {
                "type": doc.get("return_type", ""),
                "description": self._get_return_description(doc)
            },
            "version_info": {
                "available_from": doc.get("version_from", ""),
                "source_file": doc.get("source_file", "")
            }
        }
        
        return formatted

    def format_object_method(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Форматирует метод объекта."""
        return {
            "name": doc.get("name", ""),
            "syntax_ru": doc.get("syntax_ru", ""),
            "syntax_en": doc.get("syntax_en", ""),
            "description": doc.get("description", ""),
            "parameters": self._format_parameters_brief(doc.get("parameters", [])),
            "return_type": doc.get("return_type", ""),
            "type": "method"
        }

    def format_object_property(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Форматирует свойство объекта."""
        return {
            "name": doc.get("name", ""),
            "type": "property",
            "description": doc.get("description", ""),
            "access": self._determine_property_access(doc)
        }

    def format_object_event(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Форматирует событие объекта."""
        return {
            "name": doc.get("name", ""),
            "description": doc.get("description", ""),
            "parameters": self._format_parameters_brief(doc.get("parameters", [])),
            "type": "event"
        }

    def _format_document(
        self,
        doc: Dict[str, Any],
        include_examples: bool = False
    ) -> Dict[str, Any]:
        """
        Базовое форматирование документа.
        
        Args:
            doc: Документ из Elasticsearch
            include_examples: Включать примеры кода
        """
        formatted = {
            "type": doc.get("type", ""),
            "name": doc.get("name", ""),
            "object": doc.get("object", ""),
            "full_path": doc.get("full_path", ""),
            "description": doc.get("description", ""),
            "syntax": {
                "russian": doc.get("syntax_ru", ""),
                "english": doc.get("syntax_en", "")
            },
            "parameters": self._format_parameters_brief(doc.get("parameters", [])),
            "return_type": doc.get("return_type", ""),
            "version_from": doc.get("version_from", "")
        }
        
        # Добавляем примеры только если запрошены
        if include_examples:
            formatted["examples"] = doc.get("examples", [])
        
        return formatted

    def _format_parameters_brief(self, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Краткое форматирование параметров."""
        if not parameters:
            return []
        
        formatted_params = []
        for param in parameters:
            formatted_params.append({
                "name": param.get("name", ""),
                "type": param.get("type", ""),
                "required": param.get("required", False),
                "description": param.get("description", "")
            })
        
        return formatted_params

    def _format_parameters_detailed(self, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Подробное форматирование параметров."""
        if not parameters:
            return []
        
        formatted_params = []
        for param in parameters:
            formatted_param = {
                "name": param.get("name", ""),
                "type": param.get("type", ""),
                "required": param.get("required", False),
                "description": param.get("description", ""),
                "default_value": param.get("default_value", ""),
                "constraints": param.get("constraints", "")
            }
            
            # Добавляем дополнительную информацию если есть
            if param.get("enum_values"):
                formatted_param["possible_values"] = param["enum_values"]
            
            formatted_params.append(formatted_param)
        
        return formatted_params
    
    def _get_return_description(self, doc: Dict[str, Any]) -> str:
        """Получает описание возвращаемого значения."""
        # Ищем описание возвращаемого значения в описании функции
        description = doc.get("description", "")
        
        # Простой поиск ключевых слов
        return_keywords = [
            "возвращает", "возвращаемое значение", "результат",
            "returns", "return value", "result"
        ]
        
        for keyword in return_keywords:
            if keyword.lower() in description.lower():
                # Находим предложение с ключевым словом
                sentences = description.split(".")
                for sentence in sentences:
                    if keyword.lower() in sentence.lower():
                        return sentence.strip()
        
        return ""

    def _determine_property_access(self, doc: Dict[str, Any]) -> str:
        """Определяет тип доступа к свойству."""
        description = doc.get("description", "").lower()
        
        if "только чтение" in description or "read-only" in description:
            return "readonly"
        elif "только запись" in description or "write-only" in description:
            return "writeonly"
        else:
            return "readwrite"

    def _calculate_relevance_level(self, score: float) -> str:
        """Вычисляет уровень релевантности."""
        if score >= 10.0:
            return "very_high"
        elif score >= 5.0:
            return "high"
        elif score >= 2.0:
            return "medium"
        elif score >= 1.0:
            return "low"
        else:
            return "very_low"

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

    @staticmethod
    def format_syntax_info(result: Dict[str, Any]) -> str:
        """Форматирует техническую справку."""
        name = result.get("name", "")
        syntax_ru = result.get("syntax_ru", "")
        description = result.get("description", "")
        
        text = f"### {name}\n\n"
        if syntax_ru:
            text += f"**Синтаксис:** `{syntax_ru}`\n\n"
        if description:
            text += f"**Описание:** {description}\n"
        
        return text

    @staticmethod
    def format_quick_reference(result: Dict[str, Any]) -> str:
        """Форматирует краткую справку."""
        name = result.get("name", "")
        syntax_ru = result.get("syntax_ru", "")
        
        text = f"**{name}**"
        if syntax_ru:
            text += f": `{syntax_ru}`"
        
        return text

    @staticmethod
    def format_object_members_list(
        object_name: str, 
        member_type: str, 
        methods: List[Dict[str, Any]], 
        properties: List[Dict[str, Any]], 
        events: List[Dict[str, Any]], 
        total: int
    ) -> str:
        """Форматирует список элементов объекта."""
        text = f"📦 **{object_name}** (всего: {total})\n\n"
        
        if methods:
            text += "**Методы:**\n"
            for m in methods[:10]:
                text += f"  • {m.get('name', '')}\n"
            if len(methods) > 10:
                text += f"  ... и ещё {len(methods) - 10}\n"
            text += "\n"
        
        if properties:
            text += "**Свойства:**\n"
            for p in properties[:5]:
                text += f"  • {p.get('name', '')}\n"
            if len(properties) > 5:
                text += f"  ... и ещё {len(properties) - 5}\n"
            text += "\n"
        
        if events:
            text += "**События:**\n"
            for e in events[:5]:
                text += f"  • {e.get('name', '')}\n"
        
        return text
