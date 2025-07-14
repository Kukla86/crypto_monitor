import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import monitor

class TestDEX(unittest.IsolatedAsyncioTestCase):
    @patch('monitor.check_dexscreener')
    @patch('monitor.check_defillama_tvl')
    async def test_check_dex_success(self, mock_defillama, mock_dexscreener):
        mock_dexscreener.return_value = {
            'price': 1.23,
            'volume_24h': 1000,
            'liquidity_usd': 50000
        }
        mock_defillama.return_value = {
            'tvl': 100000,
            'protocols': ['uniswap', 'sushiswap']
        }
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_dex(session)
            self.assertIn('FUEL', result)
            self.assertIn('dexscreener', result['FUEL'])
            self.assertIn('defillama', result['FUEL'])

    @patch('monitor.check_dexscreener')
    @patch('monitor.check_defillama_tvl')
    async def test_check_dex_cache(self, mock_defillama, mock_dexscreener):
        mock_dexscreener.return_value = {
            'price': 1.23,
            'volume_24h': 1000
        }
        mock_defillama.return_value = {
            'tvl': 100000
        }
        
        # Очищаем кэш перед тестом
        monitor.DEX_CACHE.clear()
        
        async with monitor.aiohttp.ClientSession() as session:
            # Первый вызов
            result1 = await monitor.check_dex(session)
            # Второй вызов должен использовать кэш
            result2 = await monitor.check_dex(session)
            
            self.assertEqual(result1['FUEL'], result2['FUEL'])
            # Проверяем что функции вызвались только один раз для каждого токена
            self.assertEqual(mock_dexscreener.call_count, 2)  # FUEL и ARC
            self.assertEqual(mock_defillama.call_count, 2)    # FUEL и ARC

    @patch('monitor.rate_limit_check')
    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_dexscreener_success(self, mock_get, mock_rate_limit):
        mock_rate_limit.return_value = True  # Rate limit не превышен
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            'pairs': [{
                'priceUsd': '1.23',
                'volume': {'h24': 1000},
                'liquidity': {'usd': 50000},
                'priceChange': {'h24': 5.2},
                'dexId': 'uniswap_v3'
            }]
        })
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        token = {
            'symbol': 'FUEL',
            'contract': '0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c',
            'chain': 'ethereum'
        }
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_dexscreener(session, token)
            self.assertIn('price', result)
            self.assertEqual(result['price'], 1.23)

    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_dexscreener_no_pairs(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={'pairs': []})
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        token = {
            'symbol': 'FUEL',
            'contract': '0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c',
            'chain': 'ethereum'
        }
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_dexscreener(session, token)
            self.assertIn('error', result)

    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_defillama_tvl_success(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        # Первый вызов - список протоколов с нужным символом
        mock_resp.json = AsyncMock(side_effect=[
            [
                {
                    'name': 'Fuel Protocol',
                    'symbol': 'FUEL',
                    'slug': 'fuel-protocol',
                    'tvl': 1000000
                }
            ],
            # Второй вызов - данные TVL
            {
                'tvl': 1000000,
                'name': 'Fuel Protocol'
            }
        ])
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        token = {
            'symbol': 'FUEL',
            'contract': '0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c',
            'chain': 'ethereum'
        }
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_defillama_tvl(session, token)
            self.assertIn('tvl', result)

    @patch('monitor.rate_limit_check')
    async def test_rate_limit_handling(self, mock_rate_limit):
        mock_rate_limit.return_value = False  # Rate limited
        
        token = {
            'symbol': 'FUEL',
            'contract': '0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c',
            'chain': 'ethereum'
        }
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_dexscreener(session, token)
            self.assertIn('error', result)
            self.assertIn('Rate limited', result['error'])

if __name__ == '__main__':
    unittest.main() 