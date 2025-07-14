import unittest
import monitor

class TestErrors(unittest.IsolatedAsyncioTestCase):
    async def test_check_solana_onchain_no_address(self):
        session = monitor.aiohttp.ClientSession()
        token = {'symbol': 'ARC'}
        result = await monitor.check_solana_onchain(session, token)
        self.assertIn('error', result)
        await session.close()

if __name__ == '__main__':
    unittest.main() 