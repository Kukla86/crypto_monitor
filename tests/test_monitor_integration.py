#!/usr/bin/env python3
"""
Тесты интеграции централизованной обработки ошибок в monitor.py
"""

import unittest
import sys
import asyncio
import tempfile
import os
import pytest
sys.path.append('..')

from unittest.mock import patch, MagicMock, AsyncMock
import monitor


class TestMonitorErrorHandlingIntegration(unittest.TestCase):
    """Тесты интеграции обработки ошибок в monitor.py"""
    
    def setUp(self):
        """Настройка тестов"""
        # Создаем временную БД для тестов
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        monitor.DB_PATH = self.temp_db.name
        
        # Инициализируем БД
        monitor.init_database()
    
    def tearDown(self):
        """Очистка после тестов"""
        # Удаляем временную БД
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_error_handling_imports(self):
        """Тест импорта модулей обработки ошибок"""
        # Проверяем, что модули импортируются
        self.assertTrue(hasattr(monitor, 'ERROR_HANDLING_AVAILABLE'))
        
        if monitor.ERROR_HANDLING_AVAILABLE:
            # Проверяем импорт исключений
            from exceptions import (
                CryptoMonitorError, APIError, RateLimitError, NetworkError,
                DatabaseError, ConfigurationError, TokenError, SocialMediaError,
                AlertError, DataValidationError, RetryableError, CriticalError
            )
            
            # Проверяем импорт обработчика ошибок
            from error_handler import handle_errors, ErrorHandler
            
            self.assertTrue(True)  # Если дошли сюда, значит импорты работают
        else:
            # Проверяем fallback декоратор
            self.assertTrue(hasattr(monitor, 'handle_errors'))
            self.assertTrue(callable(monitor.handle_errors))
    
    @patch('monitor.logger')
    @pytest.mark.asyncio
    async def test_handle_errors_decorator_fallback(self, mock_logger):
        """Тест fallback декоратора handle_errors"""
        @monitor.handle_errors("test_operation")
        async def test_function():
            raise ValueError("Test error")
        result = await test_function()
        self.assertEqual(result, {})
    
    @patch('monitor.logger')
    @pytest.mark.asyncio
    async def test_handle_errors_decorator_success(self, mock_logger):
        """Тест декоратора handle_errors при успешном выполнении"""
        @monitor.handle_errors("test_operation")
        async def test_function():
            return {"success": True}
        result = await test_function()
        mock_logger.error.assert_not_called()
        self.assertEqual(result, {"success": True})
    
    def test_send_alert_async_declaration(self):
        """Тест, что send_alert объявлена как async функция"""
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(monitor.send_alert))
    
    @patch('monitor.logger')
    @patch('aiohttp.ClientSession', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_send_alert_error_handling(self, mock_session, mock_logger):
        """Тест обработки ошибок в send_alert"""
        mock_post = AsyncMock()
        mock_post.__aenter__.return_value.status = 500
        mock_session.return_value.__aenter__.return_value.post.return_value = mock_post
        await monitor.send_alert("INFO", "Test message", "FUEL")
        mock_logger.error.assert_called()
    
    @patch('monitor.logger')
    @pytest.mark.asyncio
    async def test_check_onchain_error_handling(self, mock_logger):
        """Тест обработки ошибок в check_onchain"""
        mock_session = AsyncMock()
        result = await monitor.check_onchain(mock_session)
        self.assertIsInstance(result, dict)
    
    @patch('monitor.logger')
    @pytest.mark.asyncio
    async def test_check_cex_error_handling(self, mock_logger):
        """Тест обработки ошибок в check_cex"""
        mock_session = AsyncMock()
        result = await monitor.check_cex(mock_session)
        self.assertIsInstance(result, dict)
    
    @patch('monitor.logger')
    @pytest.mark.asyncio
    async def test_check_dex_error_handling(self, mock_logger):
        """Тест обработки ошибок в check_dex"""
        mock_session = AsyncMock()
        result = await monitor.check_dex(mock_session)
        self.assertIsInstance(result, dict)
    
    @patch('monitor.logger')
    @pytest.mark.asyncio
    async def test_check_social_error_handling(self, mock_logger):
        """Тест обработки ошибок в check_social"""
        result = await monitor.check_social()
        self.assertIsInstance(result, dict)
    
    @patch('monitor.logger')
    @pytest.mark.asyncio
    async def test_check_analytics_error_handling(self, mock_logger):
        """Тест обработки ошибок в check_analytics"""
        mock_session = AsyncMock()
        result = await monitor.check_analytics(mock_session)
        self.assertIsInstance(result, dict)
    
    def test_database_operations_with_context_manager(self):
        """Тест операций с БД через контекстный менеджер"""
        # Проверяем, что БД инициализирована
        self.assertTrue(os.path.exists(monitor.DB_PATH))
        
        # Тестируем сохранение данных
        test_data = {
            'price': 1.23,
            'volume_24h': 1000000,
            'market_cap': 50000000,
            'holders_count': 1000,
            'top_holders': [{'address': '0x123', 'balance': 1000}],
            'tvl': 5000000,
            'social_mentions': 50
        }
        
        # Сохраняем данные
        monitor.save_token_data("FUEL", test_data)
        
        # Проверяем, что данные сохранились
        import sqlite3
        with sqlite3.connect(monitor.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM token_data WHERE symbol = ?', ("FUEL",))
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)


if __name__ == '__main__':
    unittest.main() 