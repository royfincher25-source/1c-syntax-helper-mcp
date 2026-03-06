"""Тесты для SevenZipSessionManager."""

import pytest
import asyncio
from pathlib import Path
from src.parsers.sevenzip_manager import SevenZipSessionManager, SevenZipError, SevenZipNotFoundError


@pytest.fixture
def sevenzip_manager() -> SevenZipSessionManager:
    """Создает менеджер сессий."""
    return SevenZipSessionManager()


@pytest.mark.asyncio
async def test_find_7zip_command(ssevenzip_manager: SevenZipSessionManager):
    """Тест поиска команды 7zip."""
    cmd = await sevenzip_manager.find_7zip_command()
    assert cmd is not None
    assert isinstance(cmd, str)
    assert sevenzip_manager._command == cmd


@pytest.mark.asyncio
async def test_find_7zip_command_caches(ssevenzip_manager: SevenZipSessionManager):
    """Тест кэширования команды 7zip."""
    cmd1 = await sevenzip_manager.find_7zip_command()
    cmd2 = await sevenzip_manager.find_7zip_command()
    assert cmd1 == cmd2


@pytest.mark.asyncio
async def test_list_archive_not_initialized(ssevenzip_manager: SevenZipSessionManager, tmp_path: Path):
    """Тест с неинициализированным архивом."""
    # Должен найти 7zip и прочитать архив
    # Для несуществующего архива должна быть ошибка
    invalid_archive = tmp_path / "nonexistent.hbk"
    with pytest.raises(SevenZipError):
        await sevenzip_manager.list_archive(invalid_archive)


@pytest.mark.asyncio
async def test_extract_file_not_initialized(ssevenzip_manager: SevenZipSessionManager):
    """Тест извлечения без инициализации архива."""
    result = await sevenzip_manager.extract_file("test.html")
    assert result is None


class TestSevenZipOutputParser:
    """Тесты парсинга вывода 7zip."""
    
    @pytest.fixture
    def manager(self) -> SevenZipSessionManager:
        return SevenZipSessionManager()
    
    def test_parse_typical_output(self, manager: SevenZipSessionManager):
        """Тест парсинга типичного вывода 7zip."""
        output = """
7-Zip 19.00 (x64) : Copyright (c) 1999-2018 Igor Pavlov : 2019-02-21

Scanning the drive for archives:
1 file, 1234 bytes (1 KiB)

Listing archive: test.hbk

--
Path = test.hbk
Type = hbk
Physical Size = 1234

----------
Date      Time    Attr    Size   Compressed  Name
------------------- ----- -------------- --------------
2024-01-01 12:00:00 D....            0            0  folder
2024-01-01 12:00:00 A....         1234          567  file.html
2024-01-01 12:00:00 A....         5678         1234  objects/Global context/methods/StrLen.html
------------------- ----- -------------- --------------
3 files
"""
        entries = manager._parse_7zip_output(output)
        
        assert len(entries) == 3
        assert entries[0].path == "folder"
        assert entries[0].is_dir is True
        assert entries[0].size == 0
        
        assert entries[1].path == "file.html"
        assert entries[1].is_dir is False
        assert entries[1].size == 1234
        
        assert entries[2].path == "objects/Global context/methods/StrLen.html"
        assert entries[2].size == 5678
    
    def test_parse_empty_output(self, manager: SevenZipSessionManager):
        """Тест парсинга пустого вывода."""
        entries = manager._parse_7zip_output("")
        assert len(entries) == 0
    
    def test_parse_malformed_output(self, manager: SevenZipSessionManager):
        """Тест парсинга некорректного вывода."""
        output = "Some random text\nwithout proper format"
        entries = manager._parse_7zip_output(output)
        assert len(entries) == 0
