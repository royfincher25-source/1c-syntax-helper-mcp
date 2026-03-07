"""Менеджер сессий 7zip для оптимизации I/O операций."""

import asyncio
import tempfile
import shutil
from typing import Optional, List, Dict
from pathlib import Path

from src.core.logging import get_logger
from src.models.doc_models import HBKEntry
from src.core.constants import (
    HBK_EXTRACT_TIMEOUT_BASE,
    HBK_EXTRACT_TIMEOUT_PER_MB,
    HBK_EXTRACT_TIMEOUT_MAX,
    MEMORY_CACHE_LIMIT_MB,
    MEMORY_CACHE_LIMIT_FILES
)

logger = get_logger(__name__)


class SevenZipError(Exception):
    """Ошибка операции 7zip."""
    pass


class SevenZipNotFoundError(Exception):
    """7zip не найден в системе."""
    pass


class SevenZipSessionManager:
    """
    Менеджер сессий 7zip с оптимизацией для больших архивов.

    Использует пакетное извлечение всех файлов в temp директорию,
    что устраняет накладные расходы на запуск процесса для каждого файла.
    
    Поддерживает:
    - Автоматический расчет таймаута в зависимости от размера архива
    - Прогресс извлечения с логированием
    - LRU кэширование файлов с лимитами памяти
    """

    def __init__(self, max_idle_time: int = 300):
        """
        Инициализация менеджера.

        Args:
            max_idle_time: Максимальное время простоя процесса в секундах
        """
        self._max_idle_time = max_idle_time
        self._command: Optional[str] = None
        self._archive_path: Optional[Path] = None
        self._temp_dir: Optional[Path] = None
        self._extracted_files: Dict[str, bytes] = {}
        self._is_extracted = False
        self._total_size_bytes = 0  # Общий размер извлеченных файлов
        self._files_count = 0  # Количество извлеченных файлов

    async def find_7zip_command(self) -> str:
        """Находит доступную команду 7zip."""
        commands = [
            '7z', '7z.exe',
            '7za', '7za.exe',
            'C:\\Program Files\\7-Zip\\7z.exe',
            'C:\\Program Files (x86)\\7-Zip\\7z.exe',
        ]

        for cmd in commands:
            try:
                if await self._test_command(cmd):
                    logger.debug(f"Найдена рабочая команда 7zip: {cmd}")
                    self._command = cmd
                    return cmd
            except Exception as e:
                logger.debug(f"Команда {cmd} не работает: {e}")
                continue

        raise SevenZipNotFoundError("7zip не найден в системе. Установите 7-Zip.")

    async def _test_command(self, cmd: str) -> bool:
        """Тестирует команду 7zip."""
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=5.0
            )
            return (proc.returncode == 0 or
                    b'Igor Pavlov' in stdout or
                    b'7-Zip' in stdout)
        except (asyncio.TimeoutError, FileNotFoundError, OSError):
            return False

    async def list_archive(self, archive_path: Path) -> List[HBKEntry]:
        """
        Получает список файлов из архива.

        Args:
            archive_path: Путь к архиву

        Returns:
            Список записей архива
        """
        if not self._command:
            self._command = await self.find_7zip_command()

        self._archive_path = archive_path
        cmd = [self._command, 'l', str(archive_path)]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=300.0  # Увеличенный таймаут для больших архивов (5 минут)
            )

            # 7zip возвращает exit code 1-2 при предупреждениях, но данные все равно читает
            # exit code 0 = успех, 1 = предупреждения, 2 = ошибки в заголовках но данные есть
            if proc.returncode > 2:
                error_msg = stderr.decode('utf-8', errors='ignore')[:500]
                logger.error(f"7zip error: {error_msg}")
                raise SevenZipError(f"Ошибка чтения архива: {error_msg}")

            # Логируем предупреждения если они есть
            if proc.returncode > 0:
                warning_msg = stderr.decode('utf-8', errors='ignore')[:200]
                logger.warning(f"7zip warnings (returncode={proc.returncode}): {warning_msg}")

            return self._parse_7zip_output(stdout.decode('utf-8', errors='ignore'))

        except asyncio.TimeoutError:
            logger.error(f"Timeout при чтении архива {archive_path}")
            raise SevenZipError("Timeout при чтении архива")

    def _parse_7zip_output(self, output: str) -> List[HBKEntry]:
        """Парсит вывод 7zip."""
        entries = []
        lines = output.split('\n')
        in_files_section = False

        for line in lines:
            if '---------------' in line:
                in_files_section = not in_files_section
                continue

            if in_files_section and line.strip():
                parts = line.split()
                if len(parts) >= 6:
                    filename = ' '.join(parts[5:])
                    if filename and not filename.startswith('Date'):
                        try:
                            size = int(parts[3]) if parts[3].isdigit() else 0
                        except (ValueError, IndexError):
                            size = 0

                        is_dir = parts[2] == 'D' if len(parts) > 2 and len(parts[2]) == 1 else False

                        entry = HBKEntry(
                            path=filename,
                            size=size,
                            is_dir=is_dir,
                            content=None
                        )
                        entries.append(entry)

        return entries

    async def extract_all_to_temp(self, archive_size_mb: float = 40.0) -> bool:
        """
        Пакетно извлекает все файлы из архива во временную директорию.

        Это устраняет накладные расходы на запуск процесса для каждого файла
        и позволяет избежать таймаутов при извлечении больших архивов.
        
        Args:
            archive_size_mb: Размер архива в MB для расчета таймаута

        Returns:
            True если извлечение успешно
        """
        if not self._command or not self._archive_path:
            logger.error("Архив не инициализирован")
            return False

        if self._is_extracted:
            logger.debug("Файлы уже извлечены")
            return True

        # Расчет таймаута в зависимости от размера архива
        # Формула: базовый таймаут + (размер_сверх_40MB * секунды_na_MB)
        timeout = HBK_EXTRACT_TIMEOUT_BASE
        if archive_size_mb > 40:
            extra_mb = archive_size_mb - 40
            timeout += int(extra_mb * HBK_EXTRACT_TIMEOUT_PER_MB)
        timeout = min(timeout, HBK_EXTRACT_TIMEOUT_MAX)  # Ограничиваем максимум
        
        logger.info(f"Извлечение архива ({archive_size_mb:.1f}MB) с таймаутом {timeout}с")

        try:
            # Создаем временную директорию
            self._temp_dir = Path(tempfile.mkdtemp(prefix="7zip_extract_"))
            logger.info(f"Временная директория: {self._temp_dir}")

            # Извлекаем все файлы одним процессом
            # -o указывает директорию назначения
            # -y автоматически отвечает Yes на все вопросы
            cmd = [self._command, 'x', str(self._archive_path), f'-o{self._temp_dir}', '-y']

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Чтение вывода с прогрессом
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(timeout)
            )

            if proc.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')[:500]
                logger.error(f"Ошибка извлечения: {error_msg}")
                raise SevenZipError(f"Ошибка извлечения архива: {error_msg}")

            self._is_extracted = True
            logger.info(f"Архив извлечен: {self._temp_dir}")
            return True

        except asyncio.TimeoutError:
            logger.error(f"Timeout ({timeout}с) при извлечении архива {archive_size_mb:.1f}MB")
            raise SevenZipError(f"Timeout при извлечении архива ({timeout}с)")
        except Exception as e:
            logger.error(f"Ошибка при извлечении архива: {e}")
            if self._temp_dir and self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            raise

    async def extract_file(self, filename: str) -> Optional[bytes]:
        """
        Извлекает файл из архива.

        Если архив еще не извлечен, сначала выполняется пакетное извлечение.
        Затем файл читается из временной директории.
        
        При превышении лимитов памяти удаляет старые файлы из кэша (LRU).

        Args:
            filename: Имя файла в архиве

        Returns:
            Содержимое файла или None
        """
        if not self._archive_path:
            logger.error("Архив не инициализирован")
            return None

        # Проверяем кэш
        if filename in self._extracted_files:
            return self._extracted_files[filename]

        # Если архив еще не извлечен, извлекаем все файлы
        if not self._is_extracted:
            await self.extract_all_to_temp()

        if not self._temp_dir:
            logger.error("Временная директория не создана")
            return None

        # Нормализуем путь (7zip может использовать разные разделители)
        normalized_filename = filename.replace('/', '\\')
        file_path = self._temp_dir / normalized_filename

        # Пробуем разные варианты пути
        if not file_path.exists():
            # Пробуем с прямыми слэшами
            normalized_filename = filename.replace('\\', '/')
            file_path = self._temp_dir / normalized_filename

        if not file_path.exists():
            logger.warning(f"Файл не найден: {filename}")
            return None

        try:
            # Читаем файл
            content = file_path.read_bytes()
            
            # Проверка лимитов памяти перед добавлением в кэш
            self._enforce_cache_limits(content)
            
            # Кэшируем в памяти
            self._extracted_files[filename] = content
            self._total_size_bytes += len(content)
            self._files_count += 1
            
            logger.debug(f"Файл извлечен: {filename} ({len(content)} байт, кэш: {self._files_count} файлов, {self._total_size_bytes / 1024 / 1024:.1f}MB)")
            return content

        except Exception as e:
            logger.warning(f"Ошибка чтения файла {filename}: {e}")
            return None

    def _enforce_cache_limits(self, new_content: bytes) -> None:
        """
        Применяет лимиты кэша, удаляя старые файлы при необходимости.
        
        Args:
            new_content: Новый файл для добавления в кэш
        """
        new_size = len(new_content)
        cache_limit_bytes = MEMORY_CACHE_LIMIT_MB * 1024 * 1024
        
        # Удаляем файлы пока не достигнем лимита
        while (self._total_size_bytes + new_size > cache_limit_bytes or 
               self._files_count >= MEMORY_CACHE_LIMIT_FILES) and self._extracted_files:
            # Удаляем первый (самый старый) файл из кэша
            oldest_key = next(iter(self._extracted_files))
            removed_size = len(self._extracted_files[oldest_key])
            del self._extracted_files[oldest_key]
            self._total_size_bytes -= removed_size
            self._files_count -= 1
            logger.debug(f"LRU eviction: удален {oldest_key} ({removed_size} байт)")

    async def close(self):
        """Закрывает сессию 7zip и очищает временные файлы."""
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                logger.info(f"Временная директория удалена: {self._temp_dir}")
            except Exception as e:
                logger.warning(f"Ошибка удаления временной директории: {e}")
            finally:
                self._temp_dir = None

        self._extracted_files.clear()
        self._command = None
        self._archive_path = None
        self._is_extracted = False
        logger.debug("7zip сессия закрыта")
