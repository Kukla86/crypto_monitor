#!/usr/bin/env python3
"""
Тесты для функции health_check
"""

import unittest
import sys
import asyncio
import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock
sys.path.append('..')

import monitor


class TestHealthCheck(unittest.TestCase):
    """Тесты для функции health_check"""
    
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
    
    @pytest.mark.asyncio
    async def test_health_check_basic(self):
        """Тест базовой работы health_check"""
        result = await monitor.health_check()
        
        # Проверяем структуру ответа
        self.assertIn('timestamp', result)
        self.assertIn('overall_status', result)
        self.assertIn('components', result)
        self.assertIn('errors', result)
        
        # Проверяем, что overall_status - это строка
        self.assertIsInstance(result['overall_status'], str)
        self.assertIn(result['overall_status'], ['healthy', 'degraded', 'unhealthy'])
        
        # Проверяем, что components - это словарь
        self.assertIsInstance(result['components'], dict)
        
        # Проверяем, что errors - это список
        self.assertIsInstance(result['errors'], list)
    
    @pytest.mark.asyncio
    async def test_health_check_database_component(self):
        """Тест проверки компонента базы данных"""
        result = await monitor.health_check()
        
        self.assertIn('database', result['components'])
        db_status = result['components']['database']
        
        self.assertIn('status', db_status)
        self.assertIn('message', db_status)
        self.assertIn(db_status['status'], ['healthy', 'unhealthy'])
    
    @pytest.mark.asyncio
    async def test_health_check_configuration_component(self):
        """Тест проверки компонента конфигурации"""
        result = await monitor.health_check()
        
        self.assertIn('configuration', result['components'])
        config_status = result['components']['configuration']
        
        self.assertIn('status', config_status)
        self.assertIn('message', config_status)
        self.assertIn(config_status['status'], ['healthy', 'warning', 'unhealthy'])
    
    @pytest.mark.asyncio
    async def test_health_check_realtime_data_component(self):
        """Тест проверки компонента real-time данных"""
        result = await monitor.health_check()
        
        self.assertIn('realtime_data', result['components'])
        realtime_status = result['components']['realtime_data']
        
        self.assertIn('status', realtime_status)
        self.assertIn('message', realtime_status)
        self.assertIn(realtime_status['status'], ['healthy', 'warning', 'unhealthy'])
    
    @pytest.mark.asyncio
    async def test_health_check_error_handling_component(self):
        """Тест проверки компонента обработки ошибок"""
        result = await monitor.health_check()
        
        self.assertIn('error_handling', result['components'])
        error_status = result['components']['error_handling']
        
        self.assertIn('status', error_status)
        self.assertIn('message', error_status)
        self.assertIn(error_status['status'], ['healthy', 'warning', 'unhealthy'])
    
    @pytest.mark.asyncio
    async def test_health_check_alerts_component(self):
        """Тест проверки компонента алертов"""
        result = await monitor.health_check()
        
        self.assertIn('alerts', result['components'])
        alerts_status = result['components']['alerts']
        
        self.assertIn('status', alerts_status)
        self.assertIn('message', alerts_status)
        self.assertIn(alerts_status['status'], ['healthy', 'warning', 'unhealthy'])
    
    @pytest.mark.asyncio
    async def test_health_check_with_database_error(self):
        """Тест health_check при ошибке базы данных"""
        # Временно изменяем путь к БД на несуществующий
        original_db_path = monitor.DB_PATH
        monitor.DB_PATH = '/nonexistent/path/database.db'
        
        try:
            result = await monitor.health_check()
            
            # Проверяем, что overall_status стал degraded или unhealthy
            self.assertIn(result['overall_status'], ['degraded', 'unhealthy'])
            
            # Проверяем, что есть ошибка в списке errors
            self.assertTrue(len(result['errors']) > 0)
            
            # Проверяем, что компонент database имеет статус unhealthy
            self.assertEqual(result['components']['database']['status'], 'unhealthy')
            
        finally:
            # Восстанавливаем оригинальный путь
            monitor.DB_PATH = original_db_path
    
    @pytest.mark.asyncio
    async def test_health_check_timestamp_format(self):
        """Тест формата timestamp в health_check"""
        result = await monitor.health_check()
        
        # Проверяем, что timestamp - это ISO формат
        from datetime import datetime
        try:
            datetime.fromisoformat(result['timestamp'])
        except ValueError:
            self.fail("Timestamp is not in ISO format")


if __name__ == '__main__':
    unittest.main() 