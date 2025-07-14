#!/usr/bin/env python3
"""
Тесты для модуля обработки ошибок
"""

import unittest
import asyncio
import time
import sys
sys.path.append('..')

from error_handler import (
    ErrorHandler, RetryConfig, ErrorStats, handle_errors, with_fallback,
    on_error, APIErrorHandler, DatabaseErrorHandler, create_api_handler,
    create_db_handler, log_error_with_context, create_error_report,
    error_handler
)
from exceptions import (
    APIError, RateLimitError, NetworkError, DatabaseError, CriticalError,
    RetryableError, create_api_error, create_network_error
)


class TestErrorStats(unittest.TestCase):
    """Тесты для статистики ошибок"""
    
    def setUp(self):
        self.stats = ErrorStats()
    
    def test_add_error_basic(self):
        """Тест добавления ошибки"""
        error = APIError("Test error", "etherscan")
        self.stats.add_error(error)
        
        self.assertEqual(self.stats.total_errors, 1)
        self.assertEqual(self.stats.api_errors, 1)
        self.assertIsNotNone(self.stats.last_error_time)
        self.assertEqual(len(self.stats.error_history), 1)
    
    def test_add_retryable_error(self):
        """Тест добавления повторяемой ошибки"""
        error = NetworkError("Connection failed", "https://example.com")
        self.stats.add_error(error)
        
        self.assertEqual(self.stats.total_errors, 1)
        self.assertEqual(self.stats.retryable_errors, 1)
        self.assertEqual(self.stats.network_errors, 1)
    
    def test_add_critical_error(self):
        """Тест добавления критической ошибки"""
        error = CriticalError("System failure", "database")
        self.stats.add_error(error)
        
        self.assertEqual(self.stats.total_errors, 1)
        self.assertEqual(self.stats.critical_errors, 1)
    
    def test_error_history_limit(self):
        """Тест ограничения истории ошибок"""
        # Добавляем 110 ошибок (больше лимита в 100)
        for i in range(110):
            error = APIError(f"Error {i}", "etherscan")
            self.stats.add_error(error)
        
        self.assertEqual(self.stats.total_errors, 110)
        self.assertEqual(len(self.stats.error_history), 100)  # Ограничено 100
        # Проверяем, что последние ошибки сохранены
        self.assertEqual(self.stats.error_history[-1]['message'], "Error 109")
    
    def test_get_summary(self):
        """Тест получения сводки"""
        # Добавляем разные типы ошибок
        self.stats.add_error(APIError("API error", "etherscan"))
        self.stats.add_error(NetworkError("Network error", "https://example.com"))
        self.stats.add_error(CriticalError("Critical error", "database"))
        
        summary = self.stats.get_summary()
        
        self.assertEqual(summary['total_errors'], 3)
        self.assertEqual(summary['api_errors'], 1)
        self.assertEqual(summary['network_errors'], 1)
        self.assertEqual(summary['critical_errors'], 1)
        self.assertEqual(summary['retryable_errors'], 1)
        self.assertIsNotNone(summary['last_error_time'])
        self.assertEqual(len(summary['recent_errors']), 3)


class TestErrorHandler(unittest.TestCase):
    """Тесты для обработчика ошибок"""
    
    def setUp(self):
        self.handler = ErrorHandler()
    
    def test_register_fallback(self):
        """Тест регистрации fallback функции"""
        def fallback_func(*args, **kwargs):
            return "fallback result"
        
        self.handler.register_fallback("test_operation", fallback_func)
        self.assertIn("test_operation", self.handler.fallback_strategies)
    
    def test_register_error_callback(self):
        """Тест регистрации callback для ошибок"""
        def callback(error, context):
            pass
        
        self.handler.register_error_callback(APIError, callback)
        self.assertIn(APIError, self.handler.error_callbacks)
        self.assertEqual(len(self.handler.error_callbacks[APIError]), 1)
    
    def test_handle_error(self):
        """Тест обработки ошибки"""
        error = APIError("Test error", "etherscan")
        context = {'operation': 'test'}
        
        self.handler.handle_error(error, context)
        
        self.assertEqual(self.handler.stats.total_errors, 1)
        self.assertEqual(self.handler.stats.api_errors, 1)
    
    def test_handle_error_with_callback(self):
        """Тест обработки ошибки с callback"""
        callback_called = False
        callback_error = None
        callback_context = None
        
        def callback(error, context):
            nonlocal callback_called, callback_error, callback_context
            callback_called = True
            callback_error = error
            callback_context = context
        
        self.handler.register_error_callback(APIError, callback)
        
        error = APIError("Test error", "etherscan")
        context = {'operation': 'test'}
        
        self.handler.handle_error(error, context)
        
        self.assertTrue(callback_called)
        self.assertEqual(callback_error, error)
        self.assertEqual(callback_context, context)


class TestRetryMechanism(unittest.TestCase):
    """Тесты для retry механизма"""
    
    def setUp(self):
        self.handler = ErrorHandler()
    
    async def test_successful_execution(self):
        """Тест успешного выполнения"""
        async def test_func():
            return "success"
        
        result = await self.handler.execute_with_retry(test_func)
        self.assertEqual(result, "success")
    
    async def test_retry_on_retryable_error(self):
        """Тест повторения при повторяемой ошибке"""
        attempt_count = 0
        
        async def test_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise NetworkError("Connection failed", "https://example.com")
            return "success"
        
        result = await self.handler.execute_with_retry(test_func)
        self.assertEqual(result, "success")
        self.assertEqual(attempt_count, 3)
    
    async def test_no_retry_on_non_retryable_error(self):
        """Тест отсутствия повторения при неповторяемой ошибке"""
        attempt_count = 0
        
        async def test_func():
            nonlocal attempt_count
            attempt_count += 1
            raise CriticalError("System failure", "database")
        
        with self.assertRaises(CriticalError):
            await self.handler.execute_with_retry(test_func)
        
        self.assertEqual(attempt_count, 1)  # Только одна попытка
    
    async def test_fallback_strategy(self):
        """Тест fallback стратегии"""
        def fallback_func(*args, **kwargs):
            return "fallback result"
        
        self.handler.register_fallback("test_operation", fallback_func)
        
        async def test_func():
            raise CriticalError("System failure", "database")
        
        result = await self.handler.execute_with_retry(
            test_func, operation_name="test_operation"
        )
        self.assertEqual(result, "fallback result")
    
    async def test_retry_config(self):
        """Тест конфигурации retry"""
        retry_config = RetryConfig(max_retries=1, base_delay=0.1)
        attempt_count = 0
        
        async def test_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise NetworkError("Connection failed", "https://example.com")
            return "success"
        
        start_time = time.time()
        result = await self.handler.execute_with_retry(
            test_func, retry_config=retry_config
        )
        end_time = time.time()
        
        self.assertEqual(result, "success")
        self.assertEqual(attempt_count, 2)
        # Проверяем, что была задержка
        self.assertGreater(end_time - start_time, 0.05)


class TestDecorators(unittest.TestCase):
    """Тесты для декораторов"""
    
    def setUp(self):
        self.handler = ErrorHandler()
    
    async def test_handle_errors_decorator(self):
        """Тест декоратора handle_errors"""
        @handle_errors("test_operation")
        async def test_func():
            raise NetworkError("Connection failed", "https://example.com")
        
        with self.assertRaises(NetworkError):
            await test_func()
        
        # Проверяем, что ошибка была обработана
        self.assertEqual(self.handler.stats.total_errors, 1)
    
    def test_with_fallback_decorator(self):
        """Тест декоратора with_fallback"""
        def fallback_func(*args, **kwargs):
            return "fallback"
        
        @with_fallback(fallback_func)
        async def test_func():
            raise CriticalError("System failure", "database")
        
        # Проверяем, что fallback зарегистрирован
        self.assertIn("test_func", self.handler.fallback_strategies)
    
    def test_on_error_decorator(self):
        """Тест декоратора on_error"""
        callback_called = False
        
        @on_error(APIError)
        def callback(error, context):
            nonlocal callback_called
            callback_called = True
        
        # Проверяем, что callback зарегистрирован
        self.assertIn(APIError, self.handler.error_callbacks)
        self.assertEqual(len(self.handler.error_callbacks[APIError]), 1)


class TestSpecializedHandlers(unittest.TestCase):
    """Тесты для специализированных обработчиков"""
    
    async def test_api_error_handler(self):
        """Тест API обработчика ошибок"""
        handler = APIErrorHandler("etherscan")
        
        async def api_call():
            raise create_api_error("etherscan", 429)
        
        with self.assertRaises(APIError):
            await handler.execute_api_call(api_call)
    
    async def test_database_error_handler(self):
        """Тест обработчика ошибок БД"""
        handler = DatabaseErrorHandler()
        
        async def db_operation():
            raise DatabaseError("Query failed", "SELECT")
        
        with self.assertRaises(DatabaseError):
            await handler.execute_db_operation("SELECT", db_operation)
    
    def test_create_handlers(self):
        """Тест создания обработчиков"""
        api_handler = create_api_handler("bybit")
        self.assertIsInstance(api_handler, APIErrorHandler)
        self.assertEqual(api_handler.api_name, "bybit")
        
        db_handler = create_db_handler()
        self.assertIsInstance(db_handler, DatabaseErrorHandler)


class TestUtilityFunctions(unittest.TestCase):
    """Тесты для утилитарных функций"""
    
    def test_log_error_with_context(self):
        """Тест логирования ошибки с контекстом"""
        error = APIError("Test error", "etherscan")
        context = {'operation': 'test'}
        
        # Проверяем, что функция не вызывает исключений
        try:
            log_error_with_context(error, context)
        except Exception as e:
            self.fail(f"log_error_with_context вызвал исключение: {e}")
    
    def test_create_error_report(self):
        """Тест создания отчета об ошибках"""
        # Добавляем несколько ошибок
        error_handler.stats.add_error(APIError("API error", "etherscan"))
        error_handler.stats.add_error(CriticalError("Critical error", "database"))
        
        report = create_error_report()
        
        self.assertIn('timestamp', report)
        self.assertIn('stats', report)
        self.assertIn('recommendations', report)
        self.assertIsInstance(report['recommendations'], list)


class TestErrorContextManager(unittest.TestCase):
    """Тесты для контекстного менеджера ошибок"""
    
    def setUp(self):
        self.handler = ErrorHandler()
    
    async def test_error_context_success(self):
        """Тест контекстного менеджера при успешном выполнении"""
        async with self.handler.error_context("test_operation"):
            result = "success"
        
        self.assertEqual(result, "success")
        self.assertEqual(self.handler.stats.total_errors, 0)
    
    async def test_error_context_failure(self):
        """Тест контекстного менеджера при ошибке"""
        with self.assertRaises(APIError):
            async with self.handler.error_context("test_operation"):
                raise APIError("Test error", "etherscan")
        
        self.assertEqual(self.handler.stats.total_errors, 1)
        self.assertEqual(self.handler.stats.api_errors, 1)


if __name__ == '__main__':
    unittest.main() 