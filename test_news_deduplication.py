import pytest
import asyncio
import json
import hashlib
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from monitor import (
    generate_news_hash,
    was_news_alert_sent,
    save_news_alert_sent,
    send_news_alert
)

pytestmark = pytest.mark.asyncio


class TestNewsDeduplication:
    """Тесты для дедупликации новостей"""
    
    @pytest.fixture
    def sample_news_data(self):
        """Тестовые данные новостей"""
        return {
            'title': 'FUEL Token Listed on Major Exchange',
            'description': 'FUEL token has been listed on a major cryptocurrency exchange',
            'link': 'https://example.com/fuel-listing',
            'source': 'Cointelegraph',
            'published_at': '2024-01-15T10:00:00Z',
            'sentiment': 'positive'
        }
    
    def test_generate_news_hash(self, sample_news_data):
        """Тест генерации хеша новости"""
        # Генерируем хеш
        hash1 = generate_news_hash(sample_news_data)
        
        # Проверяем, что хеш не пустой
        assert len(hash1) == 32  # MD5 хеш = 32 символа
        
        # Проверяем, что одинаковые новости дают одинаковый хеш
        hash2 = generate_news_hash(sample_news_data)
        assert hash1 == hash2
        
        # Проверяем, что разные новости дают разные хеши
        different_news = sample_news_data.copy()
        different_news['title'] = 'Different Title'
        hash3 = generate_news_hash(different_news)
        assert hash1 != hash3
    
    @patch('monitor.sqlite3.connect')
    def test_was_news_alert_sent_false(self, mock_connect, sample_news_data):
        """Тест проверки неотправленной новости"""
        # Мокаем БД
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (0,)  # Новость не найдена
        mock_connect.return_value.__enter__.return_value.cursor.return_value = mock_cursor
        
        # Генерируем хеш
        news_hash = generate_news_hash(sample_news_data)
        
        # Проверяем
        result = was_news_alert_sent(news_hash, 'FUEL', hours=24)
        assert result == False
        
        # Проверяем, что SQL запрос был выполнен
        mock_cursor.execute.assert_called_once()
    
    @patch('monitor.sqlite3.connect')
    def test_was_news_alert_sent_true(self, mock_connect, sample_news_data):
        """Тест проверки уже отправленной новости"""
        # Мокаем БД
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)  # Новость найдена
        mock_connect.return_value.__enter__.return_value.cursor.return_value = mock_cursor
        
        # Генерируем хеш
        news_hash = generate_news_hash(sample_news_data)
        
        # Проверяем
        result = was_news_alert_sent(news_hash, 'FUEL', hours=24)
        assert result == True
    
    @patch('monitor.sqlite3.connect')
    def test_save_news_alert_sent(self, mock_connect, sample_news_data):
        """Тест сохранения информации об отправленной новости"""
        # Мокаем БД
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value.cursor.return_value = mock_cursor
        
        # Генерируем хеш
        news_hash = generate_news_hash(sample_news_data)
        
        # Сохраняем
        save_news_alert_sent(news_hash, 'FUEL', 'high')
        
        # Проверяем, что SQL запрос был выполнен
        mock_cursor.execute.assert_called_once()
        
        # Проверяем параметры запроса
        call_args = mock_cursor.execute.call_args
        assert 'INSERT INTO social_alerts' in call_args[0][0]
    
    @patch('monitor.was_news_alert_sent')
    @patch('monitor.send_alert')
    @patch('monitor.check_news_impact_on_price')
    @patch('monitor.save_news_alert_sent')
    @patch('monitor.logger')
    async def test_send_news_alert_new_news(self, mock_logger, mock_save, mock_impact, mock_send_alert, mock_was_sent, sample_news_data):
        """Тест отправки новой новости"""
        # Настраиваем моки
        mock_was_sent.return_value = False  # Новость не была отправлена
        mock_impact.return_value = {'impact': 'moderate'}
        mock_send_alert.return_value = None
        
        # Отправляем новость
        await send_news_alert(sample_news_data, 'FUEL', 'high')
        
        # Проверяем, что все функции были вызваны
        assert mock_was_sent.called
        assert mock_impact.called
        assert mock_send_alert.called
        assert mock_save.called
        
        # Проверяем логирование
        assert mock_logger.info.called
    
    @patch('monitor.was_news_alert_sent')
    @patch('monitor.send_alert')
    @patch('monitor.check_news_impact_on_price')
    @patch('monitor.save_news_alert_sent')
    @patch('monitor.logger')
    async def test_send_news_alert_duplicate_news(self, mock_logger, mock_save, mock_impact, mock_send_alert, mock_was_sent, sample_news_data):
        """Тест пропуска дублированной новости"""
        # Настраиваем моки
        mock_was_sent.return_value = True  # Новость уже была отправлена
        mock_impact.return_value = {'impact': 'moderate'}
        mock_send_alert.return_value = None
        
        # Отправляем новость
        await send_news_alert(sample_news_data, 'FUEL', 'high')
        
        # Проверяем, что проверка была вызвана
        assert mock_was_sent.called
        
        # Проверяем, что отправка НЕ была вызвана
        assert not mock_send_alert.called
        assert not mock_save.called
        
        # Проверяем логирование
        assert mock_logger.info.called
    
    def test_news_hash_uniqueness(self):
        """Тест уникальности хешей для разных новостей"""
        news1 = {
            'title': 'FUEL Token Listed',
            'link': 'https://example.com/1',
            'source': 'Cointelegraph'
        }
        
        news2 = {
            'title': 'ARC Protocol Update',
            'link': 'https://example.com/2',
            'source': 'Decrypt'
        }
        
        news3 = {
            'title': 'FUEL Token Listed',  # Тот же заголовок
            'link': 'https://example.com/3',  # Но другая ссылка
            'source': 'Cointelegraph'
        }
        
        hash1 = generate_news_hash(news1)
        hash2 = generate_news_hash(news2)
        hash3 = generate_news_hash(news3)
        
        # Все хеши должны быть разными
        assert hash1 != hash2
        assert hash1 != hash3
        assert hash2 != hash3
        
        # Проверяем, что хеши стабильны для одинаковых данных
        hash1_again = generate_news_hash(news1)
        assert hash1 == hash1_again


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 