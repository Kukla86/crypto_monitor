#!/usr/bin/env python3
"""
Централизованная конфигурация для системы мониторинга криптовалют
Поддерживает разные окружения (dev/prod) и валидацию параметров
"""

import os
import logging
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

class Config:
    """Класс конфигурации с валидацией параметров"""
    
    def __init__(self, env_file: str = 'config.env'):
        """Инициализация конфигурации"""
        # Загружаем переменные окружения
        load_dotenv(env_file)
        
        # Определяем окружение
        self.environment = os.getenv('ENVIRONMENT', 'development').lower()
        
        # Валидируем и загружаем все настройки
        self._load_api_config()
        self._load_monitoring_config()
        self._load_social_config()
        self._load_database_config()
        self._load_logging_config()
        self._validate_config()
    
    def _load_api_config(self):
        """Загрузка API конфигурации"""
        self.api_config = {
            'etherscan': {
                'base_url': 'https://api.etherscan.io/api',
                'api_key': self._get_required_env('ETHERSCAN_API_KEY'),
            },
            'solana': {
                'rpc_url': os.getenv('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com'),
                'rate_limit': int(os.getenv('SOLANA_RATE_LIMIT', '5')),
            },
            'telegram': {
                'bot_token': self._get_required_env('TELEGRAM_BOT_TOKEN'),
                'chat_id': self._get_required_env('TELEGRAM_CHAT_ID'),
            },
            'bybit': {
                'base_url': 'https://api.bybit.com',
                'websocket_url': 'wss://stream.bybit.com/v5/public/spot'
            },
            'okx': {
                'base_url': 'https://www.okx.com/api/v5'
            },
            'htx': {
                'base_url': 'https://api.huobi.pro'
            },
            'gate': {
                'base_url': 'https://api.gateio.ws/api/v4'
            }
        }
        
        # OpenAI API (опционально)
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key and openai_key != 'your_openai_api_key_here':
            self.api_config['openai'] = {
                'api_key': openai_key
            }
    
    def _load_monitoring_config(self):
        """Загрузка конфигурации мониторинга"""
        self.monitoring_config = {
            'check_interval': int(os.getenv('CHECK_INTERVAL', '60')),
            'top_holders_count': int(os.getenv('TOP_HOLDERS_COUNT', '10')),
            'notification_threshold': float(os.getenv('NOTIFICATION_THRESHOLD', '500000')),
            'price_change_threshold': float(os.getenv('PRICE_CHANGE_THRESHOLD', '10')),
            'volume_change_threshold': float(os.getenv('VOLUME_CHANGE_THRESHOLD', '50')),
            'tvl_change_threshold': float(os.getenv('TVL_CHANGE_THRESHOLD', '20')),
            'holders_change_threshold': int(os.getenv('HOLDERS_CHANGE_THRESHOLD', '5')),
            'websocket_enabled': os.getenv('WEBSOCKET_ENABLED', 'true').lower() == 'true',
            'real_time_alerts': os.getenv('REAL_TIME_ALERTS', 'true').lower() == 'true',
        }
        
        # Whale Tracker настройки
        self.whale_tracker_config = {
            'enabled': os.getenv('WHALE_TRACKER_ENABLED', 'false').lower() == 'true',
            'interval': int(os.getenv('WHALE_TRACKER_INTERVAL', '30')),
        }
        
        # Retry конфигурация
        self.retry_config = {
            'max_retries': int(os.getenv('MAX_RETRIES', '3')),
            'retry_delay': float(os.getenv('RETRY_DELAY', '1.0')),
            'backoff_factor': float(os.getenv('BACKOFF_FACTOR', '2.0')),
            'timeout': float(os.getenv('TIMEOUT', '10.0')),
        }
        
        # Rate limiting
        self.rate_limits = {
            'solana_rpc': {'requests_per_minute': 10, 'last_request': 0},
            'etherscan': {'requests_per_minute': 5, 'last_request': 0},
            'defillama': {'requests_per_minute': 120, 'last_request': 0},
            'dexscreener': {'requests_per_minute': 300, 'last_request': 0},
            'bybit_ws': {'requests_per_minute': 10, 'last_request': 0}
        }
    
    def _load_social_config(self):
        """Загрузка конфигурации социальных сетей"""
        self.social_config = {
            'twitter_accounts': [
                '@arcdotfun',
                '@fuel_network', 
                '@BuildOnFuel',
                '@SwayLang',
                'SolanaInsiders'
            ],
            'keywords': ['fuel network', 'ARC', '#FuelNetwork', '#ARC', 'Fuel Labs', 'Sway', 'CreatorBid', 'BID', '#CreatorBid', 'Manta Network', 'MANTA', '#MantaNetwork', 'Hey Anon', 'ANON', '#HeyAnon'],
            'alert_keywords': {
                'CRITICAL': ['hack', 'exploit', 'vulnerability', 'breach'],
                'HIGH': ['rug', 'scam', 'paused', 'frozen', 'suspended'],
                'MEDIUM': ['pump', 'dump', 'airdrop', 'listing', 'upgrade', 'mainnet', 'launch'],
                'INFO': ['announcement', 'update', 'news', 'partnership']
            },
            'telegram_channels': [
                '@fuel_network',
                '@cryptosignals',
                '@binance_signals'
            ],
            'discord_servers': [
                'https://discord.com/invite/fuel-network'
            ],
            'github_accounts': [
                'https://github.com/0xPlaygrounds/rig',
                'https://github.com/FuelLabs'
            ],
            'reddit_subreddits': [
                'r/cryptocurrency',
                'r/defi',
                'r/solana',
                'r/fuelnetwork'
            ],
            'crypto_news_sources': [
                'cointelegraph.com',
                'coindesk.com',
                'decrypt.co',
                'theblock.co'
            ],
            'fetch_interval': int(os.getenv('SOCIAL_FETCH_INTERVAL', '900')),
            'translate_to': os.getenv('TRANSLATE_TO', 'en')
        }
        
        # Telegram API для мониторинга (опционально)
        telegram_api_id = os.getenv('TELEGRAM_API_ID')
        telegram_api_hash = os.getenv('TELEGRAM_API_HASH')
        telegram_phone = os.getenv('TELEGRAM_PHONE')
        
        if telegram_api_id and telegram_api_hash and telegram_phone:
            self.social_config['telegram_api'] = {
                'api_id': telegram_api_id,
                'api_hash': telegram_api_hash,
                'phone': telegram_phone
            }
        
        # Discord токен (опционально)
        discord_token = os.getenv('DISCORD_BOT_TOKEN') or os.getenv('DISCORD_USER_TOKEN')
        if discord_token:
            self.social_config['discord_token'] = discord_token
    
    def _load_database_config(self):
        """Загрузка конфигурации базы данных"""
        self.database_config = {
            'path': os.getenv('DB_PATH', 'crypto_monitor.db'),
            'backup_enabled': os.getenv('DB_BACKUP_ENABLED', 'true').lower() == 'true',
            'backup_interval_hours': int(os.getenv('DB_BACKUP_INTERVAL_HOURS', '24')),
        }
    
    def _load_logging_config(self):
        """Загрузка конфигурации логирования"""
        self.logging_config = {
            'level': os.getenv('LOG_LEVEL', 'INFO').upper(),
            'format': '%(asctime)s - %(levelname)s - %(message)s',
            'file': 'monitoring.log',
            'max_size_mb': int(os.getenv('LOG_MAX_SIZE_MB', '10')),
            'backup_count': int(os.getenv('LOG_BACKUP_COUNT', '5')),
        }
    
    def _get_required_env(self, key: str) -> str:
        """Получение обязательной переменной окружения"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Обязательная переменная окружения {key} не установлена")
        return value
    
    def _validate_config(self):
        """Валидация конфигурации"""
        # Проверяем обязательные API ключи
        required_apis = ['ETHERSCAN_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
        for api in required_apis:
            if not os.getenv(api):
                raise ValueError(f"Обязательный API ключ {api} не установлен")
        
        # Проверяем корректность значений
        if self.monitoring_config['check_interval'] < 10:
            raise ValueError("CHECK_INTERVAL должен быть не менее 10 секунд")
        
        if self.monitoring_config['price_change_threshold'] < 0:
            raise ValueError("PRICE_CHANGE_THRESHOLD должен быть положительным")
        
        # Проверяем уровень логирования
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.logging_config['level'] not in valid_log_levels:
            raise ValueError(f"Неверный уровень логирования: {self.logging_config['level']}")
    
    def get_tokens_config(self) -> Dict[str, Any]:
        """Получение конфигурации токенов"""
        return {
            'FUEL': {
                'symbol': 'FUEL',
                'name': 'Fuel',
                'chain': 'ethereum',
                'contract': '0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c',
                'decimals': 18,
                'priority': 'high',
                'min_amount_usd': 500000
            },
            'ARC': {
                'symbol': 'ARC',
                'name': 'ARC',
                'chain': 'solana',
                'contract': '61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump',
                'decimals': 9,
                'priority': 'high',
                'min_amount_usd': 500000
            },
            'VIRTUAL': {
                'symbol': 'VIRTUAL',
                'name': 'Virtuals Protocol',
                'chain': 'multi',
                'contracts': {
                    'ethereum': '0x44ff8620b8ca30902395a7bd3f2407e1a091bf73',
                    'solana': '3iQL8BFS2vE7mww4ehAqQHAsbmRNCrPxizWAT2Zfyr9y',
                    'base': '0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b'
                },
                'decimals': 18,
                'priority': 'high',
                'min_amount_usd': 500000
            },
            'BID': {
                'symbol': 'BID',
                'name': 'CreatorBid',
                'chain': 'multi',
                'contracts': {
                    'bsc': '0xa1832f7f4e534ae557f9b5ab76de54b1873e498b',
                    'base': '0xa1832f7f4e534ae557f9b5ab76de54b1873e498b'
                },
                'decimals': 18,
                'priority': 'high',
                'min_amount_usd': 100000
            },
            'MANTA': {
                'symbol': 'MANTA',
                'name': 'Manta Network',
                'chain': 'ethereum',
                'contract': '0x95cef13441be50d20ca4558cc0a27b601ac544e5',
                'decimals': 18,
                'priority': 'high',
                'min_amount_usd': 500000
            },
            'ANON': {
                'symbol': 'ANON',
                'name': 'Hey Anon',
                'chain': 'multi',
                'contracts': {
                    'ethereum': '0x79bbf4508b1391af3a0f4b30bb5fc4aa9ab0e07c',
                    'solana': '9McvH6w97oewLmPxqQEoHUAv3u5iYMyQ9AeZZhguYf1T'
                },
                'decimals': 18,
                'priority': 'high',
                'min_amount_usd': 500000
            }
        }
    
    def is_production(self) -> bool:
        """Проверка, является ли окружение продакшн"""
        return self.environment == 'production'
    
    def is_development(self) -> bool:
        """Проверка, является ли окружение разработкой"""
        return self.environment == 'development'
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Получение отладочной информации о конфигурации"""
        return {
            'environment': self.environment,
            'api_keys_configured': {
                'etherscan': bool(self.api_config['etherscan']['api_key']),
                'telegram': bool(self.api_config['telegram']['bot_token']),
                'openai': 'openai' in self.api_config,
            },
            'monitoring': {
                'check_interval': self.monitoring_config['check_interval'],
                'websocket_enabled': self.monitoring_config['websocket_enabled'],
                'real_time_alerts': self.monitoring_config['real_time_alerts'],
            },
            'whale_tracker': {
                'enabled': self.whale_tracker_config['enabled'],
                'interval': self.whale_tracker_config['interval'],
            },
            'logging': {
                'level': self.logging_config['level'],
                'file': self.logging_config['file'],
            },
            'database': {
                'path': self.database_config['path'],
                'backup_enabled': self.database_config['backup_enabled'],
            }
        }

# Глобальный экземпляр конфигурации
config = Config()

def get_config() -> Config:
    """Получение глобального экземпляра конфигурации"""
    return config

def reload_config(env_file: str = 'config.env') -> Config:
    """Перезагрузка конфигурации"""
    global config
    config = Config(env_file)
    return config 