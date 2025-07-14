import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import monitor

class TestOnchain(unittest.IsolatedAsyncioTestCase):
    @patch('monitor.os.getenv')
    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_ethereum_onchain_success(self, mock_get, mock_getenv):
        mock_getenv.return_value = 'test_api_key'
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            'status': '1',
            'message': 'OK',
            'result': [
                {
                    'hash': '0x123...',
                    'value': '2000000000000000000000',  # 2000 токенов в wei (больше порога 1000)
                    'from': '0xabc...',
                    'to': '0xdef...',
                    'timeStamp': '1640995200'
                }
            ]
        })
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        token = {
            'symbol': 'FUEL',
            'contract': '0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c',
            'chain': 'ethereum',
            'decimals': 18
        }
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_ethereum_onchain(session, token)
            self.assertIn('large_transfers', result)
            self.assertGreater(len(result['large_transfers']), 0)

    @patch('monitor.aiohttp.ClientSession.get')
    async def test_check_ethereum_onchain_error(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_get.return_value.__aenter__.return_value = mock_resp
        
        token = {
            'symbol': 'FUEL',
            'contract': '0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c',
            'chain': 'ethereum'
        }
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_ethereum_onchain(session, token)
            self.assertIn('error', result)

    @patch('monitor.rate_limit_check')
    @patch('monitor.aiohttp.ClientSession.post')
    async def test_check_solana_onchain_success(self, mock_post, mock_rate_limit):
        mock_rate_limit.return_value = True  # Всегда доступен
        mock_resp_success = AsyncMock()
        mock_resp_success.status = 200
        mock_resp_success.json = AsyncMock(return_value={
            'result': {
                'value': {
                    'amount': '1000000000000',
                    'decimals': 9,
                    'uiAmount': 1000.0
                }
            }
        })
        mock_post.return_value.__aenter__.return_value = mock_resp_success

        token = {
            'symbol': 'ARC',
            'contract': '61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump',
            'chain': 'solana'
        }

        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_solana_onchain(session, token)
            self.assertIn('total_supply', result)

    @patch('monitor.aiohttp.ClientSession.post')
    async def test_check_solana_onchain_error(self, mock_post):
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_post.return_value.__aenter__.return_value = mock_resp
        
        token = {
            'symbol': 'ARC',
            'contract': '61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump',
            'chain': 'solana'
        }
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_solana_onchain(session, token)
            self.assertIn('error', result)

    @patch('monitor.check_ethereum_onchain')
    @patch('monitor.check_solana_onchain')
    async def test_check_onchain_integration(self, mock_solana, mock_ethereum):
        mock_ethereum.return_value = {'holders': [{'address': '0x123', 'balance': '1000'}]}
        mock_solana.return_value = {'holders': [{'address': '0x456', 'balance': '2000'}]}
        
        async with monitor.aiohttp.ClientSession() as session:
            result = await monitor.check_onchain(session)
            self.assertIn('FUEL', result)
            self.assertIn('ARC', result)

if __name__ == '__main__':
    unittest.main() 