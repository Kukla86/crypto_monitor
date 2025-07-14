import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import monitor

class TestAlerts(unittest.IsolatedAsyncioTestCase):
    @patch('monitor.requests.post')
    async def test_send_alert_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        await monitor.send_alert('INFO', 'Test message', 'FUEL')
        self.assertTrue(mock_post.called)

    @patch('monitor.requests.post')
    async def test_send_alert_fail(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        with self.assertLogs('monitor', level='ERROR') as cm:
            await monitor.send_alert('INFO', 'Test message', 'FUEL')
        self.assertIn('Ошибка отправки алерта', ''.join(cm.output))

    @patch('monitor.NEWS_ANALYZER_AVAILABLE', False)
    @patch('monitor.aiohttp.ClientSession')
    async def test_send_social_alert_success(self, mock_session_class):
        # Мокируем создание сессии внутри функции
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        # Настраиваем контекстный менеджер для сессии
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        await monitor.send_social_alert('INFO', 'Twitter', 'msg', 'msg', 'link', 'FUEL', ['fuel'])
        
        # Проверяем что сессия была создана и использована
        mock_session_class.assert_called_once()
        mock_session.post.assert_called_once()

if __name__ == '__main__':
    unittest.main() 