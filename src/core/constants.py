"""
Константы проекта.
"""

# Elasticsearch настройки
ELASTICSEARCH_DEFAULT_HOST = "localhost"
ELASTICSEARCH_DEFAULT_PORT = 9200
ELASTICSEARCH_INDEX_NAME = "help1c_docs"
ELASTICSEARCH_CONNECTION_TIMEOUT = 30
ELASTICSEARCH_REQUEST_TIMEOUT = 60

# Парсинг
BATCH_SIZE = 100
MAX_FILE_SIZE_MB = 500  # Поддержка архивов до 500MB
SUPPORTED_ENCODINGS = ["utf-8", "cp1251", "iso-8859-1"]

# Таймауты парсера (автоматически масштабируются в зависимости от размера файла)
HBK_LIST_TIMEOUT = 300  # Таймаут для получения списка файлов из архива (5 минут для больших архивов)
HBK_EXTRACT_TIMEOUT_BASE = 600  # Базовый таймаут для извлечения (10 минут для 40MB)
HBK_EXTRACT_TIMEOUT_PER_MB = 15  # Дополнительные секунды на каждый MB сверх 40MB
HBK_EXTRACT_TIMEOUT_MAX = 3600  # Максимальный таймаут (1 час)
HBK_FILE_READ_TIMEOUT = 30  # Таймаут для чтения отдельного файла

# Масштабирование ресурсов
MEMORY_CACHE_LIMIT_MB = 256  # Лимит памяти для кэширования файлов
MEMORY_CACHE_LIMIT_FILES = 10000  # Максимальное количество файлов в кэше

# Параллельный парсинг
PARALLEL_PARSE_LIMIT = 10  # Максимум параллельных задач парсинга
PARSE_BATCH_SIZE = 50  # Размер батча для параллельной обработки

# Кэширование парсинга
DOC_CACHE_SIZE = 5000  # Максимум документов в кэше результатов

# Логирование
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Rate limiting
REQUESTS_PER_MINUTE = 60
REQUESTS_PER_HOUR = 1000

# Поиск
MAX_SEARCH_RESULTS = 100
SEARCH_TIMEOUT_SECONDS = 30
MIN_SCORE_THRESHOLD = 0.1

# Файловые операции
TEMP_DIR_PREFIX = "help1c_temp_"
EXTRACTION_TIMEOUT_SECONDS = 300

# HTTP
DEFAULT_REQUEST_TIMEOUT = 30
MAX_REQUEST_SIZE_MB = 10

# SSE (Server-Sent Events) конфигурация
SSE_QUEUE_MAX_SIZE = 100  # Максимум 100 сообщений в очереди
SSE_PING_INTERVAL_SECONDS = 30  # Интервал ping для поддержания соединения
SSE_SESSION_TIMEOUT_SECONDS = 3600  # Максимальное время жизни сессии (1 час)
