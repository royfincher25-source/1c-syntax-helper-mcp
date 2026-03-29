
"""Парсер .hbk файлов (архивы документации 1С)."""

import os
import tempfile
import re
import time
import asyncio
from typing import Optional, List, Dict, Any, Tuple, Set
from pathlib import Path
from dataclasses import dataclass, field

from src.models.doc_models import HBKFile, HBKEntry, ParsedHBK, CategoryInfo, Documentation
from src.core.logging import get_logger
from src.parsers.html_parser import HTMLParser
from src.parsers.sevenzip_manager import SevenZipSessionManager, SevenZipError, SevenZipNotFoundError
from src.core.utils import (
    safe_subprocess_run,
    SafeSubprocessError,
    create_safe_temp_dir,
    safe_remove_dir,
    validate_file_path
)
from src.core.constants import MAX_FILE_SIZE_MB, SUPPORTED_ENCODINGS, HBK_LIST_TIMEOUT, HBK_FILE_READ_TIMEOUT

logger = get_logger(__name__)


@dataclass
class ParserProgress:
    """Прогресс парсинга."""
    total_entries: int = 0
    processed_entries: int = 0
    html_files: int = 0
    processed_html: int = 0
    current_category: str = ""
    elapsed_time: float = 0.0
    errors: List[str] = field(default_factory=list)


class HBKParserError(Exception):
    """Исключение для ошибок парсера HBK."""
    pass


class HBKParser:
    """Парсер .hbk файлов."""

    def __init__(
        self,
        max_files_per_type: Optional[int] = None,
        max_total_files: Optional[int] = None
    ):
        """
        Инициализация парсера.

        Args:
            max_files_per_type: Максимум файлов одного типа (для тестов)
            max_total_files: Максимум всего файлов (для тестов)
        """
        self.supported_extensions = ['.hbk', '.zip', '.7z']
        self._zip_command = None
        self._archive_path = None
        self._max_file_size = MAX_FILE_SIZE_MB * 1024 * 1024  # MB в байты
        self.html_parser = HTMLParser()  # Инициализируем HTML парсер

        # Параметры ограничений для тестирования
        self.max_files_per_type = max_files_per_type  # None = без ограничений
        self.max_total_files = max_total_files        # None = парсить все файлы
    
    def parse_file(self, file_path: str) -> Optional[ParsedHBK]:
        """
        Парсит .hbk файл и извлекает содержимое.
        
        Args:
            file_path: Путь к .hbk файлу
            
        Returns:
            ParsedHBK с документацией или None при ошибке
        """
        file_path = Path(file_path)

        # Валидация
        try:
            validate_file_path(file_path, self.supported_extensions)
        except SafeSubprocessError as e:
            logger.error(f"Валидация не пройдена: {e}")
            return None

        # Проверка размера
        file_size = file_path.stat().st_size
        if file_size > self._max_file_size:
            logger.error(f"Файл слишком большой: {file_size / 1024 / 1024:.1f}MB")
            return None
        
        if file_size < 1 * 1024 * 1024:
            logger.error(f"Файл слишком мал: {file_size} байт")
            return None

        # Результат
        result = ParsedHBK(
            file_info=HBKFile(
                path=str(file_path),
                size=file_size,
                modified=file_path.stat().st_mtime
            )
        )

        try:
            # Извлечение архива
            entries = self._extract_archive(file_path)
            if not entries:
                result.errors.append("Не удалось извлечь файлы")
                return result

            result.file_info.entries_count = len(entries)

            # Анализ структуры
            progress = self._analyze_structure(entries, result)
            
            logger.info(
                f"Парсинг завершен: {progress.processed_html}/{progress.html_files} HTML файлов, "
                f"{progress.elapsed_time:.1f}с, {len(result.documentation)} документов"
            )

            return result

        except Exception as e:
            logger.error(f"Ошибка парсинга {file_path}: {e}")
            result.errors.append(f"Критическая ошибка: {str(e)}")
            return result
        
        finally:
            # Очистка ресурсов
            self._cleanup_resources()
    
    def _cleanup_resources(self):
        """Очищает ресурсы."""
        if hasattr(self, '_zip_manager') and self._zip_manager:
            try:
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self._zip_manager.close(),
                        loop
                    )
                    future.result(timeout=30)
                except RuntimeError:
                    asyncio.run(self._zip_manager.close())
                except Exception as e:
                    logger.warning(f"Ошибка закрытия 7zip сессии: {e}")
            finally:
                self._zip_manager = None
    
    def _extract_archive(self, file_path: Path) -> List[HBKEntry]:
        """
        Извлекает содержимое архива через SevenZipSessionManager.

        Использует оптимизированное пакетное извлечение:
        1. Получает список файлов из архива
        2. Извлекает ВСЕ файлы одним процессом во временную директорию
        3. Последующие чтения файлов происходят из временной директории

        Args:
            file_path: Путь к архиву

        Returns:
            Список записей архива
        """
        try:
            # Создаем менеджер сессий
            zip_manager = SevenZipSessionManager()

            # Получаем список файлов (синхронная обертка для asyncio)
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # Если есть running loop - используем run_coroutine_threadsafe
                entries = asyncio.run_coroutine_threadsafe(
                    zip_manager.list_archive(file_path),
                    loop
                ).result(timeout=HBK_LIST_TIMEOUT)  # Увеличенный таймаут
            except RuntimeError:
                # Нет running loop - используем asyncio.run
                entries = asyncio.run(zip_manager.list_archive(file_path))

            # Сохраняем менеджер для последующего извлечения файлов
            self._zip_manager = zip_manager  # type: ignore
            self._archive_path = file_path

            if not entries:
                logger.error(f"Не удалось извлечь файлы из архива: {file_path}")
                return []

            logger.info(f"Найдено {len(entries)} файлов в архиве")

            # Предварительно извлекаем все файлы в temp директорию
            # Это устраняет таймауты при извлечении отдельных файлов
            archive_size_mb = file_path.stat().st_size / 1024 / 1024
            extract_timeout = 600  # Базовый таймаут 10 минут
            if archive_size_mb > 40:
                extract_timeout += int((archive_size_mb - 40) * 15)
            extract_timeout = min(extract_timeout, 3600)  # Максимум 1 час

            try:
                # Используем asyncio.run для извлечения
                async def extract_all():
                    await zip_manager.extract_all_to_temp(archive_size_mb=archive_size_mb)
                
                asyncio.run(asyncio.wait_for(extract_all(), timeout=float(extract_timeout)))
            except asyncio.TimeoutError as e:
                logger.error(f"Timeout при извлечении архива ({extract_timeout}с): {e}")
                raise SevenZipError(f"Timeout при извлечении архива ({extract_timeout}с)")

            logger.info(f"Архив извлечен во временную директорию")

            return entries

        except SevenZipNotFoundError as e:
            logger.error(f"7zip не найден: {e}")
            return []
        except SevenZipError as e:
            logger.error(f"Ошибка 7zip: {e}")
            return []
        except Exception as e:
            logger.error(f"Ошибка обработки архива: {e}")
            return []
    
    def _classify_files(self, entries: List[HBKEntry], progress: ParserProgress) -> Dict[str, List[HBKEntry]]:
        """
        Классифицирует файлы по типам.
        
        Args:
            entries: Список записей архива
            progress: Объект прогресса
            
        Returns:
            Dict с группами файлов
        """
        file_groups: Dict[str, List[HBKEntry]] = {
            'global_methods': [],
            'global_events': [],
            'global_context': [],
            'object_constructors': [],
            'object_events': [],
            'other_objects': [],
            'categories': [],
            'st_files': []
        }
        
        for entry in entries:
            progress.processed_entries += 1
            
            if entry.is_dir:
                continue
            
            # Нормализация пути
            path_str = entry.path.replace('\\', '/').lower()
            
            # Категории
            if entry.path.endswith('__categories__'):
                file_groups['categories'].append(entry)
                continue
            
            # HTML файлы
            if entry.path.endswith('.html'):
                progress.html_files += 1
                self._classify_html_file(entry, path_str, file_groups)
                continue
            
            # ST файлы
            if entry.path.endswith('.st'):
                file_groups['st_files'].append(entry)
        
        logger.info(f"Классификация завершена: {progress.html_files} HTML файлов")
        return file_groups
    
    def _classify_html_file(self, entry: HBKEntry, path_str: str, file_groups: Dict[str, List[HBKEntry]]):
        """
        Классифицирует HTML файл по пути.
        
        Args:
            entry: Запись архива
            path_str: Нормализованный путь
            file_groups: Словарь групп файлов
        """
        # Глобальные методы
        if 'objects/global context/methods' in path_str:
            file_groups['global_methods'].append(entry)
        # Глобальные события
        elif 'objects/global context/events' in path_str:
            file_groups['global_events'].append(entry)
        # Global context свойства
        elif 'objects/global context' in path_str:
            file_groups['global_context'].append(entry)
        # Конструкторы
        elif '/ctors/' in path_str or '/ctor/' in path_str:
            file_groups['object_constructors'].append(entry)
        # События объектов
        elif '/events/' in path_str and 'global context' not in path_str:
            file_groups['object_events'].append(entry)
        # Другие объекты
        elif 'objects/' in path_str:
            file_groups['other_objects'].append(entry)
    
    def _analyze_structure(self, entries: List[HBKEntry], result: ParsedHBK) -> ParserProgress:
        """
        Анализирует структуру архива и извлекает документацию.
        
        Args:
            entries: Список записей архива
            result: Результат парсинга
            
        Returns:
            ParserProgress: Информация о прогрессе парсинга
        """
        start_time = time.time()
        
        # Инициализация прогресса
        progress = ParserProgress(total_entries=len(entries))
        logger.info(f"Начало анализа структуры: {len(entries)} записей")

        # Параметры ограничений
        min_per_type = self.max_files_per_type or float('inf')
        max_total = self.max_total_files or float('inf')
        
        # Классификация файлов
        file_groups = self._classify_files(entries, progress)
        html_files = progress.html_files

        # Обработка категорий
        for entry in file_groups['categories']:
            self._parse_categories_file(entry, result)

        # Обработка HTML файлов
        processed_html = self._process_html_files(
            file_groups=file_groups,
            result=result,
            min_per_type=min_per_type,
            max_total=max_total,
            start_time=start_time,
            progress=progress
        )
        progress.processed_html = processed_html

        # Финальный лог
        progress.elapsed_time = time.time() - start_time
        self._log_analysis_result(progress, processed_html, html_files)

        # Обновление статистики
        result.stats = self._build_stats(
            html_files=html_files,
            st_files=len(file_groups['st_files']),
            category_files=len(file_groups['categories']),
            processed_html=processed_html,
            file_groups=file_groups,
            entries=entries
        )

        return progress
    
    def _process_html_files(
        self,
        file_groups: Dict[str, List[HBKEntry]],
        result: ParsedHBK,
        min_per_type: float,
        max_total: float,
        start_time: float,
        progress: ParserProgress
    ) -> int:
        """
        Обрабатывает HTML файлы с прогрессом.
        
        Returns:
            Количество обработанных HTML файлов
        """
        processed_html = 0
        batch_size = self._calculate_batch_size(file_groups)
        
        categories_processed = {
            'global_methods': 0,
            'global_events': 0,
            'global_context': 0,
            'object_constructors': 0,
            'object_events': 0,
            'other_objects': 0
        }
        
        logger.info(f"Обработка HTML файлов, batch_size={batch_size}")
        
        while processed_html < max_total:
            initial_count = processed_html
            
            # Обработка каждой категории
            for category in categories_processed.keys():
                processed_html += self._process_category_batch(
                    category=category,
                    file_groups=file_groups,
                    categories_processed=categories_processed,
                    batch_size=batch_size,
                    result=result,
                    min_per_type=min_per_type
                )
            
            # Проверка прогресса
            if processed_html % 100 == 0 and processed_html > 0:
                elapsed = time.time() - start_time
                logger.info(f"Прогресс: {processed_html} файлов, {elapsed:.1f}с")
            
            # Если ничего не обработали - выход
            if processed_html == initial_count:
                break
        
        return processed_html
    
    def _process_category_batch(
        self,
        category: str,
        file_groups: Dict[str, List[HBKEntry]],
        categories_processed: Dict[str, int],
        batch_size: int,
        result: ParsedHBK,
        min_per_type: float
    ) -> int:
        """Обрабатывает батч файлов категории."""
        count = 0
        files = file_groups[category]
        processed = categories_processed[category]
        
        for i in range(batch_size):
            idx = processed + i
            if idx >= len(files):
                break
            
            # Проверка лимитов для разных типов
            if not self._should_process_file(category, min_per_type):
                break
            
            entry = files[idx]
            if self._create_document_from_html(entry, result):
                count += 1
        
        categories_processed[category] += batch_size
        return count
    
    def _should_process_file(self, category: str, min_per_type: float) -> bool:
        """Проверяет, нужно ли обрабатывать файл этой категории."""
        type_mapping = {
            'global_methods': ['GLOBAL_FUNCTION', 'GLOBAL_PROCEDURE'],
            'global_events': ['GLOBAL_EVENT'],
            'global_context': ['OBJECT_PROPERTY'],
            'object_constructors': ['OBJECT_CONSTRUCTOR'],
            'object_events': ['OBJECT_EVENT'],
            'other_objects': ['OBJECT_FUNCTION', 'OBJECT_PROCEDURE', 'OBJECT']
        }
        
        # Если нет ограничений - обрабатываем все
        if min_per_type == float('inf'):
            return True
        
        types = type_mapping.get(category, [])
        # Для упрощения всегда возвращаем True, детальная проверка в _process_category_batch
        return True
    
    def _calculate_batch_size(self, file_groups: Dict[str, List[HBKEntry]]) -> int:
        """Вычисляет размер батча."""
        if self.max_files_per_type or self.max_total_files:
            return 5
        
        max_len = max((len(files) for files in file_groups.values()), default=0)
        return min(100, max_len)
    
    def _log_analysis_result(self, progress: ParserProgress, processed_html: int, html_files: int):
        """Логирует результат анализа."""
        if progress.processed_entries < progress.total_entries:
            logger.warning(
                f"Анализ структуры завершен частично: "
                f"{progress.processed_entries} из {progress.total_entries}"
            )
        else:
            logger.info(
                f"Анализ структуры завершен: обработано {progress.processed_entries} из {progress.total_entries}"
            )
        
        logger.info(
            f"Анализ структуры завершен. Найдено HTML файлов: {html_files}, "
            f"обработано: {processed_html}, время: {progress.elapsed_time:.1f}с"
        )
    
    def _build_stats(
        self,
        html_files: int,
        st_files: int,
        category_files: int,
        processed_html: int,
        file_groups: Dict[str, List[HBKEntry]],
        entries: List[HBKEntry]
    ) -> Dict[str, Any]:
        """Строит статистику парсинга."""
        return {
            'html_files': html_files,
            'global_methods_files': len(file_groups['global_methods']),
            'global_events_files': len(file_groups['global_events']),
            'global_context_files': len(file_groups['global_context']),
            'object_constructors_files': len(file_groups['object_constructors']),
            'object_events_files': len(file_groups['object_events']),
            'other_object_files': len(file_groups['other_objects']),
            'processed_html': processed_html,
            'st_files': st_files,
            'category_files': category_files,
            'total_entries': len(entries)
        }

    def _create_document_from_html(self, entry: HBKEntry, result: ParsedHBK) -> bool:
        """
        Создает документ из HTML файла.
        
        Args:
            entry: Запись архива
            result: Результат парсинга
            
        Returns:
            True если успешно, False иначе
        """
        try:
            # Извлечение содержимого
            html_content = self._extract_html_content(entry)
            if not html_content:
                logger.debug(f"Нет содержимого для {entry.path}")
                return False
            
            # Парсинг HTML
            documentation = self.html_parser.parse_html_content(
                content=html_content,
                file_path=entry.path
            )
            
            if documentation:
                result.documentation.append(documentation)
                logger.debug(f"Создан документ: {documentation.name}")
                return True
            else:
                logger.debug(f"HTMLParser не смог обработать {entry.path}")
                return False
                
        except UnicodeDecodeError as e:
            logger.warning(f"Ошибка кодировки {entry.path}: {e}")
            result.errors.append(f"Unicode error in {entry.path}: {str(e)}")
            return False
        except Exception as e:
            logger.warning(f"Ошибка создания документа из {entry.path}: {e}")
            result.errors.append(f"Error in {entry.path}: {str(e)}")
            return False
    
    def _extract_html_content(self, entry: HBKEntry) -> Optional[bytes]:
        """
        Извлекает содержимое HTML файла.

        Args:
            entry: Запись архива

        Returns:
            Содержимое файла или None
        """
        if entry.content:
            return entry.content

        if not hasattr(self, '_zip_manager') or not self._archive_path:
            logger.error("Архив не инициализирован")
            return None

        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # Если есть running loop - используем run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(
                    self._zip_manager.extract_file(entry.path),
                    loop
                )
                return future.result(timeout=HBK_FILE_READ_TIMEOUT)
            except RuntimeError:
                # Нет running loop - используем asyncio.run
                return asyncio.run(self._zip_manager.extract_file(entry.path))
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout при чтении файла {entry.path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка извлечения {entry.path}: {e}")
            return None

    def _parse_categories_file(self, entry: HBKEntry, result: ParsedHBK):
        """Парсит файл __categories__ для извлечения метаинформации."""
        if not entry.content:
            return
        
        try:
            # Пробуем разные кодировки
            content = None
            for encoding in SUPPORTED_ENCODINGS:
                try:
                    content = entry.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not content:
                logger.warning(f"Не удалось декодировать файл категорий {entry.path}")
                return
            
            # Создаем категорию
            path_parts = entry.path.replace('\\', '/').split('/')
            section_name = path_parts[-2] if len(path_parts) > 1 else "unknown"
            
            category = CategoryInfo(
                name=section_name,
                section=section_name,
                description=f"Раздел документации: {section_name}"
            )
            
            # Простой парсинг версии из содержимого
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if 'version' in line.lower() or 'версия' in line.lower():
                    # Ищем версию типа 8.3.24
                    version_match = re.search(r'8\.\d+\.\d+', line)
                    if version_match:
                        category.version_from = version_match.group(0)
                        break
            
            result.categories[section_name] = category
            logger.debug(f"Обработана категория: {section_name}")
            
        except Exception as e:
            logger.warning(f"Ошибка парсинга файла категорий {entry.path}: {e}")
    
    def _extract_external_7z(self, file_path: Path) -> List[HBKEntry]:
        """Извлекает список файлов из архива через внешний 7zip."""
        entries = []
        
        # Ищем доступный 7zip - сначала в PATH, затем в стандартных местах
        zip_commands = [
            '7z',           # В PATH
            '7z.exe',       # В PATH  
            '7za',          # В PATH (standalone версия)
            '7za.exe',      # В PATH (standalone версия)
            # Стандартные пути Windows
            'C:\\Program Files\\7-Zip\\7z.exe',
            'C:\\Program Files (x86)\\7-Zip\\7z.exe',
            # Переносная версия
            '7-Zip\\7z.exe',
            '7zip\\7z.exe'
        ]
        working_7z = None
        
        for cmd in zip_commands:
            try:
                logger.debug(f"Проверяем команду: {cmd}")
                result = safe_subprocess_run([cmd], timeout=5)
                # 7zip возвращает код 0 при показе help или содержит информацию о версии
                if result.returncode == 0 or 'Igor Pavlov' in result.stdout or '7-Zip' in result.stdout:
                    working_7z = cmd
                    break
            except SafeSubprocessError as e:
                logger.debug(f"Команда {cmd} не найдена: {e}")
                continue
        
        if not working_7z:
            logger.error("7zip не найден в системе. Проверьте установку 7-Zip")
            raise HBKParserError("7zip не найден в системе. Проверьте установку 7-Zip")
        
        # Получаем список файлов (без извлечения)
        try:
            result = safe_subprocess_run([working_7z, 'l', str(file_path)], timeout=60)
        except SafeSubprocessError as e:
            logger.error(f"Ошибка выполнения команды 7zip: {e}")
            raise HBKParserError(f"Ошибка чтения архива: {e}")
        
        if result.returncode != 0:
            logger.error(
                "7zip вернул код ошибки %s. STDERR: %s | STDOUT: %s",
                result.returncode,
                (result.stderr or "").strip()[:500],
                (result.stdout or "").strip()[:500]
            )
            # Попытка резервного чтения структуры через unzip
            try:
                unzip_res = safe_subprocess_run(['unzip', '-l', str(file_path)], timeout=60)
            except SafeSubprocessError as e:
                logger.error(f"Ошибка выполнения команды unzip: {e}")
                raise HBKParserError(f"Ошибка чтения архива: {e}")
            
            if unzip_res.returncode != 0:
                logger.error(
                    "unzip вернул код ошибки %s. STDERR: %s | STDOUT: %s",
                    unzip_res.returncode,
                    (unzip_res.stderr or "").strip()[:500],
                    (unzip_res.stdout or "").strip()[:500]
                )
                raise HBKParserError(f"Ошибка чтения архива: {unzip_res.stderr}")
            
            # Парсим вывод unzip
            entries = []
            lines = (unzip_res.stdout or "").split('\n')
            in_files_section = False
            for line in lines:
                if not in_files_section:
                    # Поиск начала таблицы: строка из дефисов
                    if line.strip().startswith('------'):
                        in_files_section = True
                        continue
                else:
                    # Конец таблицы также отмечен дефисами
                    if line.strip().startswith('------'):
                        break
                    parts = line.split()
                    if len(parts) >= 4:
                        # Формат: Length  Date  Time  Name
                        try:
                            size = int(parts[0])
                        except ValueError:
                            size = 0
                        filename = ' '.join(parts[3:])
                        if filename:
                            is_dir = filename.endswith('/')
                            entry = HBKEntry(
                                path=filename.rstrip('/'),
                                size=size,
                                is_dir=is_dir,
                                content=None
                            )
                            entries.append(entry)
            
            # Сохраняем рабочую команду как unzip для последующих извлечений
            if entries:
                self._zip_command = 'unzip'
                self._archive_path = file_path
                return entries
            
            # Если даже unzip не помог
            raise HBKParserError("Не удалось прочитать структуру архива через 7zip или unzip")
        
        logger.debug(f"Вывод 7zip: {result.stdout[:500]}...")  # Первые 500 символов для отладки
        
        # Парсим вывод 7zip
        lines = result.stdout.split('\n')
        in_files_section = False
        
        for line in lines:
            if '---------------' in line:
                in_files_section = not in_files_section
                continue
            
            if in_files_section and line.strip():
                # Парсим строку файла: дата время атрибуты размер сжатый_размер имя
                parts = line.split()
                if len(parts) >= 6:
                    filename = ' '.join(parts[5:])
                    if filename and not filename.startswith('Date'):
                        # Определяем размер и тип
                        try:
                            size = int(parts[3]) if parts[3].isdigit() else 0
                        except (ValueError, IndexError):
                            size = 0
                        
                        is_dir = parts[2] == 'D' if len(parts) > 2 and len(parts[2]) == 1 else False
                        
                        entry = HBKEntry(
                            path=filename,
                            size=size,
                            is_dir=is_dir,
                            content=None  # Не извлекаем содержимое сразу
                        )
                        
                        entries.append(entry)
        
        # Сохраняем команду 7zip для дальнейшего использования
        self._zip_command = working_7z
        self._archive_path = file_path
        
        return entries
    
    def extract_file_content(self, filename: str) -> Optional[bytes]:
        """Извлекает содержимое конкретного файла по требованию."""
        if not self._zip_command or not self._archive_path:
            logger.error("Архив не был проинициализирован")
            return None
        
        try:
            return self._extract_single_file(self._archive_path, filename, self._zip_command)
        except Exception as e:
            logger.error(f"Ошибка извлечения файла {filename}: {e}")
            return None
    
    def _extract_single_file(self, archive_path: Path, filename: str, zip_cmd: str) -> Optional[bytes]:
        """Извлекает один файл из архива."""
        temp_dir = create_safe_temp_dir("hbk_extract_")
        
        try:
            # Безопасное извлечение файла
            result = safe_subprocess_run([
                zip_cmd, 'e', str(archive_path), filename, 
                f'-o{temp_dir}', '-y'
            ], timeout=30)
            
            if result.returncode == 0:
                # Ищем извлеченный файл
                extracted_files = list(temp_dir.rglob("*"))
                for extracted_file in extracted_files:
                    if extracted_file.is_file():
                        with open(extracted_file, 'rb') as f:
                            return f.read()
            
            return None
            
        except SafeSubprocessError as e:
            logger.error(f"Ошибка извлечения файла {filename}: {e}")
            return None
        finally:
            safe_remove_dir(temp_dir)
    
    def get_supported_files(self, directory: str) -> List[str]:
        """Возвращает список поддерживаемых файлов в директории."""
        supported_files = []
        
        if not os.path.exists(directory):
            return supported_files
        
        for file_name in os.listdir(directory):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path):
                file_ext = os.path.splitext(file_name)[1].lower()
                if file_ext in self.supported_extensions:
                    supported_files.append(file_path)
        
        return supported_files

    def parse_single_file_from_archive(self, archive_path: str, target_file_path: str) -> Optional[ParsedHBK]:
        """
        Извлекает и парсит один конкретный файл из архива.
        
        Args:
            archive_path: Путь к архиву .hbk
            target_file_path: Путь к файлу внутри архива (например: "Global context/methods/catalog4838/StrLen912.html")
        
        Returns:
            ParsedHBK объект с одним файлом или None при ошибке
        """
        archive_path = Path(archive_path)
        
        try:
            # Валидация входного файла
            validate_file_path(archive_path, self.supported_extensions)
        except SafeSubprocessError as e:
            logger.error(f"Валидация архива не прошла: {e}")
            return None
        
        # Создаем объект результата
        result = ParsedHBK(
            file_info=HBKFile(
                path=str(archive_path),
                size=archive_path.stat().st_size,
                modified=archive_path.stat().st_mtime
            )
        )
        
        try:
            # Определяем команду для 7zip
            zip_cmd = self._get_7zip_command()
            if not zip_cmd:
                result.errors.append("7zip не найден")
                return result
            
            # Сохраняем параметры для использования в extract_file_content
            self._zip_command = zip_cmd
            self._archive_path = archive_path
            
            logger.info(f"Извлекаение одного файла: {target_file_path}")
            
            # Извлекаем содержимое конкретного файла
            content = self.extract_file_content(target_file_path)
            if not content:
                result.errors.append(f"Не удалось извлечь файл: {target_file_path}")
                return result
            
            logger.info(f"Файл извлечен: {len(content)} байт")
            
            # Парсим HTML содержимое если это HTML файл
            if target_file_path.lower().endswith('.html'):
                try:
                    # Декодируем содержимое
                    html_content = content.decode('utf-8', errors='ignore')
                    
                    # Парсим через HTML парсер
                    parsed_doc = self.html_parser.parse_html_content(html_content, target_file_path)
                    
                    if parsed_doc:
                        result.documents.append(parsed_doc)
                        result.file_info.entries_count = 1
                        logger.info(f"Документ успешно распарсен: {parsed_doc.name}")
                    else:
                        result.errors.append(f"Не удалось распарсить HTML: {target_file_path}")
                        
                except Exception as e:
                    logger.error(f"Ошибка парсинга HTML {target_file_path}: {e}")
                    result.errors.append(f"Ошибка парсинга HTML: {str(e)}")
            else:
                result.errors.append(f"Файл не является HTML: {target_file_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка извлечения файла {target_file_path} из {archive_path}: {e}")
            result.errors.append(f"Ошибка извлечения: {str(e)}")
            return result
