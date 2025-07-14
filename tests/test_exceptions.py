#!/usr/bin/env python3
"""
Тесты для модуля исключений
"""

import unittest
import sys
sys.path.append('..')

from exceptions import (
    CryptoMonitorError, APIError, RateLimitError, NetworkError, DatabaseError,
    ConfigurationError, TokenError, SocialMediaError, AlertError,
    DataValidationError, RetryableError, CriticalError,
    create_api_error, create_rate_limit_error, create_network_error,
    create_database_error, create_configuration_error, create_token_error,
    create_social_media_error, create_alert_error, create_validation_error,
    create_critical_error, is_retryable_error, is_critical_error, is_api_error,
    get_error_context, format_error_message
)


class TestExceptions(unittest.TestCase):
    """Тесты для кастомных исключений"""
    
    def test_crypto_monitor_error_basic(self):
        """Тест базового исключения"""
        error = CryptoMonitorError("Test error")
        self.assertEqual(str(error), "CryptoMonitorError: Test error")
        self.assertEqual(error.message, "Test error")
        self.assertEqual(error.context, {})
    
    def test_crypto_monitor_error_with_context(self):
        """Тест исключения с контекстом"""
        context = {'key': 'value', 'number': 42}
        error = CryptoMonitorError("Test error", context)
        self.assertIn("Context: {'key': 'value', 'number': 42}", str(error))
        self.assertEqual(error.context, context)
    
    def test_api_error(self):
        """Тест API ошибки"""
        error = APIError("API failed", "etherscan", 500, {"error": "Internal server error"})
        self.assertEqual(error.context['api_name'], "etherscan")
        self.assertEqual(error.context['status_code'], 500)
        self.assertEqual(error.context['response_data'], {"error": "Internal server error"})
    
    def test_rate_limit_error(self):
        """Тест ошибки превышения лимита"""
        error = RateLimitError("bybit", 60)
        self.assertIsInstance(error.context, dict)
        self.assertIn('api_name', error.context)
        self.assertIn('api_name', error.context['api_name'])
        self.assertEqual(error.context['api_name']['api_name'], "bybit")
        self.assertIn('retry_after', error.context['api_name'])
        self.assertEqual(error.context['api_name']['retry_after'], 60)
        self.assertEqual(error.context['api_name']['error_type'], "rate_limit")
        self.assertIn("retry after 60 seconds", str(error))
    
    def test_network_error(self):
        """Тест сетевой ошибки"""
        error = NetworkError("Connection failed", "https://api.example.com", 10.0)
        self.assertEqual(error.context['url'], "https://api.example.com")
        self.assertEqual(error.context['timeout'], 10.0)
        self.assertEqual(error.context['error_type'], "network")
    
    def test_database_error(self):
        """Тест ошибки базы данных"""
        error = DatabaseError("Query failed", "SELECT", "tokens")
        self.assertEqual(error.context['operation'], "SELECT")
        self.assertEqual(error.context['table'], "tokens")
        self.assertEqual(error.context['error_type'], "database")
    
    def test_configuration_error(self):
        """Тест ошибки конфигурации"""
        error = ConfigurationError("Invalid config", "API_KEY", "string")
        self.assertEqual(error.context['config_key'], "API_KEY")
        self.assertEqual(error.context['expected_type'], "string")
        self.assertEqual(error.context['error_type'], "configuration")
    
    def test_token_error(self):
        """Тест ошибки токена"""
        error = TokenError("Token not found", "FUEL", "ethereum")
        self.assertEqual(error.context['token_symbol'], "FUEL")
        self.assertEqual(error.context['chain'], "ethereum")
        self.assertEqual(error.context['error_type'], "token")
    
    def test_social_media_error(self):
        """Тест ошибки социальных сетей"""
        error = SocialMediaError("Twitter API failed", "twitter", "@example")
        self.assertEqual(error.context['platform'], "twitter")
        self.assertEqual(error.context['account'], "@example")
        self.assertEqual(error.context['error_type'], "social_media")
    
    def test_alert_error(self):
        """Тест ошибки алерта"""
        error = AlertError("Failed to send", "telegram", "chat_id")
        self.assertEqual(error.context['alert_type'], "telegram")
        self.assertEqual(error.context['recipient'], "chat_id")
        self.assertEqual(error.context['error_type'], "alert")
    
    def test_validation_error(self):
        """Тест ошибки валидации"""
        error = DataValidationError("Invalid price", "price_data", "price", -100)
        self.assertEqual(error.context['data_type'], "price_data")
        self.assertEqual(error.context['field'], "price")
        self.assertEqual(error.context['value'], -100)
        self.assertEqual(error.context['error_type'], "validation")
    
    def test_retryable_error(self):
        """Тест повторяемой ошибки"""
        error = RetryableError("Temporary failure", 3, 2.0)
        self.assertEqual(error.context['max_retries'], 3)
        self.assertEqual(error.context['retry_delay'], 2.0)
        self.assertEqual(error.context['error_type'], "retryable")
    
    def test_critical_error(self):
        """Тест критической ошибки"""
        error = CriticalError("System failure", "database", "critical")
        self.assertEqual(error.context['component'], "database")
        self.assertEqual(error.context['severity'], "critical")
        self.assertEqual(error.context['error_type'], "critical")


class TestErrorCreationFunctions(unittest.TestCase):
    """Тесты для функций создания исключений"""
    
    def test_create_api_error(self):
        """Тест создания API ошибки"""
        error = create_api_error("etherscan", 429, {"error": "Rate limit exceeded"})
        self.assertIsInstance(error, APIError)
        self.assertEqual(error.context['api_name'], "etherscan")
        self.assertEqual(error.context['status_code'], 429)
        self.assertIn("Rate limit exceeded", str(error))
    
    def test_create_rate_limit_error(self):
        """Тест создания ошибки превышения лимита"""
        error = create_rate_limit_error("bybit", 30)
        self.assertIsInstance(error, RateLimitError)
        self.assertIn('api_name', error.context)
        self.assertIn('api_name', error.context['api_name'])
        self.assertEqual(error.context['api_name']['api_name'], "bybit")
        self.assertIn('retry_after', error.context['api_name'])
        self.assertEqual(error.context['api_name']['retry_after'], 30)
    
    def test_create_network_error(self):
        """Тест создания сетевой ошибки"""
        original_error = ConnectionError("Connection refused")
        error = create_network_error("https://api.example.com", 5.0, original_error)
        self.assertIsInstance(error, NetworkError)
        self.assertEqual(error.context['url'], "https://api.example.com")
        self.assertEqual(error.context['timeout'], 5.0)
        self.assertIn("Connection refused", str(error))
    
    def test_create_database_error(self):
        """Тест создания ошибки БД"""
        original_error = Exception("SQL syntax error")
        error = create_database_error("INSERT", "tokens", original_error)
        self.assertIsInstance(error, DatabaseError)
        self.assertEqual(error.context['operation'], "INSERT")
        self.assertEqual(error.context['table'], "tokens")
        self.assertIn("SQL syntax error", str(error))
    
    def test_create_configuration_error(self):
        """Тест создания ошибки конфигурации"""
        error = create_configuration_error("API_KEY", "string", 123)
        self.assertIsInstance(error, ConfigurationError)
        self.assertEqual(error.context['config_key'], "API_KEY")
        self.assertEqual(error.context['expected_type'], "string")
        self.assertIn("expected string, got int", str(error))
    
    def test_create_token_error(self):
        """Тест создания ошибки токена"""
        error = create_token_error("FUEL", "Token not found", "ethereum")
        self.assertIsInstance(error, TokenError)
        self.assertEqual(error.context['token_symbol'], "FUEL")
        self.assertEqual(error.context['chain'], "ethereum")
    
    def test_create_social_media_error(self):
        """Тест создания ошибки социальных сетей"""
        error = create_social_media_error("twitter", "API failed", "@example")
        self.assertIsInstance(error, SocialMediaError)
        self.assertEqual(error.context['platform'], "twitter")
        self.assertEqual(error.context['account'], "@example")
    
    def test_create_alert_error(self):
        """Тест создания ошибки алерта"""
        error = create_alert_error("telegram", "Failed to send", "chat_id")
        self.assertIsInstance(error, AlertError)
        self.assertEqual(error.context['alert_type'], "telegram")
        self.assertEqual(error.context['recipient'], "chat_id")
    
    def test_create_validation_error(self):
        """Тест создания ошибки валидации"""
        error = create_validation_error("price_data", "price", -100, "positive number")
        self.assertIsInstance(error, DataValidationError)
        self.assertEqual(error.context['data_type'], "price_data")
        self.assertEqual(error.context['field'], "price")
        self.assertEqual(error.context['value'], -100)
        self.assertIn("expected format: positive number", str(error))
    
    def test_create_critical_error(self):
        """Тест создания критической ошибки"""
        error = create_critical_error("database", "System failure", "critical")
        self.assertIsInstance(error, CriticalError)
        self.assertEqual(error.context['component'], "database")
        self.assertEqual(error.context['severity'], "critical")


class TestErrorUtilityFunctions(unittest.TestCase):
    """Тесты для утилитарных функций"""
    
    def test_is_retryable_error(self):
        """Тест проверки повторяемых ошибок"""
        retryable_error = RetryableError("Temporary failure")
        network_error = NetworkError("Connection failed", "https://example.com")
        rate_limit_error = RateLimitError("bybit")
        api_error = APIError("API failed", "etherscan")
        critical_error = CriticalError("System failure", "database")
        
        self.assertTrue(is_retryable_error(retryable_error))
        self.assertTrue(is_retryable_error(network_error))
        self.assertTrue(is_retryable_error(rate_limit_error))
        self.assertFalse(is_retryable_error(api_error))
        self.assertFalse(is_retryable_error(critical_error))
    
    def test_is_critical_error(self):
        """Тест проверки критических ошибок"""
        critical_error = CriticalError("System failure", "database")
        regular_error = APIError("API failed", "etherscan")
        
        self.assertTrue(is_critical_error(critical_error))
        self.assertFalse(is_critical_error(regular_error))
    
    def test_is_api_error(self):
        """Тест проверки API ошибок"""
        api_error = APIError("API failed", "etherscan")
        rate_limit_error = RateLimitError("bybit")
        network_error = NetworkError("Connection failed", "https://example.com")
        
        self.assertTrue(is_api_error(api_error))
        self.assertTrue(is_api_error(rate_limit_error))
        self.assertFalse(is_api_error(network_error))
    
    def test_get_error_context(self):
        """Тест получения контекста ошибки"""
        # Кастомная ошибка
        custom_error = APIError("API failed", "etherscan", 500)
        context = get_error_context(custom_error)
        self.assertEqual(context['api_name'], "etherscan")
        self.assertEqual(context['status_code'], 500)
        
        # Стандартная ошибка
        standard_error = ValueError("Invalid value")
        context = get_error_context(standard_error)
        self.assertEqual(context['error_type'], "ValueError")
        self.assertEqual(context['message'], "Invalid value")
    
    def test_format_error_message(self):
        """Тест форматирования сообщения об ошибке"""
        # Кастомная ошибка с контекстом
        error = APIError("API failed", "etherscan", 500, {"error": "Server error"})
        message = format_error_message(error)
        self.assertIn("APIError: API failed", message)
        self.assertIn("api_name=etherscan", message)
        self.assertIn("status_code=500", message)
        
        # Стандартная ошибка
        error = ValueError("Invalid value")
        message = format_error_message(error)
        self.assertEqual(message, "ValueError: Invalid value")


class TestErrorInheritance(unittest.TestCase):
    """Тесты наследования исключений"""
    
    def test_inheritance_hierarchy(self):
        """Тест иерархии наследования"""
        # Проверяем, что все кастомные ошибки наследуются от CryptoMonitorError
        errors = [
            APIError("test", "api"),
            RateLimitError("api"),
            NetworkError("test", "url"),
            DatabaseError("test", "operation"),
            ConfigurationError("test"),
            TokenError("test", "FUEL"),
            SocialMediaError("test", "twitter"),
            AlertError("test", "telegram"),
            DataValidationError("test", "type", "field"),
            RetryableError("test"),
            CriticalError("test", "component")
        ]
        
        for error in errors:
            self.assertIsInstance(error, CryptoMonitorError)
    
    def test_rate_limit_inheritance(self):
        """Тест наследования RateLimitError от APIError"""
        error = RateLimitError("api")
        self.assertIsInstance(error, APIError)
        self.assertIsInstance(error, CryptoMonitorError)


if __name__ == '__main__':
    unittest.main() 