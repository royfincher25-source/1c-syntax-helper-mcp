"""Конфигурация приложения."""

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings
from typing import Optional, List
import os


class ElasticsearchConfig(BaseModel):
    """Конфигурация Elasticsearch."""
    url: str = "http://localhost:9200"
    index_name: str = "help1c_docs"
    timeout: int = 30
    max_retries: int = 3
    # Connection pool настройки
    pool_maxsize: int = 10
    pool_max_retries: int = 3
    # Таймауты
    connect_timeout: int = 10
    read_timeout: int = 30


class ServerConfig(BaseModel):
    """Конфигурация сервера."""
    host: str = "0.0.0.0"
    port: int = 8002
    workers: int = 1
    log_level: str = "INFO"


class DataConfig(BaseModel):
    """Конфигурация данных."""
    hbk_directory: str = "/app/data/hbk"
    logs_directory: str = "/app/logs"


class CORSConfig(BaseModel):
    """Конфигурация CORS."""
    allow_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8002",
    ]
    allow_credentials: bool = True
    allow_methods: List[str] = ["*"]
    allow_headers: List[str] = ["*"]
    
    
class Settings(BaseSettings):
    """Основные настройки приложения."""
    
    # Elasticsearch настройки
    elasticsearch_host: str = "elasticsearch"
    elasticsearch_port: str = "9200"
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "help1c_docs"
    elasticsearch_timeout: int = 30
    elasticsearch_max_retries: int = 3
    elasticsearch_pool_maxsize: int = 10
    elasticsearch_pool_max_retries: int = 3
    elasticsearch_connect_timeout: int = 10
    elasticsearch_read_timeout: int = 30
    
    # Сервер настройки
    server_host: str = "0.0.0.0"
    server_port: int = 8002
    log_level: str = "INFO"
    
    # Пути к данным
    hbk_directory: str = "data/hbk"
    logs_directory: str = "data/logs"
    
    # Производительность
    max_concurrent_requests: int = 8
    index_batch_size: int = 100
    reindex_on_startup: bool = True
    search_max_results: int = 50
    search_timeout_seconds: int = 30
    
    # Режим разработки
    debug: bool = False
    
    # CORS - можно переопределить через переменную CORS_ORIGINS (через запятую)
    cors_origins: Optional[str] = None
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    @property
    def cors(self) -> CORSConfig:
        """Получить конфигурацию CORS."""
        origins = self.cors_origins
        if origins:
            origin_list = [o.strip() for o in origins.split(",") if o.strip()]
            if origin_list:
                return CORSConfig(allow_origins=origin_list)
        return CORSConfig()
    
    @property
    def elasticsearch(self) -> ElasticsearchConfig:
        """Получить конфигурацию Elasticsearch."""
        es_url = (self.elasticsearch_url or "").strip()
        if not es_url:
            es_url = f"{self.elasticsearch_host}:{self.elasticsearch_port}".strip()

        if not es_url.startswith("http://") and not es_url.startswith("https://"):
            es_url = f"http://{es_url}"

        return ElasticsearchConfig(
            url=es_url,
            index_name=self.elasticsearch_index,
            timeout=self.elasticsearch_timeout,
            max_retries=self.elasticsearch_max_retries,
            pool_maxsize=self.elasticsearch_pool_maxsize,
            pool_max_retries=self.elasticsearch_pool_max_retries,
            connect_timeout=self.elasticsearch_connect_timeout,
            read_timeout=self.elasticsearch_read_timeout
        )
    
    @property
    def server(self) -> ServerConfig:
        """Получить конфигурацию сервера."""
        return ServerConfig(
            host=self.server_host,
            port=self.server_port,
            log_level=self.log_level
        )
    
    @property
    def data(self) -> DataConfig:
        """Получить конфигурацию данных."""
        return DataConfig(
            hbk_directory=self.hbk_directory,
            logs_directory=self.logs_directory
        )


# Глобальный экземпляр настроек
settings = Settings()
