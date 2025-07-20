import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from monitor import (
    check_twitter_official,
    check_github_official,
    check_discord_official,
    send_official_post_alert,
    send_github_commit_alert,
    send_discord_server_alert
)

pytestmark = pytest.mark.asyncio


class TestOfficialSources:
    """Тесты для мониторинга официальных источников"""
    
    @pytest.fixture
    def sample_twitter_post(self):
        """Тестовые данные Twitter поста"""
        return {
            'title': 'Fuel Network Announces Major Update',
            'description': 'We are excited to announce a major update to the Fuel Network protocol',
            'link': 'https://nitter.net/fuel_network/status/123456789',
            'pub_date': 'Mon, 15 Jan 2024 10:00:00 GMT',
            'source': 'https://nitter.net/fuel_network/rss'
        }
    
    @pytest.fixture
    def sample_github_commit(self):
        """Тестовые данные GitHub коммита"""
        return {
            'sha': 'abc123def456',
            'commit': {
                'author': {
                    'name': 'John Doe',
                    'date': '2024-01-15T10:00:00Z'
                },
                'message': 'feat: add new feature to protocol\n\nThis commit adds a new feature to the protocol'
            }
        }
    
    @pytest.fixture
    def sample_discord_server(self):
        """Тестовые данные Discord сервера"""
        return {
            'guild': {
                'name': 'Fuel Network Community'
            },
            'approximate_member_count': 5000,
            'approximate_presence_count': 1200
        }
    
    @patch('monitor.parse_rss_news')
    @patch('monitor.send_official_post_alert')
    @patch('monitor.logger')
    @patch('monitor.parsedate_to_datetime')
    @patch('monitor.timedelta')
    @patch('monitor.datetime')
    async def test_check_twitter_official(self, mock_datetime, mock_timedelta, mock_parsedate, mock_logger, mock_send_alert, mock_parse_rss, sample_twitter_post):
        """Тест мониторинга Twitter"""
        # Настраиваем моки
        mock_parse_rss.return_value = [sample_twitter_post]
        mock_send_alert.return_value = None
        
        # Мокаем парсинг даты
        from datetime import datetime
        mock_parsedate.return_value = datetime(2024, 1, 15, 10, 0, 0)  # Время поста
        mock_datetime.now.return_value = datetime(2024, 1, 15, 12, 0, 0)  # Через 2 часа после поста
        
        # Мокаем timedelta для сравнения
        mock_timedelta_instance = MagicMock()
        mock_timedelta_instance.__lt__ = MagicMock(return_value=True)  # Пост не старше 24 часов
        mock_timedelta.return_value = mock_timedelta_instance
        
        # Тестируем
        await check_twitter_official('FUEL', ['@fuel_network'])
        
        # Проверяем, что функции были вызваны
        assert mock_parse_rss.called
        assert mock_send_alert.called
        
        # Проверяем логирование
        assert mock_logger.info.called
    
    @patch('aiohttp.ClientSession.get')
    @patch('monitor.send_github_commit_alert')
    @patch('monitor.logger')
    @patch('monitor.datetime')
    async def test_check_github_official(self, mock_datetime, mock_logger, mock_send_alert, mock_get, sample_github_commit):
        """Тест мониторинга GitHub"""
        # Настраиваем моки
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[sample_github_commit])
        mock_get.return_value.__aenter__.return_value = mock_response
        
        mock_send_alert.return_value = None
        
        # Мокаем datetime для прохождения проверки даты
        from datetime import datetime
        mock_datetime.now.return_value = datetime(2024, 1, 15, 12, 0, 0)  # Через 2 часа после коммита
        
        # Тестируем
        await check_github_official('FUEL', ['https://github.com/FuelLabs/fuel-core'])
        
        # Проверяем, что функции были вызваны
        assert mock_get.called
        assert mock_send_alert.called
        
        # Проверяем логирование
        assert mock_logger.info.called
    
    @patch('aiohttp.ClientSession.get')
    @patch('monitor.send_discord_server_alert')
    @patch('monitor.logger')
    async def test_check_discord_official(self, mock_logger, mock_send_alert, mock_get, sample_discord_server):
        """Тест мониторинга Discord"""
        # Настраиваем моки
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=sample_discord_server)
        mock_get.return_value.__aenter__.return_value = mock_response
        
        mock_send_alert.return_value = None
        
        # Тестируем
        await check_discord_official('FUEL', ['https://discord.gg/fuel-network'])
        
        # Проверяем, что функции были вызваны
        assert mock_get.called
        assert mock_send_alert.called
        
        # Проверяем логирование
        assert mock_logger.info.called
    
    @patch('monitor.was_news_alert_sent')
    @patch('monitor.send_alert')
    @patch('monitor.save_news_alert_sent')
    @patch('monitor.logger')
    async def test_send_official_post_alert_new_post(self, mock_logger, mock_save, mock_send_alert, mock_was_sent, sample_twitter_post):
        """Тест отправки алерта о новом посте"""
        # Настраиваем моки
        mock_was_sent.return_value = False  # Пост не был отправлен
        mock_send_alert.return_value = None
        
        # Тестируем
        await send_official_post_alert(sample_twitter_post, 'FUEL', 'Twitter', 'fuel_network')
        
        # Проверяем, что функции были вызваны
        assert mock_was_sent.called
        assert mock_send_alert.called
        assert mock_save.called
        
        # Проверяем логирование
        assert mock_logger.info.called
    
    @patch('monitor.was_news_alert_sent')
    @patch('monitor.send_alert')
    @patch('monitor.save_news_alert_sent')
    @patch('monitor.logger')
    async def test_send_official_post_alert_duplicate_post(self, mock_logger, mock_save, mock_send_alert, mock_was_sent, sample_twitter_post):
        """Тест пропуска дублированного поста"""
        # Настраиваем моки
        mock_was_sent.return_value = True  # Пост уже был отправлен
        mock_send_alert.return_value = None
        
        # Тестируем
        await send_official_post_alert(sample_twitter_post, 'FUEL', 'Twitter', 'fuel_network')
        
        # Проверяем, что проверка была вызвана
        assert mock_was_sent.called
        
        # Проверяем, что отправка НЕ была вызвана
        assert not mock_send_alert.called
        assert not mock_save.called
        
        # Проверяем логирование
        assert mock_logger.info.called
    
    @patch('monitor.was_news_alert_sent')
    @patch('monitor.send_alert')
    @patch('monitor.save_news_alert_sent')
    @patch('monitor.logger')
    async def test_send_github_commit_alert_new_commit(self, mock_logger, mock_save, mock_send_alert, mock_was_sent, sample_github_commit):
        """Тест отправки алерта о новом коммите"""
        # Настраиваем моки
        mock_was_sent.return_value = False  # Коммит не был отправлен
        mock_send_alert.return_value = None
        
        # Тестируем
        await send_github_commit_alert(sample_github_commit, 'FUEL', 'FuelLabs', 'fuel-core')
        
        # Проверяем, что функции были вызваны
        assert mock_was_sent.called
        assert mock_send_alert.called
        assert mock_save.called
        
        # Проверяем логирование
        assert mock_logger.info.called
    
    @patch('monitor.was_news_alert_sent')
    @patch('monitor.send_alert')
    @patch('monitor.save_news_alert_sent')
    @patch('monitor.logger')
    async def test_send_discord_server_alert_new_server(self, mock_logger, mock_save, mock_send_alert, mock_was_sent, sample_discord_server):
        """Тест отправки алерта о Discord сервере"""
        # Настраиваем моки
        mock_was_sent.return_value = False  # Сервер не был отправлен
        mock_send_alert.return_value = None
        
        # Тестируем
        await send_discord_server_alert(sample_discord_server, 'FUEL', 'fuel-network')
        
        # Проверяем, что функции были вызваны
        assert mock_was_sent.called
        assert mock_send_alert.called
        assert mock_save.called
        
        # Проверяем логирование
        assert mock_logger.info.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 