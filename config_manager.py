#!/usr/bin/env python3
"""
Менеджер конфигурации для системы мониторинга криптовалют
Поддерживает динамическую загрузку конфигурации из YAML и JSON файлов
"""

import os
import yaml
import json
import logging
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

@dataclass
class SourceConfig:
    """Конфигурация источника данных"""
    name: str
    enabled: bool
    priority: str
    endpoints: List[Dict[str, Any]]
    methods: List[str]
    rate_limit: Optional[int] = None
    timeout: Optional[int] = None

@dataclass
class MonitoringConfig:
    """Конфигурация мониторинга"""
    intervals: Dict[str, int]
    thresholds: Dict[str, float]
    alerts: Dict[str, Any]
    caching: Dict[str, Any]

class ConfigManager:
    """Менеджер конфигурации с поддержкой горячей перезагрузки"""
    
    def __init__(self, config_dir: str = "config"):
        """Инициализация менеджера конфигурации"""
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # Загружаем переменные окружения
        load_dotenv('config.env')
        
        # Файлы конфигурации
        self.sources_file = self.config_dir / "sources.yaml"
        self.tokens_file = Path("tokens.json")
        self.env_file = Path("config.env")
        
        # Кэш конфигурации
        self._config_cache = {}
        self._last_modified = {}
        self._cache_ttl = 300  # 5 минут
        
        # Загружаем конфигурацию
        self._load_config()
        
        # Запускаем мониторинг изменений
        self._start_config_monitor()
    
    def _load_config(self):
        """Загрузка всей конфигурации"""
        try:
            # Загружаем источники
            self.sources_config = self._load_sources_config()
            
            # Загружаем токены
            self.tokens_config = self._load_tokens_config()
            
            # Загружаем переменные окружения
            self.env_config = self._load_env_config()
            
            # Создаем объединенную конфигурацию
            self.combined_config = self._create_combined_config()
            
            logger.info("Конфигурация успешно загружена")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            self._load_fallback_config()
    
    def _load_sources_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации источников из YAML"""
        if not self.sources_file.exists():
            logger.warning(f"Файл {self.sources_file} не найден, создаем по умолчанию")
            self._create_default_sources_config()
        
        try:
            with open(self.sources_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Валидируем конфигурацию
            self._validate_sources_config(config)
            
            return config
            
        except Exception as e:
            logger.error(f"Ошибка загрузки sources.yaml: {e}")
            return self._get_fallback_sources_config()
    
    def _load_tokens_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации токенов из JSON"""
        if not self.tokens_file.exists():
            logger.warning(f"Файл {self.tokens_file} не найден")
            return {}
        
        try:
            with open(self.tokens_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            return config
            
        except Exception as e:
            logger.error(f"Ошибка загрузки tokens.json: {e}")
            return {}
    
    def _load_env_config(self) -> Dict[str, Any]:
        """Загрузка переменных окружения"""
        config = {
            'api_keys': {},
            'database': {},
            'logging': {},
            'telegram': {},
            'discord': {},
            'openai': {}
        }
        
        # API ключи
        config['api_keys']['etherscan'] = os.getenv('ETHERSCAN_API_KEY')
        config['api_keys']['solana_rpc'] = os.getenv('SOLANA_RPC_URL')
        config['api_keys']['alchemy'] = os.getenv('ALCHEMY_API_KEY')
        config['api_keys']['helius'] = os.getenv('HELIUS_API_KEY')
        
        # База данных
        config['database']['path'] = os.getenv('DB_PATH', 'crypto_monitor.db')
        config['database']['backup_enabled'] = os.getenv('DB_BACKUP_ENABLED', 'true').lower() == 'true'
        
        # Логирование
        config['logging']['level'] = os.getenv('LOG_LEVEL', 'INFO')
        config['logging']['file'] = os.getenv('LOG_FILE', 'monitoring.log')
        
        # Telegram
        config['telegram']['bot_token'] = os.getenv('TELEGRAM_BOT_TOKEN')
        config['telegram']['chat_id'] = os.getenv('TELEGRAM_CHAT_ID')
        config['telegram']['api_id'] = os.getenv('TELEGRAM_API_ID')
        config['telegram']['api_hash'] = os.getenv('TELEGRAM_API_HASH')
        config['telegram']['phone'] = os.getenv('TELEGRAM_PHONE')
        
        # Discord
        config['discord']['user_token'] = os.getenv('DISCORD_USER_TOKEN')
        
        # OpenAI
        config['openai']['api_key'] = os.getenv('OPENAI_API_KEY')
        
        return config
    
    def _create_combined_config(self) -> Dict[str, Any]:
        """Создание объединенной конфигурации"""
        return {
            'sources': self.sources_config.get('sources', {}),
            'monitoring': self.sources_config.get('monitoring', {}),
            'tokens': self.tokens_config.get('tokens', {}),
            'api_keys': self.env_config['api_keys'],
            'database': self.env_config['database'],
            'logging': self.env_config['logging'],
            'telegram': self.env_config['telegram'],
            'discord': self.env_config['discord'],
            'openai': self.env_config['openai']
        }
    
    def _validate_sources_config(self, config: Dict[str, Any]):
        """Валидация конфигурации источников"""
        required_sections = ['sources', 'monitoring']
        
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Отсутствует обязательная секция: {section}")
        
        # Валидируем источники
        sources = config.get('sources', {})
        for source_type, sources_list in sources.items():
            if not isinstance(sources_list, dict):
                raise ValueError(f"Неверный формат источников для {source_type}")
            
            for source_name, source_config in sources_list.items():
                if not isinstance(source_config, dict):
                    raise ValueError(f"Неверный формат конфигурации для {source_name}")
                
                required_fields = ['name', 'enabled', 'priority']
                for field in required_fields:
                    if field not in source_config:
                        raise ValueError(f"Отсутствует обязательное поле {field} для {source_name}")
    
    def _create_default_sources_config(self):
        """Создание конфигурации источников по умолчанию"""
        default_config = {
            'sources': {
                'onchain': {
                    'ethereum': {
                        'name': 'Ethereum Blockchain',
                        'enabled': True,
                        'priority': 'high',
                        'endpoints': [
                            {
                                'name': 'Etherscan',
                                'url': 'https://api.etherscan.io/api',
                                'rate_limit': 5,
                                'timeout': 10
                            }
                        ],
                        'methods': ['get_token_transfers', 'get_liquidity_pools']
                    }
                },
                'cex': {
                    'binance': {
                        'name': 'Binance',
                        'enabled': True,
                        'priority': 'high',
                        'endpoints': [
                            {
                                'name': 'REST API',
                                'url': 'https://api.binance.com/api/v3',
                                'rate_limit': 1200,
                                'timeout': 10
                            }
                        ],
                        'methods': ['get_price', 'get_volume']
                    }
                }
            },
            'monitoring': {
                'intervals': {
                    'onchain': 60,
                    'cex': 30,
                    'dex': 120,
                    'social': 900,
                    'analytics': 300,
                    'news': 1800
                },
                'thresholds': {
                    'price_change': 15.0,
                    'volume_change': 100.0,
                    'tvl_change': 20.0,
                    'holders_change': 5
                },
                'alerts': {
                    'enabled': True,
                    'telegram': True,
                    'discord': False
                },
                'caching': {
                    'enabled': True,
                    'ttl': 300,
                    'max_size': 1000
                }
            }
        }
        
        with open(self.sources_file, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"Создан файл конфигурации по умолчанию: {self.sources_file}")
    
    def _get_fallback_sources_config(self) -> Dict[str, Any]:
        """Получение резервной конфигурации источников"""
        return {
            'sources': {
                'onchain': {
                    'ethereum': {
                        'name': 'Ethereum Blockchain',
                        'enabled': True,
                        'priority': 'high',
                        'endpoints': [],
                        'methods': []
                    }
                }
            },
            'monitoring': {
                'intervals': {'onchain': 60, 'cex': 30},
                'thresholds': {'price_change': 15.0},
                'alerts': {'enabled': True},
                'caching': {'enabled': True}
            }
        }
    
    def _load_fallback_config(self):
        """Загрузка резервной конфигурации"""
        logger.warning("Загружаем резервную конфигурацию")
        
        self.sources_config = self._get_fallback_sources_config()
        self.tokens_config = {}
        self.env_config = self._load_env_config()
        self.combined_config = self._create_combined_config()
    
    def _start_config_monitor(self):
        """Запуск мониторинга изменений конфигурации"""
        # Проверяем, есть ли запущенный event loop
        try:
            loop = asyncio.get_running_loop()
            # Если есть запущенный loop, создаем задачу
            async def monitor_config():
                while True:
                    try:
                        await self._check_config_changes()
                        await asyncio.sleep(30)  # Проверяем каждые 30 секунд
                    except Exception as e:
                        logger.error(f"Ошибка мониторинга конфигурации: {e}")
                        await asyncio.sleep(60)
            
            loop.create_task(monitor_config())
        except RuntimeError:
            # Если нет запущенного loop, просто логируем
            logger.info("Event loop не запущен, мониторинг конфигурации отключен")
    
    async def _check_config_changes(self):
        """Проверка изменений в файлах конфигурации"""
        files_to_check = [self.sources_file, self.tokens_file, self.env_file]
        
        for file_path in files_to_check:
            if not file_path.exists():
                continue
            
            try:
                current_mtime = file_path.stat().st_mtime
                last_mtime = self._last_modified.get(str(file_path), 0)
                
                if current_mtime > last_mtime:
                    logger.info(f"Обнаружены изменения в {file_path}")
                    self._last_modified[str(file_path)] = current_mtime
                    self._load_config()
                    break
                    
            except Exception as e:
                logger.error(f"Ошибка проверки изменений в {file_path}: {e}")
    
    def get_source_config(self, source_type: str, source_name: str) -> Optional[SourceConfig]:
        """Получение конфигурации конкретного источника"""
        try:
            sources = self.combined_config.get('sources', {})
            source_type_config = sources.get(source_type, {})
            source_config = source_type_config.get(source_name, {})
            
            if not source_config:
                return None
            
            return SourceConfig(
                name=source_config['name'],
                enabled=source_config['enabled'],
                priority=source_config['priority'],
                endpoints=source_config.get('endpoints', []),
                methods=source_config.get('methods', [])
            )
            
        except Exception as e:
            logger.error(f"Ошибка получения конфигурации источника {source_type}/{source_name}: {e}")
            return None
    
    def get_monitoring_config(self) -> MonitoringConfig:
        """Получение конфигурации мониторинга"""
        monitoring = self.combined_config.get('monitoring', {})
        
        return MonitoringConfig(
            intervals=monitoring.get('intervals', {}),
            thresholds=monitoring.get('thresholds', {}),
            alerts=monitoring.get('alerts', {}),
            caching=monitoring.get('caching', {})
        )
    
    def get_enabled_sources(self, source_type: str) -> List[str]:
        """Получение списка включенных источников определенного типа"""
        sources = self.combined_config.get('sources', {})
        source_type_config = sources.get(source_type, {})
        
        enabled_sources = []
        for source_name, source_config in source_type_config.items():
            if source_config.get('enabled', False):
                enabled_sources.append(source_name)
        
        return enabled_sources
    
    def get_token_config(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Получение конфигурации токена"""
        tokens = self.combined_config.get('tokens', {})
        return tokens.get(symbol)
    
    def get_api_key(self, service: str) -> Optional[str]:
        """Получение API ключа для сервиса"""
        api_keys = self.combined_config.get('api_keys', {})
        return api_keys.get(service)
    
    def is_source_enabled(self, source_type: str, source_name: str) -> bool:
        """Проверка, включен ли источник"""
        source_config = self.get_source_config(source_type, source_name)
        return source_config is not None and source_config.enabled
    
    def get_check_interval(self, source_type: str) -> int:
        """Получение интервала проверки для типа источника"""
        monitoring_config = self.get_monitoring_config()
        return monitoring_config.intervals.get(source_type, 60)
    
    def get_threshold(self, threshold_name: str) -> float:
        """Получение порогового значения"""
        monitoring_config = self.get_monitoring_config()
        return monitoring_config.thresholds.get(threshold_name, 0.0)
    
    def reload_config(self):
        """Принудительная перезагрузка конфигурации"""
        logger.info("Принудительная перезагрузка конфигурации")
        self._load_config()
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Получение сводки конфигурации"""
        return {
            'sources_count': {
                source_type: len(sources) 
                for source_type, sources in self.combined_config.get('sources', {}).items()
            },
            'tokens_count': len(self.combined_config.get('tokens', {})),
            'enabled_sources': {
                source_type: self.get_enabled_sources(source_type)
                for source_type in self.combined_config.get('sources', {}).keys()
            },
            'monitoring': asdict(self.get_monitoring_config()),
            'last_modified': self._last_modified
        }

# Глобальный экземпляр менеджера конфигурации
config_manager = None

def get_config_manager() -> ConfigManager:
    """Получение глобального менеджера конфигурации"""
    global config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    return config_manager

def reload_config():
    """Перезагрузка конфигурации"""
    global config_manager
    if config_manager:
        config_manager.reload_config()
    else:
        config_manager = ConfigManager() 