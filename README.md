# 1C Syntax Helper MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.0+-blue.svg)](https://www.docker.com/)

[**Этот MCP использован в статье**](https://infostart.ru/1c/articles/2605838)

MCP-сервер для быстрого поиска по синтаксису 1С, предоставляющий ИИ-агентам в VS Code доступ к документации платформы 1С:Предприятие через централизованный сервис.

## 📚 Документация

- **[📖 SETUP_GUIDE.md](SETUP_GUIDE.md)** - Подробная инструкция по развертыванию
- **[📋 ТЕХНИЧЕСКОЕ_ЗАДАНИЕ.md](ТЕХНИЧЕСКОЕ_ЗАДАНИЕ.md)** - Техническое задание проекта
- **[📝 CHANGELOG.md](CHANGELOG.md)** - История изменений

## 🚀 Быстрый старт

### Системные требования
- Windows 10/11 64-bit
- Docker Desktop
- 4+ ГБ RAM
- VS Code с MCP расширением

### Развертывание сервиса

```bash
# 1. Клонировать проект
git clone https://github.com/royfincher25-source/1c-syntax-helper-mcp.git
cd 1c-syntax-helper-mcp

# 2. Поместить .hbk файл документации
copy "path\to\1c_documentation.hbk" "data\hbk\1c_documentation.hbk"

# 3. Запустить сервисы
docker compose up -d

# 4. Проверить доступность
curl http://localhost:8002/health
```

### Настройка VS Code

Добавьте в настройки VS Code (`settings.json`):

```json
{
  "mcp.servers": {
    "1c-syntax-helper": {
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-d", "@-",
        "http://localhost:8002/mcp"
      ]
    }
  }
}
```

> **💡 Подробные инструкции** смотрите в [SETUP_GUIDE.md](SETUP_GUIDE.md)

## 🏗️ Архитектура

```
                    🖥️ Сервер (localhost:8002)
┌─────────────────────────────────────────────────────────┐
│  ┌─────────────────┐    ┌──────────────────────────────┐ │
│  │  Elasticsearch  │    │    FastAPI MCP Server        │ │
│  │    (общий)      │◄───┤      (shared service)       │ │
│  │ 1c_docs_index   │    │   - Single .hbk file        │ │
│  └─────────────────┘    │   - No authentication       │ │
│                         │   - Shared documentation    │ │
│                         └──────────────┬───────────────┘ │
└────────────────────────────────────────┼─────────────────┘
                                         │ Port 8002
        ┌────────────────────────────────┼────────────────┐
        │                                │                │
   ┌────▼────┐                     ┌────▼────┐     ┌────▼────┐
   │VS Code  │                     │VS Code  │ ... │VS Code  │
   │ User 1  │                     │ User 2  │     │ User 8  │
   └─────────┘                     └─────────┘     └─────────┘
```

## 📁 Структура проекта

```
1c-syntax-helper-mcp/
├── docker-compose.yml          # Оркестрация контейнеров
├── Dockerfile                  # Образ MCP сервера
├── requirements.txt           # Python зависимости
├── .env.example              # Пример конфигурации
├── src/                      # Исходный код
│   ├── main.py              # FastAPI приложение
│   ├── core/                # Ядро системы
│   ├── parsers/             # Парсеры .hbk документации
│   ├── search/              # Модули поиска
│   └── models/              # Pydantic модели
├── data/                    # Данные
│   ├── hbk/                # .hbk файл документации
│   └── logs/               # Логи приложения
├── tests/                   # Тесты
└── docs/                   # Документация
```

## 🔧 Основные возможности

- **Поиск глобальных функций**: `СтрДлина`, `ЧислоПрописью`
- **Поиск методов объектов**: `ТаблицаЗначений.Добавить`
- **Поиск свойств**: `ТаблицаЗначений.Колонки`
- **Информация об объектах**: получение всех методов/свойств/событий

## 📚 Документация

- [Техническое задание](ТЕХНИЧЕСКОЕ_ЗАДАНИЕ.md)
- [Инструкции по настройке](SETUP_GUIDE.md)
- [Настройка VS Code](docs/VS_CODE_CONFIG.md)
- [API Reference](docs/API_REFERENCE.md)
- [История изменений](CHANGELOG.md)

## 🛠️ Разработка

### Требования

- Docker Engine 20.0+
- Docker Compose 2.0+
- Python 3.11+ (для разработки)

### Локальная разработка

```bash
# Создать виртуальное окружение
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
# source venv/bin/activate   # Linux/Mac

# Установить зависимости
pip install -r requirements.txt

# Запустить в режиме разработки
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8002
```

### Тестирование

```bash
# Запустить тесты
python -m pytest tests/ -v

# Проверить покрытие
python -m pytest tests/ --cov=src --cov-report=html
```

## 🔄 Обновление документации

Документация обновляется вручную раз в год:

```bash
# 1. Остановить сервисы
docker-compose down

# 2. Заменить .hbk файл
copy "new_1c_documentation.hbk" "data\hbk\1c_documentation.hbk"

# 3. Запустить и переиндексировать
docker-compose up -d
curl -X POST http://localhost:8002/index/rebuild
```

## 📋 MCP Protocol

Сервер реализует [Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/index) со следующими tools:

| Инструмент | Описание |
|------------|----------|
| `find_1c_help` | Универсальный поиск по синтаксису 1С |
| `get_syntax_info` | Полная техническая информация об элементе |
| `get_quick_reference` | Краткая справка по элементу |
| `search_by_context` | Поиск с фильтром по контексту (глобальный/объектный) |
| `list_object_members` | Список методов и свойств объекта |

### Примеры использования

**find_1c_help** - поиск по запросу:
```json
{
  "name": "find_1c_help",
  "arguments": {"query": "Массив", "limit": 5}
}
```

**get_syntax_info** - детальная информация:
```json
{
  "name": "get_syntax_info",
  "arguments": {"element_name": "Массив"}
}
```

**list_object_members** - методы объекта:
```json
{
  "name": "list_object_members",
  "arguments": {"object_name": "Массив", "member_type": "all"}
}
```

## ⚡ Performance

- Время отклика поиска: < 500ms
- Поддержка 8 одновременных пользователей
- Размер индекса: ~32MB (80% от 40MB .hbk файла)
- Потребление памяти: ~512MB (256MB ES + 256MB MCP сервер)

## 🐛 Поддержка

При возникновении проблем:

1. Проверить логи: `docker-compose logs mcp-server`
2. Проверить статус Elasticsearch: `curl http://localhost:9200/_cluster/health`
3. Проверить статус индексации: `curl http://localhost:8002/index/status`

## 📄 Лицензия

MIT License
