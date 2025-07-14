#!/usr/bin/env python3
"""
Тесты для модуля конфигурации
"""

import unittest
import os
import tempfile
from unittest.mock import patch
import sys
sys.path.append('..')

from config import Config, get_config, reload_config

class TestConfig(unittest.TestCase):
    """Тесты для класса Config"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        # Создаем временный .env файл
        self.temp_env = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env')
        self.env_path = self.temp_env.name
        
        # Базовые переменные окружения для тестов
        self.test_env_vars = {
            'ETHERSCAN_API_KEY': 'test_etherscan_key',
            'TELEGRAM_BOT_TOKEN': 'test_telegram_token',
            'TELEGRAM_CHAT_ID': 'test_chat_id',
            'ENVIRONMENT': 'development',
            'LOG_LEVEL': 'INFO',
            'CHECK_INTERVAL': '60',
            'PRICE_CHANGE_THRESHOLD': '10',
        }
        
        # Записываем в временный файл
        for key, value in self.test_env_vars.items():
            self.temp_env.write(f'{key}={value}\n')
        self.temp_env.close()
    
    def tearDown(self):
        """Очистка после тестов"""
        if os.path.exists(self.env_path):
            os.unlink(self.env_path)
    
    def test_config_initialization(self):
        """Тест инициализации конфигурации"""
        # Используем patch для изоляции переменных окружения
        with patch.dict(os.environ, self.test_env_vars):
            config = Config(self.env_path)
            
            # Проверяем основные настройки
            self.assertEqual(config.environment, 'development')
            self.assertEqual(config.api_config['etherscan']['api_key'], 'test_etherscan_key')
            self.assertEqual(config.api_config['telegram']['bot_token'], 'test_telegram_token')
            self.assertEqual(config.monitoring_config['check_interval'], 60)
            self.assertEqual(config.logging_config['level'], 'INFO')
    
    def test_missing_required_env_vars(self):
        """Тест обработки отсутствующих обязательных переменных"""
        # Создаем .env без обязательных переменных
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as temp_env:
            temp_env.write('ENVIRONMENT=development\n')
            temp_env.write('LOG_LEVEL=INFO\n')
            temp_env_path = temp_env.name
        
        try:
            # Очищаем переменные окружения
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError) as context:
                    Config(temp_env_path)
                
                self.assertIn('Обязательная переменная окружения', str(context.exception))
        finally:
            if os.path.exists(temp_env_path):
                os.unlink(temp_env_path)
    
    def test_invalid_log_level(self):
        """Тест валидации уровня логирования"""
        # Создаем .env с неверным уровнем логирования
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as temp_env:
            temp_env.write('ETHERSCAN_API_KEY=test_key\n')
            temp_env.write('TELEGRAM_BOT_TOKEN=test_token\n')
            temp_env.write('TELEGRAM_CHAT_ID=test_chat\n')
            temp_env.write('LOG_LEVEL=INVALID_LEVEL\n')
            temp_env_path = temp_env.name
        
        try:
            with patch.dict(os.environ, {
                'ETHERSCAN_API_KEY': 'test_key',
                'TELEGRAM_BOT_TOKEN': 'test_token',
                'TELEGRAM_CHAT_ID': 'test_chat',
                'LOG_LEVEL': 'INVALID_LEVEL'
            }):
                with self.assertRaises(ValueError) as context:
                    Config(temp_env_path)
                
                self.assertIn('Неверный уровень логирования', str(context.exception))
        finally:
            if os.path.exists(temp_env_path):
                os.unlink(temp_env_path)
    
    def test_invalid_check_interval(self):
        """Тест валидации интервала проверки"""
        # Создаем .env с неверным интервалом
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as temp_env:
            temp_env.write('ETHERSCAN_API_KEY=test_key\n')
            temp_env.write('TELEGRAM_BOT_TOKEN=test_token\n')
            temp_env.write('TELEGRAM_CHAT_ID=test_chat\n')
            temp_env.write('CHECK_INTERVAL=5\n')  # Меньше 10
            temp_env_path = temp_env.name
        
        try:
            with patch.dict(os.environ, {
                'ETHERSCAN_API_KEY': 'test_key',
                'TELEGRAM_BOT_TOKEN': 'test_token',
                'TELEGRAM_CHAT_ID': 'test_chat',
                'CHECK_INTERVAL': '5'
            }):
                with self.assertRaises(ValueError) as context:
                    Config(temp_env_path)
                
                self.assertIn('CHECK_INTERVAL должен быть не менее 10 секунд', str(context.exception))
        finally:
            if os.path.exists(temp_env_path):
                os.unlink(temp_env_path)
    
    def test_optional_openai_config(self):
        """Тест опциональной конфигурации OpenAI"""
        # Создаем .env с OpenAI ключом
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as temp_env:
            temp_env.write('ETHERSCAN_API_KEY=test_key\n')
            temp_env.write('TELEGRAM_BOT_TOKEN=test_token\n')
            temp_env.write('TELEGRAM_CHAT_ID=test_chat\n')
            temp_env.write('OPENAI_API_KEY=test_openai_key\n')
            temp_env_path = temp_env.name
        
        try:
            with patch.dict(os.environ, {
                'ETHERSCAN_API_KEY': 'test_key',
                'TELEGRAM_BOT_TOKEN': 'test_token',
                'TELEGRAM_CHAT_ID': 'test_chat',
                'OPENAI_API_KEY': 'test_openai_key'
            }):
                config = Config(temp_env_path)
                self.assertIn('openai', config.api_config)
                self.assertEqual(config.api_config['openai']['api_key'], 'test_openai_key')
        finally:
            if os.path.exists(temp_env_path):
                os.unlink(temp_env_path)
    
    def test_tokens_config(self):
        """Тест конфигурации токенов"""
        with patch.dict(os.environ, self.test_env_vars):
            config = Config(self.env_path)
            tokens = config.get_tokens_config()
            
            # Проверяем структуру токенов
            self.assertIn('FUEL', tokens)
            self.assertIn('ARC', tokens)
            
            fuel_config = tokens['FUEL']
            self.assertEqual(fuel_config['symbol'], 'FUEL')
            self.assertEqual(fuel_config['chain'], 'ethereum')
            self.assertEqual(fuel_config['decimals'], 18)
            
            arc_config = tokens['ARC']
            self.assertEqual(arc_config['symbol'], 'ARC')
            self.assertEqual(arc_config['chain'], 'solana')
            self.assertEqual(arc_config['decimals'], 9)
    
    def test_environment_checks(self):
        """Тест проверок окружения"""
        with patch.dict(os.environ, self.test_env_vars):
            config = Config(self.env_path)
            
            self.assertTrue(config.is_development())
            self.assertFalse(config.is_production())
            
            # Тест продакшн окружения
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as temp_env:
                temp_env.write('ETHERSCAN_API_KEY=test_key\n')
                temp_env.write('TELEGRAM_BOT_TOKEN=test_token\n')
                temp_env.write('TELEGRAM_CHAT_ID=test_chat\n')
                temp_env.write('ENVIRONMENT=production\n')
                temp_env_path = temp_env.name
            
            try:
                with patch.dict(os.environ, {
                    'ETHERSCAN_API_KEY': 'test_key',
                    'TELEGRAM_BOT_TOKEN': 'test_token',
                    'TELEGRAM_CHAT_ID': 'test_chat',
                    'ENVIRONMENT': 'production'
                }):
                    prod_config = Config(temp_env_path)
                    self.assertTrue(prod_config.is_production())
                    self.assertFalse(prod_config.is_development())
            finally:
                if os.path.exists(temp_env_path):
                    os.unlink(temp_env_path)
    
    def test_debug_info(self):
        """Тест отладочной информации"""
        with patch.dict(os.environ, self.test_env_vars):
            config = Config(self.env_path)
            debug_info = config.get_debug_info()
            
            # Проверяем структуру отладочной информации
            self.assertIn('environment', debug_info)
            self.assertIn('api_keys_configured', debug_info)
            self.assertIn('monitoring', debug_info)
            self.assertIn('whale_tracker', debug_info)
            self.assertIn('logging', debug_info)
            self.assertIn('database', debug_info)
            
            # Проверяем значения
            self.assertEqual(debug_info['environment'], 'development')
            self.assertTrue(debug_info['api_keys_configured']['etherscan'])
            self.assertTrue(debug_info['api_keys_configured']['telegram'])
    
    def test_get_config_function(self):
        """Тест функции get_config"""
        config_instance = get_config()
        self.assertIsInstance(config_instance, Config)
    
    def test_reload_config_function(self):
        """Тест функции reload_config"""
        # Создаем новый .env с другими значениями
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as temp_env:
            temp_env.write('ETHERSCAN_API_KEY=new_key\n')
            temp_env.write('TELEGRAM_BOT_TOKEN=new_token\n')
            temp_env.write('TELEGRAM_CHAT_ID=new_chat\n')
            temp_env.write('LOG_LEVEL=DEBUG\n')
            temp_env_path = temp_env.name
        
        try:
            with patch.dict(os.environ, {
                'ETHERSCAN_API_KEY': 'new_key',
                'TELEGRAM_BOT_TOKEN': 'new_token',
                'TELEGRAM_CHAT_ID': 'new_chat',
                'LOG_LEVEL': 'DEBUG'
            }):
                new_config = reload_config(temp_env_path)
                self.assertEqual(new_config.api_config['etherscan']['api_key'], 'new_key')
                self.assertEqual(new_config.logging_config['level'], 'DEBUG')
        finally:
            if os.path.exists(temp_env_path):
                os.unlink(temp_env_path)

if __name__ == '__main__':
    unittest.main() 