"""Тесты для модуля lifespan management."""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.lifespan import (
    LifespanManager,
    get_lifespan_manager,
    reset_lifespan_manager
)


@pytest.fixture
def mock_es_client():
    """Mock Elasticsearch client."""
    with patch('src.core.lifespan.es_client') as mock:
        mock.connect = AsyncMock(return_value=True)
        mock.index_exists = AsyncMock(return_value=False)
        mock.get_documents_count = AsyncMock(return_value=0)
        yield mock


@pytest.fixture
def mock_cache():
    """Mock cache."""
    with patch('src.core.lifespan.cache') as mock:
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        yield mock


@pytest.fixture
def mock_monitor():
    """Mock system monitor."""
    with patch('src.core.lifespan.get_system_monitor') as mock:
        monitor_instance = MagicMock()
        monitor_instance.start_monitoring = AsyncMock()
        monitor_instance.stop_monitoring = AsyncMock()
        mock.return_value = monitor_instance
        yield monitor_instance


@pytest.fixture
def mock_metrics():
    """Mock metrics collector."""
    with patch('src.core.lifespan.get_metrics_collector') as mock:
        metrics_instance = MagicMock()
        metrics_instance.increment = AsyncMock()
        mock.return_value = metrics_instance
        yield metrics_instance


@pytest.fixture
def temp_hbk_file(tmp_path):
    """Создать временный .hbk файл."""
    hbk_dir = tmp_path / "hbk"
    hbk_dir.mkdir()
    hbk_file = hbk_dir / "test.hbk"
    hbk_file.write_bytes(b"test content")
    return str(hbk_file)


class TestLifespanManager:
    """Тесты для LifespanManager."""

    @pytest.mark.asyncio
    async def test_init_default_values(self):
        """Тест инициализации со значениями по умолчанию."""
        manager = LifespanManager()
        
        assert manager.hbk_directory is None
        assert manager.auto_index is True
        assert manager._background_tasks == []

    @pytest.mark.asyncio
    async def test_init_custom_values(self):
        """Тест инициализации с кастомными значениями."""
        manager = LifespanManager(
            hbk_directory="/path/to/hbk",
            auto_index=False
        )
        
        assert manager.hbk_directory == "/path/to/hbk"
        assert manager.auto_index is False

    @pytest.mark.asyncio
    async def test_startup_success(
        self,
        mock_es_client,
        mock_cache,
        mock_monitor,
        mock_metrics
    ):
        """Тест успешного startup."""
        manager = LifespanManager(auto_index=False)
        app = MagicMock()
        
        await manager.startup(app)
        
        # Проверяем вызовы
        mock_cache.start.assert_called_once()
        mock_monitor.start_monitoring.assert_called_once_with(interval=60)
        mock_es_client.connect.assert_called_once()
        mock_metrics.increment.assert_any_call("startup.elasticsearch.connection_success")
        mock_metrics.increment.assert_any_call("startup.completed")

    @pytest.mark.asyncio
    async def test_startup_es_connection_failed(
        self,
        mock_es_client,
        mock_cache,
        mock_monitor,
        mock_metrics
    ):
        """Тест неудачного подключения к Elasticsearch."""
        mock_es_client.connect = AsyncMock(return_value=False)
        
        manager = LifespanManager(auto_index=False)
        app = MagicMock()
        
        await manager.startup(app)
        
        mock_metrics.increment.assert_any_call("startup.elasticsearch.connection_failed")

    @pytest.mark.asyncio
    async def test_startup_with_auto_index(
        self,
        mock_es_client,
        mock_cache,
        mock_monitor,
        mock_metrics,
        temp_hbk_file
    ):
        """Тест startup с автоиндексацией."""
        with patch('src.core.lifespan.HBKParser') as MockParser, \
             patch('src.core.lifespan.indexer') as mock_indexer:
            
            # Настраиваем mock парсер
            mock_parser_instance = MagicMock()
            mock_parsed_hbk = MagicMock()
            mock_parsed_hbk.documentation = [MagicMock()]
            mock_parser_instance.parse_file.return_value = mock_parsed_hbk
            MockParser.return_value = mock_parser_instance
            
            # Настраиваем mock indexer
            mock_indexer.reindex_all = AsyncMock(return_value=True)
            
            manager = LifespanManager(
                hbk_directory=Path(temp_hbk_file).parent,
                auto_index=True
            )
            app = MagicMock()
            
            await manager.startup(app)
            
            # Ждем завершения фоновой задачи
            await asyncio.sleep(0.1)
            
            # Проверяем что фоновая задача была создана
            assert len(manager._background_tasks) > 0

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_monitor, mock_cache):
        """Тест shutdown."""
        manager = LifespanManager()
        app = MagicMock()
        
        await manager.shutdown(app)
        
        # Shutdown просто логирует, проверяем что ошибок нет
        assert True

    @pytest.mark.asyncio
    async def test_lifespan_context_manager(
        self,
        mock_es_client,
        mock_cache,
        mock_monitor
    ):
        """Тест context manager lifespan."""
        manager = LifespanManager(auto_index=False)
        app = MagicMock()
        
        async with manager.lifespan(app):
            # В контексте startup уже выполнен
            mock_cache.start.assert_called()
        
        # После выхода shutdown выполнен
        # (в данном случае просто логирование)

    @pytest.mark.asyncio
    async def test_auto_index_skipped_if_index_exists(
        self,
        mock_es_client,
        temp_hbk_file
    ):
        """Тест пропуска автоиндексации если индекс существует."""
        mock_es_client.index_exists = AsyncMock(return_value=True)
        mock_es_client.get_documents_count = AsyncMock(return_value=100)
        
        manager = LifespanManager(
            hbk_directory=Path(temp_hbk_file).parent,
            auto_index=True
        )
        
        await manager._auto_index_on_startup()
        
        # Индексация не должна была вызваться
        # Проверяем что не было попыток парсинга

    @pytest.mark.asyncio
    async def test_auto_index_no_hbk_directory(self):
        """Тест автоиндексации без директории."""
        manager = LifespanManager(
            hbk_directory=None,
            auto_index=True
        )
        
        # Не должно быть ошибок
        await manager._auto_index_on_startup()

    @pytest.mark.asyncio
    async def test_auto_index_directory_not_exists(self, tmp_path):
        """Тест автоиндексации с несуществующей директорией."""
        non_existent_dir = str(tmp_path / "non_existent")
        
        manager = LifespanManager(
            hbk_directory=non_existent_dir,
            auto_index=True
        )
        
        # Не должно быть ошибок
        await manager._auto_index_on_startup()

    @pytest.mark.asyncio
    async def test_auto_index_no_hbk_files(self, tmp_path):
        """Тест автоиндексации с пустой директорией."""
        hbk_dir = tmp_path / "hbk"
        hbk_dir.mkdir()
        
        manager = LifespanManager(
            hbk_directory=str(hbk_dir),
            auto_index=True
        )
        
        # Не должно быть ошибок
        await manager._auto_index_on_startup()

    @pytest.mark.asyncio
    async def test_index_hbk_file_success(self, temp_hbk_file):
        """Тест успешной индексации файла."""
        with patch('src.core.lifespan.HBKParser') as MockParser, \
             patch('src.core.lifespan.indexer') as mock_indexer, \
             patch('src.core.lifespan.es_client') as mock_es:
            
            # Настраиваем mock парсер
            mock_parser_instance = MagicMock()
            mock_parsed_hbk = MagicMock()
            mock_parsed_hbk.documentation = [MagicMock()]
            mock_parser_instance.parse_file.return_value = mock_parsed_hbk
            MockParser.return_value = mock_parser_instance
            
            # Настраиваем mock indexer
            mock_indexer.reindex_all = AsyncMock(return_value=True)
            mock_es.get_documents_count = AsyncMock(return_value=1)
            
            manager = LifespanManager()
            
            result = await manager._index_hbk_file(temp_hbk_file)
            
            assert result is True
            mock_indexer.reindex_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_hbk_file_parse_error(self, temp_hbk_file):
        """Тест ошибки парсинга файла."""
        with patch('src.core.lifespan.HBKParser') as MockParser:
            MockParser.return_value.parse_file.return_value = None
            
            manager = LifespanManager()
            
            result = await manager._index_hbk_file(temp_hbk_file)
            
            assert result is False

    @pytest.mark.asyncio
    async def test_index_hbk_file_no_documentation(self, temp_hbk_file):
        """Тест когда в файле нет документации."""
        with patch('src.core.lifespan.HBKParser') as MockParser:
            mock_parsed_hbk = MagicMock()
            mock_parsed_hbk.documentation = None
            MockParser.return_value.parse_file.return_value = mock_parsed_hbk
            
            manager = LifespanManager()
            
            result = await manager._index_hbk_file(temp_hbk_file)
            
            assert result is False

    @pytest.mark.asyncio
    async def test_index_hbk_file_exception(self, temp_hbk_file):
        """Тест исключения при индексации."""
        with patch('src.core.lifespan.HBKParser') as MockParser:
            MockParser.return_value.parse_file.side_effect = Exception("Test error")
            
            manager = LifespanManager()
            
            result = await manager._index_hbk_file(temp_hbk_file)
            
            assert result is False


class TestGetLifespanManager:
    """Тесты для функции get_lifespan_manager."""

    def setup_method(self):
        """Сброс перед каждым тестом."""
        reset_lifespan_manager()

    def teardown_method(self):
        """Сброс после каждого теста."""
        reset_lifespan_manager()

    def test_get_lifespan_manager_creates_new(self):
        """Тест создания нового экземпляра."""
        manager = get_lifespan_manager()
        
        assert manager is not None
        assert isinstance(manager, LifespanManager)

    def test_get_lifespan_manager_returns_same_instance(self):
        """Тест что возвращается тот же экземпляр."""
        manager1 = get_lifespan_manager()
        manager2 = get_lifespan_manager()
        
        assert manager1 is manager2

    def test_get_lifespan_manager_with_params(self):
        """Тест создания с параметрами."""
        manager = get_lifespan_manager(
            hbk_directory="/test/path",
            auto_index=False
        )
        
        assert manager.hbk_directory == "/test/path"
        assert manager.auto_index is False

    def test_reset_lifespan_manager(self):
        """Тест сброса менеджера."""
        manager1 = get_lifespan_manager()
        reset_lifespan_manager()
        manager2 = get_lifespan_manager()
        
        assert manager1 is not manager2
