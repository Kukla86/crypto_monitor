import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import monitor

class TestCEX(unittest.IsolatedAsyncioTestCase):
    @patch('monitor.check_bybit_price')
    @patch('monitor.check_okx_price')
    @patch('monitor.check_htx_price')
    @patch('monitor.check_gate_price')
    async def test_check_cex_success(self, mock_gate, mock_htx, mock_okx, mock_bybit):
        mock_bybit.return_value = {'price': 1.23, 'volume_24h': 1000}
        mock_okx.return_value = {'price': 1.24, 'volume_24h': 1100}
        mock_htx.return_value = {'price': 1.25, 'volume_24h': 1200}
        mock_gate.return_value = {'price': 1.26, 'volume_24h': 1300}
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_cex(session)
            self.assertIn('FUEL', result)
            self.assertIn('bybit', result['FUEL'])
            self.assertIn('okx', result['FUEL'])
            self.assertIn('htx', result['FUEL'])
            self.assertIn('gate', result['FUEL'])

    @patch('monitor.check_bybit_price')
    @patch('monitor.check_okx_price')
    @patch('monitor.check_htx_price')
    @patch('monitor.check_gate_price')
    async def test_check_cex_partial_failure(self, mock_gate, mock_htx, mock_okx, mock_bybit):
        mock_bybit.return_value = {'price': 1.23, 'volume_24h': 1000}
        mock_okx.return_value = {'error': 'API error'}
        mock_htx.return_value = {'error': 'Network error'}
        mock_gate.return_value = {'price': 1.26, 'volume_24h': 1300}
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_cex(session)
            self.assertIn('FUEL', result)
            self.assertIn('bybit', result['FUEL'])
            self.assertIn('error', result['FUEL']['okx'])
            self.assertIn('error', result['FUEL']['htx'])
            self.assertIn('gate', result['FUEL'])

    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_okx_price_success(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            'code': '0',
            'data': [{
                'last': '1.23',
                'vol24h': '1000',
                'change24h': '0.05',
                'high24h': '1.5',
                'low24h': '1.0'
            }]
        })
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_okx_price(session, 'FUEL')
            self.assertIn('price', result)
            self.assertEqual(result['price'], 1.23)

    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_htx_price_success(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            'status': 'ok',
            'tick': {
                'close': '1.23',
                'vol': '1000',
                'open': '1.20',
                'high': '1.5',
                'low': '1.0'
            }
        })
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_htx_price(session, 'FUEL')
            self.assertIn('price', result)
            self.assertEqual(result['price'], 1.23)

    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_gate_price_success(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=[{
            'last': '1.23',
            'quote_volume': '1000',
            'change_percentage': '2.5',
            'high_24h': '1.5',
            'low_24h': '1.0'
        }])
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_gate_price(session, 'FUEL')
            self.assertIn('price', result)
            self.assertEqual(result['price'], 1.23)

if __name__ == '__main__':
    unittest.main() 