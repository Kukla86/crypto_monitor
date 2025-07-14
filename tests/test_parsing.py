import unittest
from unittest.mock import AsyncMock, patch
import monitor

class TestParsing(unittest.IsolatedAsyncioTestCase):
    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_bybit_price(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            'retCode': 0,
            'result': {'list': [{
                'lastPrice': '1.23',
                'volume24h': '1000',
                'price24hPcnt': '0.05',
                'highPrice24h': '1.5',
                'lowPrice24h': '1.0'
            }]}
        })
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        # Создаем реальную сессию для теста
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_bybit_price(session, 'FUEL')
            self.assertIn('price', result)
            self.assertEqual(result['price'], 1.23)

    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_bybit_price_error(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_bybit_price(session, 'FUEL')
            self.assertIn('error', result)

if __name__ == '__main__':
    unittest.main() 