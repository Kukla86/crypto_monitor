#!/usr/bin/env python3
"""
Централизованная обработка ошибок для системы мониторинга криптовалют
"""

import asyncio
import logging
import time
import functools
from typing import Callable, Any, Optional, Dict, List, Type, Union
from contextlib import asynccontextmanager
from dataclasses import dataclass

from exceptions import (
    CryptoMonitorError, APIError, RateLimitError, NetworkError, DatabaseError,
    ConfigurationError, TokenError, SocialMediaError, AlertError, 
    DataValidationError, RetryableError, CriticalError,
    is_retryable_error, is_critical_error, is_api_error,
    get_error_context, format_error_message
)

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Конфигурация retry механизма"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class ErrorStats:
    """Статистика ошибок"""
    total_errors: int = 0
    retryable_errors: int = 0
    critical_errors: int = 0
    api_errors: int = 0
    network_errors: int = 0
    database_errors: int = 0
    last_error_time: Optional[float] = None
    error_history: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.error_history is None:
            self.error_history = []
    
    def add_error(self, error: Exception, context: Dict[str, Any] = None):
        """Добавляет ошибку в статистику"""
        self.total_errors += 1
        self.last_error_time = time.time()
        
        error_info = {
            'timestamp': self.last_error_time,
            'error_type': type(error).__name__,
            'message': str(error),
            'context': context or {}
        }
        
        if is_retryable_error(error):
            self.retryable_errors += 1
            error_info['retryable'] = True
        
        if is_critical_error(error):
            self.critical_errors += 1
            error_info['critical'] = True
        
        if is_api_error(error):
            self.api_errors += 1
            error_info['api_error'] = True
        
        if isinstance(error, NetworkError):
            self.network_errors += 1
            error_info['network_error'] = True
        
        if isinstance(error, DatabaseError):
            self.database_errors += 1
            error_info['database_error'] = True
        
        # Ограничиваем историю ошибок (последние 100)
        if len(self.error_history) >= 100:
            self.error_history.pop(0)
        
        self.error_history.append(error_info)
    
    def get_summary(self) -> Dict[str, Any]:
        """Получает сводку статистики ошибок"""
        return {
            'total_errors': self.total_errors,
            'retryable_errors': self.retryable_errors,
            'critical_errors': self.critical_errors,
            'api_errors': self.api_errors,
            'network_errors': self.network_errors,
            'database_errors': self.database_errors,
            'last_error_time': self.last_error_time,
            'recent_errors': self.error_history[-10:] if self.error_history else []
        }


class ErrorHandler:
    """Централизованный обработчик ошибок"""
    
    def __init__(self):
        self.stats = ErrorStats()
        self.fallback_strategies: Dict[str, Callable] = {}
        self.error_callbacks: Dict[Type[Exception], List[Callable]] = {}
    
    def register_fallback(self, operation_name: str, fallback_func: Callable):
        """Регистрирует fallback функцию для операции"""
        self.fallback_strategies[operation_name] = fallback_func
        logger.debug(f"Зарегистрирован fallback для операции: {operation_name}")
    
    def register_error_callback(self, error_type: Type[Exception], callback: Callable):
        """Регистрирует callback для определенного типа ошибки"""
        if error_type not in self.error_callbacks:
            self.error_callbacks[error_type] = []
        self.error_callbacks[error_type].append(callback)
        logger.debug(f"Зарегистрирован callback для ошибки: {error_type.__name__}")
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> None:
        """Обрабатывает ошибку"""
        # Добавляем в статистику
        self.stats.add_error(error, context)
        
        # Логируем ошибку
        error_message = format_error_message(error)
        error_context = get_error_context(error)
        
        if is_critical_error(error):
            logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: {error_message}")
        elif is_retryable_error(error):
            logger.warning(f"Повторяемая ошибка: {error_message}")
        else:
            logger.error(f"Ошибка: {error_message}")
        
        # Вызываем callbacks для данного типа ошибки
        error_type = type(error)
        if error_type in self.error_callbacks:
            for callback in self.error_callbacks[error_type]:
                try:
                    callback(error, context)
                except Exception as callback_error:
                    logger.error(f"Ошибка в callback для {error_type.__name__}: {callback_error}")
        
        # Вызываем callbacks для базовых типов
        for base_type, callbacks in self.error_callbacks.items():
            if base_type != error_type and isinstance(error, base_type):
                for callback in callbacks:
                    try:
                        callback(error, context)
                    except Exception as callback_error:
                        logger.error(f"Ошибка в callback для {base_type.__name__}: {callback_error}")
    
    async def execute_with_retry(self, func: Callable, *args, 
                                retry_config: Optional[RetryConfig] = None,
                                operation_name: str = None,
                                **kwargs) -> Any:
        """Выполняет функцию с retry механизмом"""
        if retry_config is None:
            retry_config = RetryConfig()
        last_error = None
        for attempt in range(retry_config.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"Операция {operation_name} успешно выполнена после {attempt} попыток")
                return result
            except Exception as error:
                last_error = error
                context = {
                    'operation_name': operation_name,
                    'attempt': attempt + 1,
                    'max_attempts': retry_config.max_retries + 1
                }
                self.handle_error(error, context)
                if not is_retryable_error(error) or attempt == retry_config.max_retries:
                    break
                delay = min(
                    retry_config.base_delay * (retry_config.exponential_base ** attempt),
                    retry_config.max_delay
                )
                if retry_config.jitter:
                    import random
                    delay *= (0.5 + random.random() * 0.5)
                logger.info(f"Повтор попытки {attempt + 1} для {operation_name} через {delay:.1f}с")
                await asyncio.sleep(delay)
        # Все попытки исчерпаны, пробуем fallback
        if operation_name and operation_name in self.fallback_strategies:
            try:
                logger.info(f"Используем fallback для операции: {operation_name}")
                fallback_result = self.fallback_strategies[operation_name](*args, **kwargs)
                if asyncio.iscoroutine(fallback_result):
                    fallback_result = await fallback_result
                return fallback_result
            except Exception as fallback_error:
                logger.error(f"Fallback для {operation_name} также не удался: {fallback_error}")
                self.handle_error(fallback_error, {'operation_name': operation_name, 'fallback': True})
        # Если fallback не помог, возвращаем дефолтное значение
        if asyncio.iscoroutinefunction(func):
            return {}
        else:
            return None
    
    @asynccontextmanager
    async def error_context(self, operation_name: str, context: Dict[str, Any] = None):
        """Контекстный менеджер для обработки ошибок"""
        try:
            yield
        except Exception as error:
            full_context = context or {}
            full_context['operation_name'] = operation_name
            self.handle_error(error, full_context)
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Получает статистику ошибок"""
        return self.stats.get_summary()
    
    def reset_stats(self):
        """Сбрасывает статистику ошибок"""
        self.stats = ErrorStats()
        logger.info("Статистика ошибок сброшена")


# Глобальный экземпляр обработчика ошибок
error_handler = ErrorHandler()


# Декораторы для удобного использования
def handle_errors(operation_name: str = None, retry_config: Optional[RetryConfig] = None):
    """Декоратор для обработки ошибок"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await error_handler.execute_with_retry(
                func, *args, retry_config=retry_config, 
                operation_name=operation_name or func.__name__, **kwargs
            )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return error_handler.execute_with_retry(
                func, *args, retry_config=retry_config,
                operation_name=operation_name or func.__name__, **kwargs
            )
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def with_fallback(fallback_func: Callable):
    """Декоратор для добавления fallback функции"""
    def decorator(func):
        operation_name = func.__name__
        error_handler.register_fallback(operation_name, fallback_func)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return error_handler.execute_with_retry(
                func, *args, operation_name=operation_name, **kwargs
            )
        
        return wrapper
    return decorator


def on_error(error_type: Type[Exception]):
    """Декоратор для регистрации обработчика ошибок"""
    def decorator(callback: Callable):
        error_handler.register_error_callback(error_type, callback)
        return callback
    return decorator


# Специализированные обработчики для разных типов операций
class APIErrorHandler:
    """Специализированный обработчик для API операций"""
    
    def __init__(self, api_name: str, retry_config: Optional[RetryConfig] = None):
        self.api_name = api_name
        self.retry_config = retry_config or RetryConfig(max_retries=2, base_delay=2.0)
    
    async def execute_api_call(self, func: Callable, *args, **kwargs) -> Any:
        """Выполняет API вызов с обработкой ошибок"""
        operation_name = f"{self.api_name}_api_call"
        
        try:
            return await error_handler.execute_with_retry(
                func, *args, retry_config=self.retry_config,
                operation_name=operation_name, **kwargs
            )
        except RateLimitError as e:
            # Специальная обработка rate limit ошибок
            retry_after = e.context.get('retry_after', 60)
            logger.warning(f"Rate limit для {self.api_name}, ожидание {retry_after}с")
            await asyncio.sleep(retry_after)
            # Повторяем попытку
            return await error_handler.execute_with_retry(
                func, *args, retry_config=self.retry_config,
                operation_name=operation_name, **kwargs
            )


class DatabaseErrorHandler:
    """Специализированный обработчик для операций с БД"""
    
    def __init__(self, retry_config: Optional[RetryConfig] = None):
        self.retry_config = retry_config or RetryConfig(max_retries=3, base_delay=1.0)
    
    async def execute_db_operation(self, operation: str, func: Callable, *args, **kwargs) -> Any:
        """Выполняет операцию с БД с обработкой ошибок"""
        operation_name = f"db_{operation}"
        
        return await error_handler.execute_with_retry(
            func, *args, retry_config=self.retry_config,
            operation_name=operation_name, **kwargs
        )


# Функции для создания специализированных обработчиков
def create_api_handler(api_name: str, retry_config: Optional[RetryConfig] = None) -> APIErrorHandler:
    """Создает обработчик для API"""
    return APIErrorHandler(api_name, retry_config)


def create_db_handler(retry_config: Optional[RetryConfig] = None) -> DatabaseErrorHandler:
    """Создает обработчик для БД"""
    return DatabaseErrorHandler(retry_config)


# Утилиты для работы с ошибками
def log_error_with_context(error: Exception, context: Dict[str, Any] = None, level: str = 'error'):
    """Логирует ошибку с контекстом"""
    error_message = format_error_message(error)
    context_str = f" | Context: {context}" if context else ""
    
    log_func = getattr(logger, level.lower(), logger.error)
    log_func(f"{error_message}{context_str}")


def create_error_report() -> Dict[str, Any]:
    """Создает отчет об ошибках"""
    stats = error_handler.get_stats()
    
    report = {
        'timestamp': time.time(),
        'stats': stats,
        'recommendations': []
    }
    
    # Анализируем статистику и даем рекомендации
    if stats['critical_errors'] > 0:
        report['recommendations'].append({
            'type': 'critical',
            'message': f"Обнаружено {stats['critical_errors']} критических ошибок. Требуется немедленное внимание."
        })
    
    if stats['api_errors'] > stats['total_errors'] * 0.5:
        report['recommendations'].append({
            'type': 'api',
            'message': "Высокий процент API ошибок. Проверьте API ключи и лимиты."
        })
    
    if stats['network_errors'] > stats['total_errors'] * 0.3:
        report['recommendations'].append({
            'type': 'network',
            'message': "Много сетевых ошибок. Проверьте интернет соединение."
        })
    
    return report 