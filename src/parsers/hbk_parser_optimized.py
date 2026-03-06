"""Оптимизированный парсер .hbk файлов с параллельной обработкой."""

import asyncio
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import OrderedDict

from src.models.doc_models import HBKFile, HBKEntry, ParsedHBK, CategoryInfo, Documentation
from src.core.logging import get_logger
from src.parsers.html_parser import HTMLParser
from src.parsers.sevenzip_manager import SevenZipSessionManager, SevenZipError, SevenZipNotFoundError
from src.core.constants import (
    MAX_FILE_SIZE_MB, SUPPORTED_ENCODINGS, HBK_LIST_TIMEOUT,
    PARALLEL_PARSE_LIMIT, PARSE_BATCH_SIZE, DOC_CACHE_SIZE,
    HBK_EXTRACT_TIMEOUT_BASE, HBK_EXTRACT_TIMEOUT_PER_MB, HBK_EXTRACT_TIMEOUT_MAX
)

logger = get_logger(__name__)


class LRUDocCache:
    """LRU кэш для распарсенных документов на базе OrderedDict."""
    
    def __init__(self, max_size: int = DOC_CACHE_SIZE):
        self._cache: OrderedDict[str, Documentation] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Documentation]:
        """Получает документ из кэша."""
        if key in self._cache:
            self._cache.move_to_end(key)  # O(1)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None
    
    def set(self, key: str, value: Documentation):
        """Сохраняет документ в кэш с eviction самого старого."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # O(1) - удаляем самый старый
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Статистика кэша."""
        total = self._hits + self._misses
        return {
            'size': len(self._cache),
            'max_size': self._max_size,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': (self._hits / total * 100) if total > 0 else 0,
        }


class HBKParserOptimized:
    """
    Оптимизированный парсер .hbk файлов.
    
    Оптимизации:
    1. Параллельный парсинг HTML файлов (asyncio.gather с semaphore)
    2. LRU кэш результатов парсинга
    3. Пакетная обработка файлов
    """
    
    def __init__(self):
        self.supported_extensions = ['.hbk', '.zip', '.7z']
        self._max_file_size = MAX_FILE_SIZE_MB * 1024 * 1024
        self.html_parser = HTMLParser()
        self._doc_cache = LRUDocCache(max_size=DOC_CACHE_SIZE)
        self._zip_manager: Optional[SevenZipSessionManager] = None
        self._archive_path: Optional[Path] = None
        self._parse_status = "idle"
        self._parse_progress = 0.0
        self._parse_message = "No active parsing task"
    
    async def parse_file_async(self, file_path: Path) -> Optional[ParsedHBK]:
        """
        Асинхронный парсинг .hbk файла.
        
        Args:
            file_path: Путь к .hbk файлу
            
        Returns:
            ParsedHBK с документацией или None при ошибке
        """
        # Валидация
        if not file_path.exists():
            logger.error(f"Файл не найден: {file_path}")
            return None
        
        if file_path.suffix.lower() not in self.supported_extensions:
            logger.error(f"Неподдерживаемое расширение: {file_path.suffix}")
            return None
        
        file_size = file_path.stat().st_size
        if file_size > self._max_file_size:
            logger.error(f"Файл слишком большой: {file_size / 1024 / 1024:.1f}MB")
            return None
        
        # Предупреждение о малом размере (не ошибка)
        if file_size < 100 * 1024:  # 100KB
            logger.warning(f"Файл подозрительно мал: {file_size} байт")

        self._parse_status = "parsing"
        self._parse_progress = 0.0
        self._parse_message = f"Начало парсинга: {file_path.name}"
        logger.info(f"Начало парсинга: {file_path} ({file_size / 1024 / 1024:.1f}MB)")
        start_time = time.time()
        
        result = ParsedHBK(
            file_info=HBKFile(
                path=str(file_path),
                size=file_size,
                modified=file_path.stat().st_mtime
            )
        )
        
        try:
            # Извлечение архива
            entries = await self._extract_archive_async(file_path)
            if not entries:
                result.errors.append("Не удалось извлечь файлы")
                return result
            
            result.file_info.entries_count = len(entries)
            logger.info(f"Найдено {len(entries)} файлов в архиве")
            
            # Классификация файлов
            html_entries = self._classify_files(entries)
            logger.info(f"HTML файлов для парсинга: {len(html_entries)}")
            
            # Параллельный парсинг
            documents = await self._parse_html_files_parallel(html_entries)
            result.documentation = documents
            
            # Парсинг категорий
            category_entries = [e for e in entries if e.path.endswith('__categories__')]
            for entry in category_entries:
                self._parse_categories_file(entry, result)
            
            elapsed = time.time() - start_time
            logger.info(
                f"Парсинг завершен: {len(documents)} документов за {elapsed:.1f}с "
                f"({len(documents) / elapsed:.1f} док/с)"
            )
            
            # Статистика кэша
            cache_stats = self._doc_cache.stats
            logger.info(f"Кэш документов: {cache_stats['size']}/{cache_stats['max_size']}, hit rate: {cache_stats['hit_rate']:.1f}%")
            
            return result
            
        except asyncio.CancelledError:
            logger.warning("Парсинг отменен пользователем")
            result.errors.append("Парсинг отменен пользователем")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка парсинга {file_path}: {e}", exc_info=True)
            result.errors.append(f"Критическая ошибка: {str(e)}")
            return result
        finally:
            await self._cleanup_async()
    
    async def _extract_archive_async(self, file_path: Path) -> List[HBKEntry]:
        """Извлекает архив асинхронно."""
        try:
            self._zip_manager = SevenZipSessionManager()
            self._archive_path = file_path
            
            # Список файлов
            entries = await asyncio.wait_for(
                self._zip_manager.list_archive(file_path),
                timeout=HBK_LIST_TIMEOUT
            )
            
            if not entries:
                return []
            
            # Пакетное извлечение
            archive_size_mb = file_path.stat().st_size / 1024 / 1024
            extract_timeout = self._calculate_extract_timeout(archive_size_mb)
            
            await asyncio.wait_for(
                self._zip_manager.extract_all_to_temp(archive_size_mb=archive_size_mb),
                timeout=extract_timeout
            )
            
            logger.info(f"Архив извлечен во временную директорию")
            return entries
            
        except SevenZipNotFoundError as e:
            logger.error(f"7zip не найден: {e}")
            return []
        except SevenZipError as e:
            logger.error(f"Ошибка 7zip: {e}")
            return []
    
    def _calculate_extract_timeout(self, archive_size_mb: float) -> float:
        """Расчитывает таймаут извлечения."""
        from src.core.constants import (
            HBK_EXTRACT_TIMEOUT_BASE,
            HBK_EXTRACT_TIMEOUT_PER_MB,
            HBK_EXTRACT_TIMEOUT_MAX
        )
        
        timeout = HBK_EXTRACT_TIMEOUT_BASE
        if archive_size_mb > 40:
            timeout += (archive_size_mb - 40) * HBK_EXTRACT_TIMEOUT_PER_MB
        return min(timeout, HBK_EXTRACT_TIMEOUT_MAX)
    
    def _classify_files(self, entries: List[HBKEntry]) -> List[HBKEntry]:
        """Классифицирует файлы и возвращает только HTML."""
        return [e for e in entries if e.path.endswith('.html') and not e.is_dir]
    
    async def _parse_html_files_parallel(self, entries: List[HBKEntry]) -> List[Documentation]:
        """
        Параллельный парсинг HTML файлов.
        
        Использует semaphore для ограничения параллелизма.
        """
        semaphore = asyncio.Semaphore(PARALLEL_PARSE_LIMIT)
        
        # Разбиваем на батчи для прогресса
        total = len(entries)
        documents: List[Documentation] = []
        seen_ids: set = set()  # Для дедупликации
        
        logger.info(f"Запуск параллельного парсинга {total} файлов (лимит: {PARALLEL_PARSE_LIMIT})")
        
        # Создаем задачи
        tasks = [
            self._parse_single_html(entry, semaphore)
            for entry in entries
        ]
        
        # Выполняем с прогрессом и дедупликацией
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            try:
                doc = await coro
                if doc:
                    # Дедупликация по ID документа
                    if doc.id not in seen_ids:
                        seen_ids.add(doc.id)
                        documents.append(doc)
            except asyncio.CancelledError:
                logger.info("Парсинг отменен пользователем")
                raise
            except Exception as e:
                logger.debug(f"Ошибка парсинга файла (пропускаем): {e}")
            
            # Лог прогресса каждые 1000 файлов
            if i % 1000 == 0:
                logger.info(f"Прогресс: {i}/{total} файлов, найдено документов: {len(documents)}")
        
        return documents
    
    async def _parse_single_html(self, entry: HBKEntry, semaphore: asyncio.Semaphore) -> Optional[Documentation]:
        """Парсит один HTML файл с кэшированием."""
        async with semaphore:
            try:
                # Проверка кэша
                cached = self._doc_cache.get(entry.path)
                if cached:
                    return cached
                
                # Извлечение содержимого
                if entry.content:
                    content = entry.content
                elif self._zip_manager:
                    content = await self._zip_manager.extract_file(entry.path)
                else:
                    return None
                
                if not content:
                    return None
                
                # Парсинг
                doc = self.html_parser.parse_html_content(content, entry.path)
                
                # Кэширование
                if doc:
                    self._doc_cache.set(entry.path, doc)
                
                return doc
                
            except Exception as e:
                logger.debug(f"Ошибка парсинга {entry.path}: {e}")
                return None
    
    async def _cleanup_async(self):
        """Асинхронная очистка ресурсов."""
        if self._zip_manager:
            try:
                await self._zip_manager.close()
            except Exception as e:
                logger.warning(f"Ошибка закрытия 7zip сессии: {e}")
            finally:
                self._zip_manager = None
    
    def _parse_categories_file(self, entry: HBKEntry, result: ParsedHBK):
        """Парсит файл __categories__."""
        if not entry.content:
            return
        
        try:
            content = None
            for encoding in SUPPORTED_ENCODINGS:
                try:
                    content = entry.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not content:
                return
            
            path_parts = entry.path.replace('\\', '/').split('/')
            section_name = path_parts[-2] if len(path_parts) > 1 else "unknown"
            
            category = CategoryInfo(
                name=section_name,
                section=section_name,
                description=f"Раздел документации: {section_name}"
            )
            
            result.categories[section_name] = category
            
        except Exception as e:
            logger.warning(f"Ошибка парсинга файла категорий {entry.path}: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Получить статистику кэша документов.

        Returns:
            Dict с ключами: size, max_size, hits, misses, hit_rate
        """
        return self._doc_cache.stats

    def get_parse_status(self) -> Dict[str, Any]:
        """
        Получить статус текущего парсинга.

        Returns:
            Dict с ключами: status, progress, message
        """
        return {
            "status": self._parse_status,
            "progress": self._parse_progress,
            "message": self._parse_message
        }
