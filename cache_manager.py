#!/usr/bin/env python3
"""
Менеджер кэширования для системы мониторинга криптовалют
Поддерживает TTLCache, LRUCache и декораторы для кэширования
"""

import time
import hashlib
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Union, Callable, TypeVar, ParamSpec
from functools import wraps
from datetime import datetime, timedelta
from collections import OrderedDict
import threading
from dataclasses import dataclass, asdict
import pickle

logger = logging.getLogger(__name__)

T = TypeVar('T')
P = ParamSpec('P')

@dataclass
class CacheEntry:
    """Запись в кэше"""
    value: Any
    timestamp: float
    ttl: int
    access_count: int = 0
    last_access: float = 0.0

class TTLCache:
    """Кэш с временем жизни (Time To Live)"""
    
    def __init__(self, maxsize: int = 1000, default_ttl: int = 300):
        """
        Инициализация TTLCache
        
        Args:
            maxsize: Максимальное количество записей
            default_ttl: Время жизни записи по умолчанию (в секундах)
        """
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = 60  # секунды
        self._last_cleanup = time.time()
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Генерация ключа кэша из аргументов"""
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Получение значения из кэша
        
        Args:
            key: Ключ кэша
            default: Значение по умолчанию
            
        Returns:
            Значение из кэша или default
        """
        with self._lock:
            self._cleanup_expired()
            
            if key not in self._cache:
                return default
            
            entry = self._cache[key]
            
            # Проверяем, не истекло ли время жизни
            if time.time() - entry.timestamp > entry.ttl:
                del self._cache[key]
                return default
            
            # Обновляем статистику доступа
            entry.access_count += 1
            entry.last_access = time.time()
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Установка значения в кэш
        
        Args:
            key: Ключ кэша
            value: Значение для кэширования
            ttl: Время жизни записи (в секундах)
        """
        with self._lock:
            self._cleanup_expired()
            
            # Если кэш переполнен, удаляем самую старую запись
            if len(self._cache) >= self.maxsize:
                oldest_key = min(self._cache.keys(), 
                               key=lambda k: self._cache[k].timestamp)
                del self._cache[oldest_key]
            
            ttl = ttl or self.default_ttl
            entry = CacheEntry(
                value=value,
                timestamp=time.time(),
                ttl=ttl
            )
            
            self._cache[key] = entry
    
    def delete(self, key: str) -> bool:
        """
        Удаление записи из кэша
        
        Args:
            key: Ключ для удаления
            
        Returns:
            True если запись была удалена, False если не найдена
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Очистка всего кэша"""
        with self._lock:
            self._cache.clear()
    
    def _cleanup_expired(self) -> None:
        """Удаление истекших записей"""
        current_time = time.time()
        
        # Проверяем, нужно ли выполнить очистку
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
        
        expired_keys = []
        for key, entry in self._cache.items():
            if current_time - entry.timestamp > entry.ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug(f"Удалено {len(expired_keys)} истекших записей из кэша")
        
        self._last_cleanup = current_time
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша"""
        with self._lock:
            current_time = time.time()
            total_entries = len(self._cache)
            expired_entries = sum(1 for entry in self._cache.values() 
                                if current_time - entry.timestamp > entry.ttl)
            
            return {
                'total_entries': total_entries,
                'expired_entries': expired_entries,
                'maxsize': self.maxsize,
                'usage_percent': (total_entries / self.maxsize) * 100 if self.maxsize > 0 else 0
            }

class LRUCache:
    """Кэш с политикой вытеснения LRU (Least Recently Used)"""
    
    def __init__(self, maxsize: int = 1000):
        """
        Инициализация LRUCache
        
        Args:
            maxsize: Максимальное количество записей
        """
        self.maxsize = maxsize
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Получение значения из кэша
        
        Args:
            key: Ключ кэша
            default: Значение по умолчанию
            
        Returns:
            Значение из кэша или default
        """
        with self._lock:
            if key not in self._cache:
                return default
            
            # Перемещаем запись в конец (самая недавно использованная)
            entry = self._cache.pop(key)
            self._cache[key] = entry
            
            # Обновляем статистику доступа
            entry.access_count += 1
            entry.last_access = time.time()
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Установка значения в кэш
        
        Args:
            key: Ключ кэша
            value: Значение для кэширования
            ttl: Время жизни записи (в секундах)
        """
        with self._lock:
            # Если ключ уже существует, удаляем старую запись
            if key in self._cache:
                del self._cache[key]
            
            # Если кэш переполнен, удаляем самую старую запись
            if len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)
            
            ttl = ttl or 300  # 5 минут по умолчанию
            entry = CacheEntry(
                value=value,
                timestamp=time.time(),
                ttl=ttl
            )
            
            self._cache[key] = entry
    
    def delete(self, key: str) -> bool:
        """
        Удаление записи из кэша
        
        Args:
            key: Ключ для удаления
            
        Returns:
            True если запись была удалена, False если не найдена
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Очистка всего кэша"""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша"""
        with self._lock:
            return {
                'total_entries': len(self._cache),
                'maxsize': self.maxsize,
                'usage_percent': (len(self._cache) / self.maxsize) * 100 if self.maxsize > 0 else 0
            }

class CacheManager:
    """Менеджер кэширования с поддержкой разных типов кэшей"""
    
    def __init__(self):
        """Инициализация менеджера кэширования"""
        self._caches: Dict[str, Union[TTLCache, LRUCache]] = {}
        self._lock = threading.RLock()
        
        # Создаем кэши по умолчанию
        self._create_default_caches()
    
    def _create_default_caches(self):
        """Создание кэшей по умолчанию"""
        # Кэш для цен (короткое время жизни)
        self.add_cache('price_data', 'ttl', maxsize=1000, default_ttl=60)
        
        # Кэш для объемов (среднее время жизни)
        self.add_cache('volume_data', 'ttl', maxsize=500, default_ttl=300)
        
        # Кэш для социальных данных (долгое время жизни)
        self.add_cache('social_data', 'ttl', maxsize=200, default_ttl=900)
        
        # Кэш для новостей (очень долгое время жизни)
        self.add_cache('news_data', 'ttl', maxsize=100, default_ttl=1800)
        
        # LRU кэш для аналитических данных
        self.add_cache('analytics_data', 'lru', maxsize=300)
        
        # LRU кэш для результатов API запросов
        self.add_cache('api_results', 'lru', maxsize=500)
    
    def add_cache(self, name: str, cache_type: str, **kwargs) -> None:
        """
        Добавление нового кэша
        
        Args:
            name: Имя кэша
            cache_type: Тип кэша ('ttl' или 'lru')
            **kwargs: Параметры для создания кэша
        """
        with self._lock:
            if cache_type == 'ttl':
                cache = TTLCache(**kwargs)
            elif cache_type == 'lru':
                cache = LRUCache(**kwargs)
            else:
                raise ValueError(f"Неизвестный тип кэша: {cache_type}")
            
            self._caches[name] = cache
            logger.info(f"Создан кэш '{name}' типа {cache_type}")
    
    def get_cache(self, name: str) -> Optional[Union[TTLCache, LRUCache]]:
        """
        Получение кэша по имени
        
        Args:
            name: Имя кэша
            
        Returns:
            Кэш или None если не найден
        """
        return self._caches.get(name)
    
    def get(self, cache_name: str, key: str, default: Any = None) -> Any:
        """
        Получение значения из кэша
        
        Args:
            cache_name: Имя кэша
            key: Ключ
            default: Значение по умолчанию
            
        Returns:
            Значение из кэша или default
        """
        cache = self.get_cache(cache_name)
        if cache is None:
            return default
        
        return cache.get(key, default)
    
    def set(self, cache_name: str, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Установка значения в кэш
        
        Args:
            cache_name: Имя кэша
            key: Ключ
            value: Значение
            ttl: Время жизни (только для TTLCache)
        """
        cache = self.get_cache(cache_name)
        if cache is None:
            logger.warning(f"Кэш '{cache_name}' не найден")
            return
        
        if isinstance(cache, TTLCache):
            cache.set(key, value, ttl)
        else:
            cache.set(key, value)
    
    def delete(self, cache_name: str, key: str) -> bool:
        """
        Удаление записи из кэша
        
        Args:
            cache_name: Имя кэша
            key: Ключ для удаления
            
        Returns:
            True если запись была удалена
        """
        cache = self.get_cache(cache_name)
        if cache is None:
            return False
        
        return cache.delete(key)
    
    def clear_cache(self, cache_name: str) -> None:
        """
        Очистка кэша
        
        Args:
            cache_name: Имя кэша для очистки
        """
        cache = self.get_cache(cache_name)
        if cache:
            cache.clear()
            logger.info(f"Кэш '{cache_name}' очищен")
    
    def clear_all(self) -> None:
        """Очистка всех кэшей"""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()
            logger.info("Все кэши очищены")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики всех кэшей"""
        stats = {}
        with self._lock:
            for name, cache in self._caches.items():
                stats[name] = cache.get_stats()
        return stats
    
    def get_cache_names(self) -> List[str]:
        """Получение списка имен кэшей"""
        return list(self._caches.keys())

def cache_result(cache_name: str, ttl: Optional[int] = None, key_prefix: str = ""):
    """
    Декоратор для кэширования результатов функций
    
    Args:
        cache_name: Имя кэша для использования
        ttl: Время жизни записи (только для TTLCache)
        key_prefix: Префикс для ключа кэша
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Получаем менеджер кэширования
            cache_manager = get_cache_manager()
            
            # Генерируем ключ кэша
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Пытаемся получить результат из кэша
            cached_result = cache_manager.get(cache_name, cache_key)
            if cached_result is not None:
                logger.debug(f"Результат получен из кэша '{cache_name}' для {func.__name__}")
                return cached_result
            
            # Выполняем функцию
            result = func(*args, **kwargs)
            
            # Сохраняем результат в кэш
            cache_manager.set(cache_name, cache_key, result, ttl)
            logger.debug(f"Результат сохранен в кэш '{cache_name}' для {func.__name__}")
            
            return result
        
        return wrapper
    return decorator

def async_cache_result(cache_name: str, ttl: Optional[int] = None, key_prefix: str = ""):
    """
    Декоратор для кэширования результатов асинхронных функций
    
    Args:
        cache_name: Имя кэша для использования
        ttl: Время жизни записи (только для TTLCache)
        key_prefix: Префикс для ключа кэша
    """
    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            # Получаем менеджер кэширования
            cache_manager = get_cache_manager()
            
            # Генерируем ключ кэша
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Пытаемся получить результат из кэша
            cached_result = cache_manager.get(cache_name, cache_key)
            if cached_result is not None:
                logger.debug(f"Результат получен из кэша '{cache_name}' для {func.__name__}")
                return cached_result
            
            # Выполняем асинхронную функцию
            result = await func(*args, **kwargs)
            
            # Сохраняем результат в кэш
            cache_manager.set(cache_name, cache_key, result, ttl)
            logger.debug(f"Результат сохранен в кэш '{cache_name}' для {func.__name__}")
            
            return result
        
        return wrapper
    return decorator

def cache_method_result(cache_name: str, ttl: Optional[int] = None, key_prefix: str = ""):
    """
    Декоратор для кэширования результатов методов класса
    
    Args:
        cache_name: Имя кэша для использования
        ttl: Время жизни записи (только для TTLCache)
        key_prefix: Префикс для ключа кэша
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(self, *args: P.args, **kwargs: P.kwargs) -> T:
            # Получаем менеджер кэширования
            cache_manager = get_cache_manager()
            
            # Генерируем ключ кэша с учетом self
            cache_key = f"{key_prefix}:{self.__class__.__name__}.{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Пытаемся получить результат из кэша
            cached_result = cache_manager.get(cache_name, cache_key)
            if cached_result is not None:
                logger.debug(f"Результат получен из кэша '{cache_name}' для {self.__class__.__name__}.{func.__name__}")
                return cached_result
            
            # Выполняем метод
            result = func(self, *args, **kwargs)
            
            # Сохраняем результат в кэш
            cache_manager.set(cache_name, cache_key, result, ttl)
            logger.debug(f"Результат сохранен в кэш '{cache_name}' для {self.__class__.__name__}.{func.__name__}")
            
            return result
        
        return wrapper
    return decorator

# Глобальный экземпляр менеджера кэширования
cache_manager = None

def get_cache_manager() -> CacheManager:
    """Получение глобального менеджера кэширования"""
    global cache_manager
    if cache_manager is None:
        cache_manager = CacheManager()
    return cache_manager

def clear_all_caches():
    """Очистка всех кэшей"""
    global cache_manager
    if cache_manager:
        cache_manager.clear_all()

def get_cache_stats() -> Dict[str, Any]:
    """Получение статистики всех кэшей"""
    global cache_manager
    if cache_manager:
        return cache_manager.get_stats() 