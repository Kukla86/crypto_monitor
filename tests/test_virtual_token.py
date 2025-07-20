import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from monitor import (
    check_onchain,
    check_cex,
    check_official_sources
)


class TestVirtualToken:
    """Тесты для мультичейн токена VIRTUAL"""
    
    @pytest.fixture
    def mock_tokens_config(self):
        """Мок конфигурации токенов с VIRTUAL"""
        return {
            "tokens": {
                "VIRTUAL": {
                    "symbol": "VIRTUAL",
                    "name": "Virtuals Protocol",
                    "chain": "multi",
                    "contracts": {
                        "ethereum": "0x44ff8620b8ca30902395a7bd3f2407e1a091bf73",
                        "solana": "3iQL8BFS2vE7mww4ehAqQHAsbmRNCrPxizWAT2Zfyr9y",
                        "base": "0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b"
                    },
                    "decimals": 18,
                    "priority": "high",
                    "min_amount_usd": 500000,
                    "social_accounts": {
                        "twitter": ["@virtuals_io"]
                    }
                }
            }
        }
    
    @patch('builtins.open')
    @patch('json.load')
    @patch('monitor.logger')
    async def test_virtual_multi_chain_onchain(self, mock_logger, mock_json_load, mock_open, mock_tokens_config):
        """Тест мультичейн onchain мониторинга для VIRTUAL"""
        # Настройка моков
        mock_json_load.return_value = mock_tokens_config
        mock_open.return_value.__enter__.return_value = MagicMock()
        
        # Мокаем TOKENS чтобы был только VIRTUAL
        with patch('monitor.TOKENS', mock_tokens_config['tokens']), \
             patch('monitor.check_ethereum_onchain') as mock_eth, \
             patch('monitor.check_solana_onchain') as mock_sol:
            
            # Настраиваем возвращаемые значения
            mock_eth.return_value = {'ethereum_data': 'test'}
            mock_sol.return_value = {'solana_data': 'test'}
            
            # Создаем мок сессии
            mock_session = AsyncMock()
            
            # Выполняем тест
            result = await check_onchain(mock_session)
            
            # Проверяем, что функция была вызвана для всех сетей
            assert mock_eth.call_count == 2  # Ethereum и Base
            assert mock_sol.call_count == 1  # Solana
            
            # Проверяем логирование
            assert mock_logger.info.called
    
    @patch('monitor.logger')
    async def test_virtual_cex_support(self, mock_logger):
        """Тест поддержки VIRTUAL на CEX"""
        # Мокаем функции CEX
        with patch('monitor.check_bybit_price') as mock_bybit, \
             patch('monitor.check_okx_price') as mock_okx, \
             patch('monitor.check_htx_price') as mock_htx, \
             patch('monitor.check_gate_price') as mock_gate:
            
            # Настраиваем возвращаемые значения
            mock_bybit.return_value = {'price': 1.71}
            mock_okx.return_value = {'price': 1.72}
            mock_htx.return_value = {'price': 1.70}
            mock_gate.return_value = {'price': 1.71}
            
            # Создаем мок сессии
            mock_session = AsyncMock()
            
            # Мокаем TOKENS
            with patch('monitor.TOKENS', {'VIRTUAL': {'symbol': 'VIRTUAL'}}):
                result = await check_cex(mock_session)
                
                # Проверяем, что все CEX функции были вызваны
                assert mock_bybit.called
                assert mock_okx.called
                assert mock_htx.called
                assert mock_gate.called
                
                # Проверяем результат
                assert 'VIRTUAL' in result
                assert 'bybit' in result['VIRTUAL']
                assert 'okx' in result['VIRTUAL']
                assert 'htx' in result['VIRTUAL']
                assert 'gate' in result['VIRTUAL']
    
    @patch('builtins.open')
    @patch('json.load')
    @patch('monitor.logger')
    async def test_virtual_official_sources(self, mock_logger, mock_json_load, mock_open, mock_tokens_config):
        """Тест мониторинга официальных источников VIRTUAL"""
        # Настройка моков
        mock_json_load.return_value = mock_tokens_config
        mock_open.return_value.__enter__.return_value = MagicMock()
        
        # Выполнение теста
        await check_official_sources()
        
        # Проверяем логирование
        assert mock_logger.info.called
        
        # Проверяем, что функция была вызвана для VIRTUAL
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("VIRTUAL" in call for call in info_calls)
    
    @patch('monitor.logger')
    async def test_virtual_contract_addresses(self, mock_logger):
        """Тест корректности адресов контрактов VIRTUAL"""
        # Проверяем адреса из конфигурации
        expected_addresses = {
            'ethereum': '0x44ff8620b8ca30902395a7bd3f2407e1a091bf73',
            'solana': '3iQL8BFS2vE7mww4ehAqQHAsbmRNCrPxizWAT2Zfyr9y',
            'base': '0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b'
        }
        
        # Загружаем реальную конфигурацию
        with open('tokens.json', 'r') as f:
            config = json.load(f)
        
        virtual_config = config['tokens']['VIRTUAL']
        contracts = virtual_config['contracts']
        
        # Проверяем, что все адреса корректны
        assert contracts['ethereum'] == expected_addresses['ethereum']
        assert contracts['solana'] == expected_addresses['solana']
        assert contracts['base'] == expected_addresses['base']
        
        # Проверяем, что это мультичейн токен
        assert virtual_config['chain'] == 'multi'
    
    @patch('monitor.logger')
    async def test_virtual_social_accounts(self, mock_logger):
        """Тест социальных аккаунтов VIRTUAL"""
        # Загружаем реальную конфигурацию
        with open('tokens.json', 'r') as f:
            config = json.load(f)
        
        virtual_config = config['tokens']['VIRTUAL']
        social_accounts = virtual_config['social_accounts']
        
        # Проверяем Twitter аккаунт
        assert 'twitter' in social_accounts
        assert '@virtuals_io' in social_accounts['twitter']
        
        # Проверяем, что нет Discord (как у ARC)
        assert 'discord' not in social_accounts


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 