#!/usr/bin/env python3
"""
Система мониторинга криптовалют FUEL и ARC
Мониторинг on-chain данных, CEX, DEX, социальных сетей и аналитики
"""

import asyncio
import aiohttp
import requests
import sqlite3
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import time
import random
import websockets
import threading
from collections import deque
# Проверка доступности переводчика
try:
    from googletrans import Translator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
from telethon import TelegramClient, events
import discord
import subprocess
import sys
import hashlib
import openai
import xml.etree.ElementTree as ET
import re
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify

# Создаем Flask app для webhook
app = Flask(__name__)

# Импорт Telegram бота
try:
    from telegram_bot import CryptoMonitorBot, DexScreenerMonitor
    TELEGRAM_BOT_AVAILABLE = True
except ImportError:
    TELEGRAM_BOT_AVAILABLE = False
    # Временно используем print, так как logger еще не определен
    print("Telegram бот недоступен - модуль telegram_bot не найден")

# Глобальные переменные для кэширования алертов
alert_cache = {}
last_alert_time = {}

# Новая система отслеживания последних значений токенов
last_token_values = {}  # {symbol: {'price': float, 'volume': float, 'timestamp': float}}

def get_last_token_value(symbol: str, value_type: str = 'price') -> Optional[float]:
    """Получает последнее значение токена (цена или объем)"""
    if symbol in last_token_values:
        return last_token_values[symbol].get(value_type)
    return None

def set_last_token_value(symbol: str, price: float = None, volume: float = None):
    """Устанавливает последнее значение токена"""
    if symbol not in last_token_values:
        last_token_values[symbol] = {}
    
    if price is not None:
        last_token_values[symbol]['price'] = price
    if volume is not None:
        last_token_values[symbol]['volume'] = volume
    
    last_token_values[symbol]['timestamp'] = time.time()

def calculate_change_from_last(current_value: float, last_value: float) -> float:
    """Вычисляет процентное изменение от последнего значения"""
    if last_value is None or last_value == 0:
        return 0.0
    return ((current_value - last_value) / last_value) * 100

def should_send_price_alert_from_last(symbol: str, current_price: float, threshold: float = 10.0) -> bool:
    """Проверяет, нужно ли отправить алерт о изменении цены от последнего значения"""
    last_price = get_last_token_value(symbol, 'price')
    if last_price is None:
        # Первый алерт - всегда отправляем
        return True
    
    change_percent = calculate_change_from_last(current_price, last_price)
    return abs(change_percent) >= threshold

def should_send_volume_alert_from_last(symbol: str, current_volume: float, threshold: float = 50.0) -> bool:
    """Проверяет, нужно ли отправить алерт о изменении объема от последнего значения"""
    last_volume = get_last_token_value(symbol, 'volume')
    if last_volume is None:
        # Первый алерт - всегда отправляем
        return True
    
    change_percent = calculate_change_from_last(current_volume, last_volume)
    return abs(change_percent) >= threshold

# Импорт конфигурации
from config import get_config

# Импорт обработки ошибок
try:
    from exceptions import (
        CryptoMonitorError, APIError, RateLimitError, NetworkError, DatabaseError,
        ConfigurationError, TokenError, SocialMediaError, AlertError,
        DataValidationError, RetryableError, CriticalError
    )
    from error_handler import handle_errors, ErrorHandler
    ERROR_HANDLING_AVAILABLE = True
except ImportError:
    ERROR_HANDLING_AVAILABLE = False
    # Fallback декоратор если модуль недоступен
    def handle_errors(operation_name):
        def decorator(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Ошибка в {operation_name}: {e}")
                    return {}
            return wrapper
        return decorator

# Импорт AI анализатора новостей
try:
    from news_analyzer import analyze_crypto_news, should_alert_news, format_news_alert
    NEWS_ANALYZER_AVAILABLE = True
except ImportError:
    NEWS_ANALYZER_AVAILABLE = False

# Импорт новых модулей для улучшения системы
try:
    from performance_monitor import get_performance_monitor, performance_decorator
    from alert_manager import get_alert_manager, AlertLevel, AlertChannel, send_alert
    from recovery_manager import get_recovery_manager, RecoveryConfig, RecoveryStrategy, recovery_decorator
    from config_manager import ConfigManager
    from cache_manager import CacheManager
    NEW_MODULES_AVAILABLE = True
    print("Новые модули загружены успешно")
except ImportError as e:
    NEW_MODULES_AVAILABLE = False
    print(f"Новые модули недоступны: {e}")
    # Fallback функции
    def performance_decorator(operation_name):
        def decorator(func):
            return func
        return decorator
    
    def recovery_decorator(component_name, config=None):
        def decorator(func):
            return func
        return decorator

# Загружаем переменные окружения из .env файла
from dotenv import load_dotenv
load_dotenv('config.env')

# Получаем конфигурацию
config = get_config()

# OpenAI API ключ
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# --- Настройка детального логирования ---
"""
Детальное логирование для отладки:
- Уровень логирования берётся из конфигурации
- Формат: время, уровень, модуль:строка, сообщение
- Логи пишутся в файл monitoring.log и выводятся в консоль
- Отдельный файл для ошибок: error.log
"""
import logging.handlers

def setup_logging():
    """Настройка логирования"""
    try:
        logging.basicConfig(
            level=getattr(logging, config.logging_config['level'], logging.INFO),
            format='%(asctime)s %(levelname)s [%(module)s:%(lineno)d] %(message)s',
            handlers=[
                logging.FileHandler(config.logging_config['file'], mode='a', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
    except Exception as e:
        # Fallback логирование если конфигурация недоступна
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s [%(module)s:%(lineno)d] %(message)s',
            handlers=[
                logging.FileHandler('monitoring.log', mode='a', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        print(f"Ошибка настройки логирования: {e}")

    # Логгер для ошибок
    error_logger = logging.getLogger('error_logger')
    error_logger.setLevel(logging.ERROR)
    error_handler = logging.FileHandler('error.log')
    error_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(module)s:%(lineno)d] %(message)s'))
    error_logger.addHandler(error_handler)

    return logging.getLogger(__name__), error_logger

# Инициализируем логгеры
logger, error_logger = setup_logging()

# Функция для детального логирования ошибок
def log_error(operation: str, error: Exception, context: dict = None):
    """Детальное логирование ошибок с контекстом"""
    error_msg = f"❌ ОШИБКА в {operation}: {type(error).__name__}: {str(error)}"
    if context:
        error_msg += f" | Контекст: {context}"
    
    logger.error(error_msg)
    error_logger.error(error_msg)
    
    # Логируем stack trace для критических ошибок
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        import traceback
        stack_trace = traceback.format_exc()
        error_logger.error(f"Stack trace для {operation}:\n{stack_trace}")

# Глобальные переменные для real-time данных
realtime_data = {
    'FUEL': {
        'price': 0.0,
        'volume_24h': 0.0,
        'price_change_24h': 0.0,
        'last_update': None,
        'source': None,
        'technical_indicators': {},
        'alerts': []
    },
    'ARC': {
        'price': 0.0,
        'volume_24h': 0.0,
        'price_change_24h': 0.0,
        'last_update': None,
        'source': None,
        'technical_indicators': {},
        'alerts': []
    },
    'VIRTUAL': {
        'price': 0.0,
        'volume_24h': 0.0,
        'price_change_24h': 0.0,
        'last_update': None,
        'source': None,
        'technical_indicators': {},
        'alerts': []
    },
    'BID': {
        'price': 0.0,
        'volume_24h': 0.0,
        'price_change_24h': 0.0,
        'last_update': None,
        'source': None,
        'technical_indicators': {},
        'alerts': []
    },
    'MANTA': {
        'price': 0.0,
        'volume_24h': 0.0,
        'price_change_24h': 0.0,
        'last_update': None,
        'source': None,
        'technical_indicators': {},
        'alerts': []
    },
    'ANON': {
        'price': 0.0,
        'volume_24h': 0.0,
        'price_change_24h': 0.0,
        'last_update': None,
        'source': None,
        'technical_indicators': {},
        'alerts': []
    }
}

# Портфолио трекинг
portfolio_data = {
    'holdings': {},  # {symbol: {'amount': float, 'avg_price': float}}
    'total_value': 0.0,
    'total_pnl': 0.0,
    'last_update': None
}

# WebSocket подключения
websocket_connections = {}
websocket_tasks = []

# Технические индикаторы и алерты
technical_alerts = {
    'rsi_overbought': 70,
    'rsi_oversold': 30,
    'macd_signal_threshold': 0.001,
    'volume_spike_threshold': 2.0,  # 200% увеличение объема
    'price_change_threshold': 5.0   # 5% изменение цены
}

# Очередь для алертов
alert_queue = deque(maxlen=100)

# Конфигурация токенов из config
TOKENS = config.get_tokens_config()

# Инициализация базы данных
DB_PATH = config.database_config['path']

def datetime_to_iso(dt):
    """Конвертирует datetime в ISO строку для JSON сериализации"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)

def clean_realtime_data_for_json():
    """Очищает realtime_data для JSON сериализации"""
    cleaned = {}
    for symbol, data in realtime_data.items():
        cleaned[symbol] = {
            'price': data['price'],
            'volume_24h': data['volume_24h'],
            'price_change_24h': data['price_change_24h'],
            'last_update': datetime_to_iso(data['last_update']),
            'source': data['source']
        }
    return cleaned

async def rate_limit_check(api_name: str) -> bool:
    """Проверка rate limiting для API"""
    current_time = time.time()
    limit_info = config.rate_limits.get(api_name, {'requests_per_minute': 60, 'last_request': 0})
    
    if current_time - limit_info['last_request'] < 60.0 / limit_info['requests_per_minute']:
        return False
    
    config.rate_limits[api_name]['last_request'] = current_time
    return True

async def retry_request(func, *args, max_retries=None, **kwargs):
    """Retry логика для HTTP запросов"""
    if max_retries is None:
        max_retries = config.retry_config['max_retries']
    
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                raise e
            
            delay = config.retry_config['retry_delay'] * (config.retry_config['backoff_factor'] ** attempt)
            logger.warning(f"Попытка {attempt + 1} не удалась, повтор через {delay:.1f}с: {e}")
            await asyncio.sleep(delay)

def init_openai():
    """Инициализация OpenAI API"""
    try:
        if OPENAI_API_KEY and OPENAI_API_KEY != 'your_openai_api_key_here':
            # Пробуем новый API
            try:
                from openai import OpenAI
                client = OpenAI(api_key=OPENAI_API_KEY)
                logger.info("✅ OpenAI API инициализирован (новая версия)")
            except ImportError:
                # Fallback для старой версии
                openai.api_key = OPENAI_API_KEY
                logger.info("✅ OpenAI API инициализирован (старая версия)")
        else:
            logger.warning("⚠️ OpenAI API ключ не настроен")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации OpenAI: {e}")

async def analyze_with_chatgpt(prompt: str, analysis_type: str) -> Optional[Dict[str, Any]]:
    """Анализ с помощью ChatGPT"""
    try:
        if not OPENAI_API_KEY or OPENAI_API_KEY == 'your_openai_api_key_here':
            logger.warning("⚠️ OpenAI API ключ не настроен для анализа")
            return None
        
        logger.info(f"🤖 Запуск AI анализа типа: {analysis_type}")
        
        # Настройка модели в зависимости от типа анализа
        model = "gpt-4o"  # Используем GPT-4 Omni для лучшего анализа
        
        # Создаем сообщение для ChatGPT
        messages = [
            {"role": "system", "content": f"Ты эксперт по анализу криптовалютных данных. Тип анализа: {analysis_type}"},
            {"role": "user", "content": prompt}
        ]
        
        logger.info(f"📤 Отправка запроса к OpenAI API (модель: {model})")
        
        # Выполняем запрос к OpenAI API с новым синтаксисом
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            
            # Используем ThreadPoolExecutor для Python 3.8
            import concurrent.futures
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                response = await loop.run_in_executor(
                    executor,
                    lambda: client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=1000,
                        temperature=0.7
                    )
                )
            
            # Преобразуем ответ в старый формат для совместимости
            result = {
                'choices': [{
                    'message': {
                        'content': response.choices[0].message.content
                    }
                }]
            }
            
            logger.info("✅ AI анализ успешно завершен")
            return result
            
        except ImportError:
            # Fallback для старой версии OpenAI
            logger.info("Используем старую версию OpenAI API")
            import concurrent.futures
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                response = await loop.run_in_executor(
                    executor,
                    lambda: openai.ChatCompletion.create(
                        model=model,
                        messages=messages,
                        max_tokens=1000,
                        temperature=0.7
                    )
                )
            
            logger.info("✅ AI анализ успешно завершен (старая версия)")
            return response
        
    except Exception as e:
        logger.error(f"❌ Ошибка AI анализа: {e}")
        log_error("AI анализ", e, {"analysis_type": analysis_type})
        return None

def init_database():
    """Инициализация SQLite базы данных"""
    try:
        # Используем глобальный путь к БД
        with sqlite3.connect(DB_PATH) as conn:
            with conn:
                cursor = conn.cursor()
                # Таблица для данных токенов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS token_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        price REAL,
                        volume_24h REAL,
                        market_cap REAL,
                        holders_count INTEGER,
                        top_holders TEXT,
                        tvl REAL,
                        social_mentions INTEGER,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Таблица для алертов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        level TEXT NOT NULL,
                        message TEXT NOT NULL,
                        token_symbol TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Таблица для real-time данных
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS realtime_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        price REAL,
                        volume_24h REAL,
                        price_change_24h REAL,
                        source TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Таблица для технических индикаторов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS technical_indicators (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        indicator_name TEXT NOT NULL,
                        value REAL,
                        signal TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Таблица для социальных алертов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS social_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        source TEXT,
                        level TEXT,
                        original_text TEXT,
                        translated_text TEXT,
                        link TEXT,
                        token TEXT,
                        keywords TEXT,
                        important_news INTEGER
                    )
                ''')
                # Таблица для точек отсчёта алертов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alert_reference (
                        symbol TEXT PRIMARY KEY,
                        last_price REAL,
                        last_volume REAL,
                        last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица для пиковых значений (новая)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS peak_values (
                        symbol TEXT PRIMARY KEY,
                        peak_price REAL DEFAULT 0.0,
                        peak_volume REAL DEFAULT 0.0,
                        last_alert_time INTEGER DEFAULT 0,
                        last_price_alert REAL DEFAULT 0.0,
                        last_volume_alert REAL DEFAULT 0.0,
                        updated_at INTEGER DEFAULT 0
                    )
                ''')
                
                # Таблица для обработанных твитов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS processed_tweets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tweet_hash TEXT UNIQUE,
                        username TEXT NOT NULL,
                        tweet_id TEXT,
                        processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            # conn.commit() не нужен, with сам коммитит
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

async def websocket_bybit_handler():
    """WebSocket обработчик для Bybit с улучшенной обработкой ошибок (исправлено)"""
    reconnect_delay = 5
    max_reconnect_delay = 60
    
    while True:
        try:
            # Проверяем rate limiting
            if not await rate_limit_check('bybit_ws'):
                await asyncio.sleep(1)
                continue
            
            url = "wss://stream.bybit.com/v5/public/spot"
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as websocket:
                logger.info("WebSocket подключение к Bybit установлено")
                
                # Подписываемся на FUEL и ARC
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [
                        "orderbook.1.FUELUSDT",
                        "orderbook.1.ARCUSDT"
                    ]
                }
                await websocket.send(json.dumps(subscribe_msg))
                
                # Сбрасываем delay при успешном подключении
                reconnect_delay = 5
                
                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30)
                        data = json.loads(message)
                        
                        # Обрабатываем данные
                        if 'data' in data:
                            symbol = data.get('topic', '').split('.')[-1]
                            if 'FUEL' in symbol:
                                # Обновляем realtime данные
                                if 'b' in data['data'] and data['data']['b']:
                                    price = float(data['data']['b'][0][0])
                                    realtime_data['FUEL']['price'] = price
                                    realtime_data['FUEL']['last_update'] = datetime.now()
                                    realtime_data['FUEL']['source'] = 'Bybit WS'
                                    
                                    # Сохраняем в БД
                                    await save_realtime_data('FUEL', {
                                        'price': price,
                                        'volume_24h': realtime_data['FUEL'].get('volume_24h', 0),
                                        'price_change_24h': realtime_data['FUEL'].get('price_change_24h', 0)
                                    }, 'Bybit WS')
                            elif 'ARC' in symbol:
                                if 'b' in data['data'] and data['data']['b']:
                                    price = float(data['data']['b'][0][0])
                                    realtime_data['ARC']['price'] = price
                                    realtime_data['ARC']['last_update'] = datetime.now()
                                    realtime_data['ARC']['source'] = 'Bybit WS'
                                    
                                    # Сохраняем в БД
                                    await save_realtime_data('ARC', {
                                        'price': price,
                                        'volume_24h': realtime_data['ARC'].get('volume_24h', 0),
                                        'price_change_24h': realtime_data['ARC'].get('price_change_24h', 0)
                                    }, 'Bybit WS')
                                    
                    except asyncio.TimeoutError:
                        # Отправляем ping для поддержания соединения
                        await websocket.ping()
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("WebSocket соединение закрыто")
                        break
                    except Exception as e:
                        logger.error(f"Ошибка обработки WebSocket сообщения: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"WebSocket соединение разорвано: {e}")
            await asyncio.sleep(reconnect_delay)
            # Увеличиваем delay с ограничением
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

async def websocket_okx_handler():
    """WebSocket обработчик для OKX"""
    reconnect_delay = 5
    max_reconnect_delay = 60
    
    while True:
        try:
            if not await rate_limit_check('okx_ws'):
                await asyncio.sleep(1)
                continue
            
            url = "wss://ws.okx.com:8443/ws/v5/public"
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as websocket:
                logger.info("WebSocket подключение к OKX установлено")
                
                # Подписываемся на ARC и VIRTUAL
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [
                        {"channel": "tickers", "instId": "ARC-USDT"},
                        {"channel": "tickers", "instId": "VIRTUAL-USDT"}
                    ]
                }
                await websocket.send(json.dumps(subscribe_msg))
                
                reconnect_delay = 5
                
                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30)
                        data = json.loads(message)
                        
                        if 'data' in data:
                            ticker_data = data['data'][0]
                            symbol = ticker_data.get('instId', '').replace('-USDT', '')
                            
                            if symbol in ['ARC', 'VIRTUAL']:
                                price = float(ticker_data.get('last', 0))
                                volume = float(ticker_data.get('vol24h', 0))
                                price_change = float(ticker_data.get('change24h', 0)) * 100
                                
                                realtime_data[symbol].update({
                                    'price': price,
                                    'volume_24h': volume,
                                    'price_change_24h': price_change,
                                    'last_update': datetime.now(),
                                    'source': 'OKX WS'
                                })
                                
                                # Сохраняем в БД
                                await save_realtime_data(symbol, {
                                    'price': price,
                                    'volume_24h': volume,
                                    'price_change_24h': price_change
                                }, 'OKX WS')
                                
                                logger.info(f"OKX WebSocket: {symbol} = ${price:.6f} (24h: {price_change:+.2f}%)")
                                await check_realtime_alerts(symbol, realtime_data[symbol])
                                
                    except asyncio.TimeoutError:
                        await websocket.ping()
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("OKX WebSocket соединение закрыто")
                        break
                    except Exception as e:
                        logger.error(f"Ошибка обработки OKX WebSocket: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"OKX WebSocket соединение разорвано: {e}")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

async def websocket_gate_handler():
    """WebSocket обработчик для Gate.io"""
    reconnect_delay = 5
    max_reconnect_delay = 60
    
    while True:
        try:
            if not await rate_limit_check('gate_ws'):
                await asyncio.sleep(1)
                continue
            
            url = "wss://api.gateio.ws/ws/v4/"
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as websocket:
                logger.info("WebSocket подключение к Gate.io установлено")
                
                # Подписываемся на FUEL, VIRTUAL и BID
                subscribe_msg = {
                    "time": int(time.time()),
                    "channel": "spot.tickers",
                    "event": "subscribe",
                    "payload": ["FUEL_USDT", "VIRTUAL_USDT", "BID_USDT"]
                }
                await websocket.send(json.dumps(subscribe_msg))
                
                reconnect_delay = 5
                
                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30)
                        data = json.loads(message)
                        
                        if 'result' in data and data['result'].get('status') == 'success':
                            continue  # Подтверждение подписки
                        
                        if 'result' in data and 'currency_pair' in data['result']:
                            ticker_data = data['result']
                            symbol = ticker_data.get('currency_pair', '').replace('_USDT', '')
                            
                            if symbol in ['FUEL', 'VIRTUAL', 'BID']:
                                price = float(ticker_data.get('last', 0))
                                volume = float(ticker_data.get('quote_volume', 0))
                                price_change = float(ticker_data.get('change_percentage', 0))
                                
                                realtime_data[symbol].update({
                                    'price': price,
                                    'volume_24h': volume,
                                    'price_change_24h': price_change,
                                    'last_update': datetime.now(),
                                    'source': 'Gate.io WS'
                                })
                                
                                # Сохраняем в БД
                                await save_realtime_data(symbol, {
                                    'price': price,
                                    'volume_24h': volume,
                                    'price_change_24h': price_change
                                }, 'Gate.io WS')
                                
                                logger.info(f"Gate.io WebSocket: {symbol} = ${price:.6f} (24h: {price_change:+.2f}%)")
                                await check_realtime_alerts(symbol, realtime_data[symbol])
                                
                    except asyncio.TimeoutError:
                        await websocket.ping()
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("Gate.io WebSocket соединение закрыто")
                        break
                    except Exception as e:
                        logger.error(f"Ошибка обработки Gate.io WebSocket: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"Gate.io WebSocket соединение разорвано: {e}")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

async def start_websocket_connections():
    """Запуск всех WebSocket подключений с обработкой ошибок"""
    logger.info("🚀 Запуск WebSocket подключений...")
    
    while True:
        try:
            # Создаем задачи для каждого WebSocket с обработкой ошибок
            websocket_tasks = []
            
            # Bybit WebSocket
            try:
                bybit_task = asyncio.create_task(websocket_bybit_handler())
                websocket_tasks.append(bybit_task)
            except Exception as e:
                logger.error(f"Ошибка создания Bybit WebSocket задачи: {e}")
            
            # OKX WebSocket
            try:
                okx_task = asyncio.create_task(websocket_okx_handler())
                websocket_tasks.append(okx_task)
            except Exception as e:
                logger.error(f"Ошибка создания OKX WebSocket задачи: {e}")
            
            # Gate.io WebSocket
            try:
                gate_task = asyncio.create_task(websocket_gate_handler())
                websocket_tasks.append(gate_task)
            except Exception as e:
                logger.error(f"Ошибка создания Gate.io WebSocket задачи: {e}")
            
            if not websocket_tasks:
                logger.warning("⚠️ Нет активных WebSocket задач, пропускаем итерацию")
                await asyncio.sleep(30)
                continue
            
            # Запускаем все WebSocket подключения с обработкой исключений
            results = await asyncio.gather(*websocket_tasks, return_exceptions=True)
            
            # Проверяем результаты на ошибки
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"WebSocket ошибка {i}: {result}")
            
            logger.info("✅ WebSocket подключения обработаны")
            
            # Небольшая пауза перед следующей итерацией
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Критическая ошибка в WebSocket подключениях: {e}")
            logger.info("🔄 Перезапуск WebSocket подключений через 30 секунд...")
            await asyncio.sleep(30)

async def save_realtime_data(symbol: str, data: Dict[str, Any], source: str):
    """Сохранение real-time данных в БД"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO realtime_data (symbol, price, volume_24h, price_change_24h, source)
                    VALUES (?, ?, ?, ?, ?)
                ''', (symbol, data['price'], data['volume_24h'], data['price_change_24h'], source))
    except Exception as e:
        logger.error(f"Ошибка сохранения real-time данных: {e}")

# Глобальные переменные для отслеживания пиковых значений
peak_values = {}  # {symbol: {'price': float, 'volume': float, 'last_alert_time': int}}

def get_peak_values(symbol: str) -> Dict[str, Any]:
    """Получает пиковые значения для токена"""
    try:
        peak_data = peak_values.get(symbol, {
            'price': 0.0,
            'volume': 0.0,
            'last_alert_time': 0,
            'last_price_alert': 0.0,
            'last_volume_alert': 0.0
        })
        
        # Валидация типов данных
        for key in ['price', 'volume', 'last_price_alert', 'last_volume_alert']:
            if not isinstance(peak_data[key], (int, float)):
                logger.warning(f"Некорректный тип данных для {symbol}.{key}: {type(peak_data[key])}")
                peak_data[key] = 0.0
                
        if not isinstance(peak_data['last_alert_time'], int):
            logger.warning(f"Некорректный тип времени для {symbol}: {type(peak_data['last_alert_time'])}")
            peak_data['last_alert_time'] = 0
            
        return peak_data
    except Exception as e:
        logger.error(f"Ошибка получения пиковых значений для {symbol}: {e}")
        return {
            'price': 0.0,
            'volume': 0.0,
            'last_alert_time': 0,
            'last_price_alert': 0.0,
            'last_volume_alert': 0.0
        }

def set_peak_values(symbol: str, price: float = None, volume: float = None, alert_type: str = None):
    """Устанавливает пиковые значения для токена"""
    current_time = int(time.time())
    
    if symbol not in peak_values:
        peak_values[symbol] = {
            'price': 0.0,
            'volume': 0.0,
            'last_alert_time': 0,
            'last_price_alert': 0.0,
            'last_volume_alert': 0.0
        }
    
    # Обновляем пиковые значения
    if price is not None and price > peak_values[symbol]['price']:
        peak_values[symbol]['price'] = price
    
    if volume is not None and volume > peak_values[symbol]['volume']:
        peak_values[symbol]['volume'] = volume
    
    # Обновляем время последнего алерта
    peak_values[symbol]['last_alert_time'] = current_time
    
    # Обновляем значения последних алертов
    if alert_type == 'price' and price is not None:
        peak_values[symbol]['last_price_alert'] = price
    elif alert_type == 'volume' and volume is not None:
        peak_values[symbol]['last_volume_alert'] = volume
    
    # Сохраняем в базу данных
    save_peak_values_to_db(symbol, peak_values[symbol])

def save_peak_values_to_db(symbol: str, peak_data: Dict[str, Any]):
    """Сохраняет пиковые значения в базу данных"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO peak_values 
                    (symbol, peak_price, peak_volume, last_alert_time, last_price_alert, last_volume_alert, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    peak_data['price'],
                    peak_data['volume'],
                    peak_data['last_alert_time'],
                    peak_data['last_price_alert'],
                    peak_data['last_volume_alert'],
                    int(time.time())
                ))
    except Exception as e:
        logger.error(f"Ошибка сохранения пиковых значений для {symbol}: {e}")

def load_peak_values_from_db():
    """Загружает пиковые значения из базы данных"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, peak_price, peak_volume, last_alert_time, last_price_alert, last_volume_alert
                FROM peak_values
            ''')
            rows = cursor.fetchall()
            
            for row in rows:
                symbol, peak_price, peak_volume, last_alert_time, last_price_alert, last_volume_alert = row
                peak_values[symbol] = {
                    'price': float(peak_price) if peak_price else 0.0,
                    'volume': float(peak_volume) if peak_volume else 0.0,
                    'last_alert_time': int(last_alert_time) if last_alert_time else 0,
                    'last_price_alert': float(last_price_alert) if last_price_alert else 0.0,
                    'last_volume_alert': float(last_volume_alert) if last_volume_alert else 0.0
                }
            
            logger.info(f"Загружено {len(peak_values)} записей пиковых значений из БД")
    except Exception as e:
        logger.error(f"Ошибка загрузки пиковых значений из БД: {e}")

def should_update_peak(symbol: str, current_price: float, current_volume: float, 
                      price_change_threshold: float = 5.0, volume_change_threshold: float = 10.0) -> bool:
    """Определяет, нужно ли обновить пиковые значения"""
    peak = get_peak_values(symbol)
    
    # Если это первый запуск или прошло много времени
    if peak['last_alert_time'] == 0:
        return True
    
    # Проверяем, не слишком ли часто обновляем
    current_time = int(time.time())
    if current_time - peak['last_alert_time'] < 300:  # 5 минут
        return False
    
    # Проверяем значимость изменений
    price_change = abs((current_price - peak['price']) / peak['price']) * 100 if peak['price'] > 0 else 0
    volume_change = abs((current_volume - peak['volume']) / peak['volume']) * 100 if peak['volume'] > 0 else 0
    
    return price_change > price_change_threshold or volume_change > volume_change_threshold

def calculate_relative_change(current_value: float, reference_value: float) -> float:
    """Вычисляет относительное изменение в процентах"""
    try:
        # Дополнительная валидация типов
        if not isinstance(current_value, (int, float)) or not isinstance(reference_value, (int, float)):
            logger.warning(f"Некорректные типы данных для расчета изменения: current={type(current_value)}, reference={type(reference_value)}")
            return 0.0
            
        if reference_value <= 0:
            return 0.0
        return ((current_value - reference_value) / reference_value) * 100
    except Exception as e:
        logger.error(f"Ошибка расчета относительного изменения: {e}")
        return 0.0

async def check_realtime_alerts(symbol: str, data: Dict[str, Any]):
    """Проверка алертов в реальном времени с техническим анализом"""
    try:
        # Получаем историю цен для технического анализа
        price_history = get_price_history(symbol, hours=24)
        if len(price_history) < 20:
            return
        
        prices = [float(price) for _, price in price_history]
        current_price = data['price']
        
        # Рассчитываем технические индикаторы
        indicators = calculate_technical_indicators(symbol, prices)
        
        # Обновляем данные в realtime_data
        realtime_data[symbol]['technical_indicators'] = indicators
        
        # Проверяем алерты на основе индикаторов
        alerts = []
        
        # 1. RSI алерты
        if 'rsi' in indicators:
            rsi = indicators['rsi']
            if rsi > technical_alerts['rsi_overbought']:
                alerts.append(f"📈 RSI перекуплен ({rsi:.1f}) - возможна коррекция")
            elif rsi < technical_alerts['rsi_oversold']:
                alerts.append(f"📉 RSI перепродан ({rsi:.1f}) - возможен отскок")
        
        # 2. MACD алерты
        if 'macd' in indicators and indicators['macd']:
            macd = indicators['macd']
            if abs(macd['histogram']) > technical_alerts['macd_signal_threshold']:
                if macd['histogram'] > 0:
                    alerts.append(f"🟢 MACD бычий сигнал (гистограмма: {macd['histogram']:.4f})")
                else:
                    alerts.append(f"🔴 MACD медвежий сигнал (гистограмма: {macd['histogram']:.4f})")
        
        # 3. Bollinger Bands алерты
        if 'bollinger_bands' in indicators and indicators['bollinger_bands']:
            bb = indicators['bollinger_bands']
            if current_price <= bb['lower']:
                alerts.append(f"📊 Цена ниже нижней полосы Боллинджера - возможен отскок")
            elif current_price >= bb['upper']:
                alerts.append(f"📊 Цена выше верхней полосы Боллинджера - возможна коррекция")
        
        # 4. Объемные алерты
        current_volume = data['volume_24h']
        avg_volume = sum([float(vol) for _, vol in get_volume_history(symbol, hours=24)]) / 24
        if avg_volume > 0 and current_volume > avg_volume * technical_alerts['volume_spike_threshold']:
            alerts.append(f"📈 Спайк объема: {current_volume/avg_volume:.1f}x от среднего")
        
        # 5. Ценовые алерты
        price_change = abs(data['price_change_24h'])
        if price_change > technical_alerts['price_change_threshold']:
            direction = "📈" if data['price_change_24h'] > 0 else "📉"
            alerts.append(f"{direction} Резкое изменение цены: {price_change:.2f}% за 24ч")
        
        # 6. Скрещивание скользящих средних
        if 'sma_20' in indicators and 'sma_50' in indicators:
            sma_20 = indicators['sma_20']
            sma_50 = indicators['sma_50']
            if current_price > sma_20 > sma_50:
                alerts.append(f"🟢 Золотой крест: цена > SMA20 > SMA50")
            elif current_price < sma_20 < sma_50:
                alerts.append(f"🔴 Мертвый крест: цена < SMA20 < SMA50")
        
        # Отправляем алерты
        for alert in alerts:
            alert_message = f"🔔 {symbol} ТЕХНИЧЕСКИЙ АЛЕРТ: {alert}"
            await send_alert('INFO', alert_message, symbol)
            
            # Сохраняем алерт в realtime_data
            realtime_data[symbol]['alerts'].append({
                'message': alert,
                'timestamp': datetime.now(),
                'type': 'technical'
            })
            
            logger.info(f"Отправлен технический алерт для {symbol}: {alert}")
        
        # Ограничиваем количество алертов в памяти
        if len(realtime_data[symbol]['alerts']) > 10:
            realtime_data[symbol]['alerts'] = realtime_data[symbol]['alerts'][-10:]
            
    except Exception as e:
        logger.error(f"Ошибка проверки real-time алертов: {e}")

def get_volume_history(symbol: str, hours: int = 24) -> List[tuple]:
    """Получение истории объемов"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, volume_24h FROM realtime_data 
                WHERE symbol = ? AND timestamp >= datetime('now', '-{} hours')
                ORDER BY timestamp DESC
            '''.format(hours), (symbol,))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка получения истории объемов: {e}")
        return []

def calculate_technical_indicators(symbol: str, price_history: List[float]) -> Dict[str, Any]:
    """Расчет технических индикаторов"""
    try:
        if len(price_history) < 26:
            return {}
        
        current_price = price_history[-1]
        
        # Простая скользящая средняя (SMA)
        sma_20 = sum(price_history[-20:]) / 20
        sma_10 = sum(price_history[-10:]) / 10
        sma_50 = sum(price_history[-50:]) / 50 if len(price_history) >= 50 else sma_20
        
        # Экспоненциальная скользящая средняя (EMA)
        ema_12 = calculate_ema(price_history, 12)
        ema_26 = calculate_ema(price_history, 26)
        
        # RSI
        rsi = calculate_rsi(price_history, 14)
        
        # MACD
        macd_data = calculate_macd(price_history) if len(price_history) >= 26 else None
        
        # Bollinger Bands
        bb_data = calculate_bollinger_bands(price_history, 20, 2)
        
        # Stochastic Oscillator
        stoch_data = calculate_stochastic(price_history, 14)
        
        # Williams %R
        williams_r = calculate_williams_r(price_history, 14)
        
        # Сигналы
        signals = {}
        
        # SMA сигналы
        if current_price > sma_20:
            signals['sma_20_signal'] = 'BUY'
        else:
            signals['sma_20_signal'] = 'SELL'
            
        if current_price > sma_50:
            signals['sma_50_signal'] = 'BUY'
        else:
            signals['sma_50_signal'] = 'SELL'
        
        # RSI сигналы
        if rsi > 70:
            signals['rsi_signal'] = 'SELL'
        elif rsi < 30:
            signals['rsi_signal'] = 'BUY'
        else:
            signals['rsi_signal'] = 'NEUTRAL'
        
        # MACD сигналы
        if macd_data:
            if macd_data['histogram'] > 0:
                signals['macd_signal'] = 'BUY'
            else:
                signals['macd_signal'] = 'SELL'
        
        # Bollinger Bands сигналы
        if bb_data:
            if current_price <= bb_data['lower']:
                signals['bb_signal'] = 'BUY'
            elif current_price >= bb_data['upper']:
                signals['bb_signal'] = 'SELL'
            else:
                signals['bb_signal'] = 'NEUTRAL'
        
        # Stochastic сигналы
        if stoch_data:
            if stoch_data['k'] > 80:
                signals['stoch_signal'] = 'SELL'
            elif stoch_data['k'] < 20:
                signals['stoch_signal'] = 'BUY'
            else:
                signals['stoch_signal'] = 'NEUTRAL'
        
        # Williams %R сигналы
        if williams_r is not None:
            if williams_r > -20:
                signals['williams_signal'] = 'SELL'
            elif williams_r < -80:
                signals['williams_signal'] = 'BUY'
            else:
                signals['williams_signal'] = 'NEUTRAL'
        
        return {
            'sma_20': sma_20,
            'sma_10': sma_10,
            'sma_50': sma_50,
            'ema_12': ema_12,
            'ema_26': ema_26,
            'rsi': rsi,
            'macd': macd_data,
            'bollinger_bands': bb_data,
            'stochastic': stoch_data,
            'williams_r': williams_r,
            'signals': signals
        }
        
    except Exception as e:
        logger.error(f"Ошибка расчета технических индикаторов: {e}")
        return {}

def calculate_ema(prices: List[float], period: int) -> float:
    """Расчет экспоненциальной скользящей средней"""
    try:
        if len(prices) < period:
            return prices[-1] if prices else 0
            
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
            
        return round(ema, 6)
        
    except Exception as e:
        logger.error(f"Ошибка расчета EMA: {e}")
        return prices[-1] if prices else 0

def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
    """Расчет MACD"""
    try:
        if len(prices) < slow:
            return None
            
        ema_fast = calculate_ema(prices, fast)
        ema_slow = calculate_ema(prices, slow)
        
        macd_line = ema_fast - ema_slow
        
        # Упрощенный расчет signal line
        signal_line = macd_line * 0.8
        histogram = macd_line - signal_line
        
        return {
            'macd': round(macd_line, 6),
            'signal_line': round(signal_line, 6),
            'histogram': round(histogram, 6)
        }
        
    except Exception as e:
        logger.error(f"Ошибка расчета MACD: {e}")
        return None

def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2) -> Dict[str, float]:
    """Расчет полос Боллинджера"""
    try:
        if len(prices) < period:
            return None
            
        sma = sum(prices[-period:]) / period
        
        # Стандартное отклонение
        variance = sum((price - sma) ** 2 for price in prices[-period:]) / period
        std = variance ** 0.5
        
        upper = sma + (std_dev * std)
        lower = sma - (std_dev * std)
        
        return {
            'upper': round(upper, 6),
            'middle': round(sma, 6),
            'lower': round(lower, 6)
        }
        
    except Exception as e:
        logger.error(f"Ошибка расчета Bollinger Bands: {e}")
        return None

def calculate_stochastic(prices: List[float], period: int = 14) -> Dict[str, float]:
    """Расчет стохастического осциллятора"""
    try:
        if len(prices) < period:
            return None
            
        recent_prices = prices[-period:]
        highest_high = max(recent_prices)
        lowest_low = min(recent_prices)
        current_price = prices[-1]
        
        if highest_high == lowest_low:
            k_percent = 50
        else:
            k_percent = ((current_price - lowest_low) / (highest_high - lowest_low)) * 100
            
        # Упрощенный расчет %D (среднее %K)
        d_percent = k_percent * 0.8
        
        return {
            'k': round(k_percent, 2),
            'd': round(d_percent, 2)
        }
        
    except Exception as e:
        logger.error(f"Ошибка расчета Stochastic: {e}")
        return None

def calculate_williams_r(prices: List[float], period: int = 14) -> float:
    """Расчет Williams %R"""
    try:
        if len(prices) < period:
            return None
            
        recent_prices = prices[-period:]
        highest_high = max(recent_prices)
        lowest_low = min(recent_prices)
        current_price = prices[-1]
        
        if highest_high == lowest_low:
            return -50
            
        williams_r = ((highest_high - current_price) / (highest_high - lowest_low)) * -100
        
        return round(williams_r, 2)
        
    except Exception as e:
        logger.error(f"Ошибка расчета Williams %R: {e}")
        return None

async def save_technical_indicators(symbol: str, indicators: Dict[str, Any]):
    """Сохранение технических индикаторов в БД"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            with conn:
                cursor = conn.cursor()
                
                # Сохраняем основные индикаторы
                basic_indicators = ['sma_20', 'sma_10', 'sma_50', 'ema_12', 'ema_26', 'rsi', 'williams_r']
                for indicator_name in basic_indicators:
                    if indicator_name in indicators and indicators[indicator_name] is not None:
                        signal = indicators.get('signals', {}).get(f"{indicator_name}_signal", "NEUTRAL")
                        cursor.execute('''
                            INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                            VALUES (?, ?, ?, ?)
                        ''', (symbol, indicator_name, indicators[indicator_name], signal))
                
                # Сохраняем MACD компоненты
                if indicators.get('macd'):
                    macd_data = indicators['macd']
                    cursor.execute('''
                        INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                        VALUES (?, ?, ?, ?)
                    ''', (symbol, 'MACD', macd_data['macd'], indicators.get('signals', {}).get('macd_signal', 'NEUTRAL')))
                    
                    cursor.execute('''
                        INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                        VALUES (?, ?, ?, ?)
                    ''', (symbol, 'MACD_SIGNAL', macd_data['signal_line'], indicators.get('signals', {}).get('macd_signal', 'NEUTRAL')))
                    
                    cursor.execute('''
                        INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                        VALUES (?, ?, ?, ?)
                    ''', (symbol, 'MACD_HISTOGRAM', macd_data['histogram'], indicators.get('signals', {}).get('macd_signal', 'NEUTRAL')))
                
                # Сохраняем Bollinger Bands
                if indicators.get('bollinger_bands'):
                    bb_data = indicators['bollinger_bands']
                    bb_signal = indicators.get('signals', {}).get('bb_signal', 'NEUTRAL')
                    
                    cursor.execute('''
                        INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                        VALUES (?, ?, ?, ?)
                    ''', (symbol, 'BB_UPPER', bb_data['upper'], bb_signal))
                    
                    cursor.execute('''
                        INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                        VALUES (?, ?, ?, ?)
                    ''', (symbol, 'BB_MIDDLE', bb_data['middle'], bb_signal))
                    
                    cursor.execute('''
                        INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                        VALUES (?, ?, ?, ?)
                    ''', (symbol, 'BB_LOWER', bb_data['lower'], bb_signal))
                
                # Сохраняем Stochastic
                if indicators.get('stochastic'):
                    stoch_data = indicators['stochastic']
                    stoch_signal = indicators.get('signals', {}).get('stoch_signal', 'NEUTRAL')
                    
                    cursor.execute('''
                        INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                        VALUES (?, ?, ?, ?)
                    ''', (symbol, 'STOCH_K', stoch_data['k'], stoch_signal))
                    
                    cursor.execute('''
                        INSERT INTO technical_indicators (symbol, indicator_name, value, signal)
                        VALUES (?, ?, ?, ?)
                    ''', (symbol, 'STOCH_D', stoch_data['d'], stoch_signal))
                    
    except Exception as e:
        logger.error(f"Ошибка сохранения технических индикаторов: {e}")

@handle_errors("check_onchain")
@performance_decorator("check_onchain")
@recovery_decorator("onchain_monitor")
async def check_onchain(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """
    Проверка on-chain данных (Etherscan, Solana RPC)
    Все ошибки обрабатываются централизованно через error_handler
    """
    logger.info("Проверка on-chain данных...")
    results = {}
    
    for symbol, token in TOKENS.items():
        try:
            if token['chain'] == 'ethereum':
                data = await check_ethereum_onchain(session, token)
            elif token['chain'] == 'solana':
                data = await check_solana_onchain(session, token)
            elif token['chain'] == 'multi':
                # Для мультичейн токенов проверяем все сети
                multi_data = {}
                contracts = token.get('contracts', {})
                
                if 'ethereum' in contracts:
                    eth_token = {**token, 'contract': contracts['ethereum']}
                    eth_data = await check_ethereum_onchain(session, eth_token)
                    multi_data['ethereum'] = eth_data
                
                if 'solana' in contracts:
                    sol_token = {**token, 'contract': contracts['solana']}
                    sol_data = await check_solana_onchain(session, sol_token)
                    multi_data['solana'] = sol_data
                
                # Для Base используем Ethereum API (Base совместим с Ethereum)
                if 'base' in contracts:
                    base_token = {**token, 'contract': contracts['base']}
                    base_data = await check_ethereum_onchain(session, base_token)
                    multi_data['base'] = base_data
                
                data = multi_data
            else:
                continue
                
            results[symbol] = data
            
            # Сохраняем данные в БД
            if data and not all('error' in str(v) for v in data.values() if isinstance(v, dict)):
                # Находим лучшие данные (без ошибок)
                best_data = {}
                if isinstance(data, dict):
                    # Для мультичейн токенов
                    for chain, chain_data in data.items():
                        if isinstance(chain_data, dict) and 'error' not in chain_data:
                            if 'large_transfers' in chain_data:
                                best_data['large_transfers'] = chain_data['large_transfers']
                            if 'total_transactions' in chain_data:
                                best_data['total_transactions'] = chain_data['total_transactions']
                            if 'last_activity' in chain_data:
                                best_data['last_activity'] = chain_data['last_activity']
                            break
                else:
                    # Для обычных токенов
                    if 'large_transfers' in data:
                        best_data['large_transfers'] = data['large_transfers']
                    if 'total_transactions' in data:
                        best_data['total_transactions'] = data['total_transactions']
                    if 'last_activity' in data:
                        best_data['last_activity'] = data['last_activity']
                
                if best_data:
                    save_token_data(symbol, best_data)
                    logger.info(f"✅ Сохранены on-chain данные для {symbol}: {best_data}")
            
            logger.info(f"On-chain данные для {symbol}: {data}")
            
            # Проверяем алерты для этого токена
            await check_alerts(symbol, {'onchain': data})
            
        except Exception as e:
            logger.error(f"Ошибка проверки on-chain данных для {symbol}: {e}")
            results[symbol] = {'error': str(e)}
    
    logger.info("On-chain мониторинг завершён")
    return results

async def check_ethereum_onchain(session: aiohttp.ClientSession, token: Dict) -> Dict[str, Any]:
    """Проверка Ethereum on-chain данных"""
    try:
        logger.debug(f"Запрос Etherscan API для токена {token['symbol']}")
        # Получение данных через Etherscan API
        etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
        if not etherscan_api_key or etherscan_api_key == 'your_etherscan_api_key_here':
            logger.warning(f"Etherscan API ключ не настроен для {token['symbol']}")
            return {'error': 'Etherscan API key not configured'}
        
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': token['contract'],
            'startblock': 0,
            'endblock': 99999999,
            'sort': 'desc',
            'apikey': etherscan_api_key
        }
        
        # Проверяем rate limit для Etherscan
        if not await rate_limit_check('etherscan'):
            logger.warning(f"Rate limit для Etherscan API, пропускаем {token['symbol']}")
            return {'error': 'Rate limit exceeded'}
        
        async with session.get('https://api.etherscan.io/api', params=params) as response:
            if response.status == 200:
                data = await response.json()
                logger.debug(f"Etherscan ответ для {token['symbol']}: {data}")
                if data['status'] == '1':
                    transactions = data['result'][:10]  # Последние 10 транзакций
                    logger.debug(f"Получено {len(transactions)} транзакций для {token['symbol']}")
                    
                    # Анализ транзакций
                    large_transfers = []
                    for tx in transactions:
                        if tx['value'] and int(tx['value']) > 0:
                            value_eth = int(tx['value']) / (10 ** token['decimals'])
                            if value_eth > 1000:  # Транзакции больше 1000 токенов
                                large_transfers.append({
                                    'hash': tx['hash'],
                                    'value': value_eth,
                                    'from': tx['from'],
                                    'to': tx['to'],
                                    'timestamp': int(tx['timeStamp'])
                                })
                    
                    logger.debug(f"Найдено {len(large_transfers)} крупных транзакций для {token['symbol']}")
                    return {
                        'large_transfers': large_transfers,
                        'total_transactions': len(transactions),
                        'last_activity': int(transactions[0]['timeStamp']) if transactions else 0
                    }
                else:
                    error_msg = data.get('message', 'Unknown error')
                    if 'NOTOK' in error_msg:
                        logger.warning(f"Etherscan API ошибка: {error_msg} - возможно проблема с API ключом")
                        
                        # Fallback на альтернативные источники
                        try:
                            # Пробуем получить данные через Covalent API
                            covalent_api_key = os.getenv('COVALENT_API_KEY')
                            if covalent_api_key:
                                covalent_url = f"https://api.covalenthq.com/v1/1/address/{token['contract']}/transactions_v3/"
                                headers = {'Authorization': f'Bearer {covalent_api_key}'}
                                
                                async with session.get(covalent_url, headers=headers, timeout=10) as cov_response:
                                    if cov_response.status == 200:
                                        cov_data = await cov_response.json()
                                        if cov_data.get('data', {}).get('items'):
                                            transactions = cov_data['data']['items'][:10]
                                            logger.info(f"✅ Получены данные через Covalent API для {token['symbol']}")
                                            
                                            large_transfers = []
                                            for tx in transactions:
                                                if tx.get('value_quote', 0) > 1000:  # Транзакции больше $1000
                                                    large_transfers.append({
                                                        'hash': tx['tx_hash'],
                                                        'value': tx['value_quote'],
                                                        'from': tx['from_address'],
                                                        'to': tx['to_address'],
                                                        'timestamp': tx['block_signed_at']
                                                    })
                                            
                                            return {
                                                'large_transfers': large_transfers,
                                                'total_transactions': len(transactions),
                                                'last_activity': int(time.time()),
                                                'source': 'covalent'
                                            }
                        except Exception as cov_error:
                            logger.debug(f"Covalent fallback ошибка: {cov_error}")
                    else:
                        logger.warning(f"Etherscan API ошибка: {error_msg}")
            else:
                logger.warning(f"Etherscan HTTP ошибка: {response.status}")
                
    except Exception as e:
        logger.error(f"Ошибка Ethereum on-chain проверки: {e}")
    
    return {'error': 'Failed to fetch data'}

async def check_solana_onchain(session: aiohttp.ClientSession, token: Dict) -> Dict[str, Any]:
    """Проверка on-chain данных Solana с улучшенной обработкой rate limit"""
    try:
        symbol = token['symbol']
        address = token.get('contract') or token.get('address')
        
        if not address:
            logger.error(f"Адрес не найден для токена {symbol}")
            return {'error': 'Address not found'}
        
        # Список RPC endpoints с приоритетом (расширенный)
        rpc_urls = [
            "https://api.mainnet-beta.solana.com",
            "https://solana.public-rpc.com",
            "https://rpc.ankr.com/solana",
            "https://solana-api.projectserum.com",
            "https://solana.getblock.io/mainnet/",
            "https://solana.rpc.extrnode.com",
            "https://solana.rpcpool.com",
            "https://mainnet.rpcpool.com",
            "https://solana.public-rpc.com",
            "https://api.mainnet-beta.solana.com",
            "https://solana-api.projectserum.com",
            "https://solana.rpc.extrnode.com",
            "https://solana.rpcpool.com",
            "https://mainnet.rpcpool.com",
            "https://solana.public-rpc.com",
            "https://api.mainnet-beta.solana.com",
            "https://solana-api.projectserum.com",
            "https://solana.rpc.extrnode.com",
            "https://solana.rpcpool.com",
            "https://mainnet.rpcpool.com",
            "https://solana.rpc.extrnode.com",
            "https://solana.rpcpool.com",
            "https://mainnet.rpcpool.com",
            "https://solana.public-rpc.com",
            "https://api.mainnet-beta.solana.com",
            "https://solana-api.projectserum.com"
        ]
        
        async def fetch_solana_data(rpc_url: str):
            """Получение данных с конкретного RPC endpoint"""
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenSupply",
                "params": [address]
            }
            
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'CryptoMonitor/1.0'
            }
            
            try:
                async with session.post(rpc_url, json=payload, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data and 'result' in data:
                            return data
                        else:
                            raise Exception("Invalid response format")
                    elif resp.status == 429:
                        raise Exception("Rate limited")
                    elif resp.status == 503:
                        raise Exception("Service unavailable")
                    else:
                        raise Exception(f"HTTP {resp.status}")
            except asyncio.TimeoutError:
                raise Exception("Timeout")
            except Exception as e:
                raise Exception(f"Request failed: {str(e)}")
        
        # Пробуем разные RPC endpoints
        for i, rpc_url in enumerate(rpc_urls):
            try:
                # Проверяем rate limit для каждого endpoint
                if not await rate_limit_check(f'solana_rpc_{i}'):
                    logger.debug(f"Rate limit для Solana RPC {i}, пробуем следующий")
                    continue
                
                logger.debug(f"Пробуем Solana RPC {i}: {rpc_url}")
                data = await retry_request(fetch_solana_data, rpc_url, max_retries=2)
                
                if data and 'result' in data and 'value' in data['result']:
                    supply_info = data['result']['value']
                    try:
                        result = {
                            'total_supply': float(supply_info['amount']) / (10 ** supply_info['decimals']),
                            'decimals': supply_info['decimals'],
                            'ui_amount': float(supply_info['uiAmount']),
                            'rpc_endpoint': rpc_url
                        }
                        
                        logger.info(f"Solana данные для {symbol}: supply={result['total_supply']:,.0f}")
                        return result
                    except (ValueError, KeyError, TypeError) as e:
                        logger.warning(f"Ошибка парсинга данных от RPC {i}: {e}")
                        continue
                else:
                    logger.warning(f"Неверный формат ответа от RPC {i}")
                    
            except Exception as e:
                logger.debug(f"Ошибка RPC {i} ({rpc_url}): {e}")
                # Небольшая пауза между попытками
                await asyncio.sleep(1.0)
                continue
        
        # Если все RPC недоступны, возвращаем ошибку
        logger.warning(f"Все Solana RPC endpoints недоступны для {symbol}")
        return {'error': 'All RPC endpoints failed'}
            
    except Exception as e:
        logger.error(f"Критическая ошибка Solana on-chain для {token['symbol']}: {e}")
        return {'error': str(e)}

@handle_errors("check_cex")
@performance_decorator("check_cex")
@recovery_decorator("cex_monitor")
async def cex_loop(session: aiohttp.ClientSession):
    """Бесконечный цикл мониторинга CEX данных"""
    logger.info("🏪 Запуск CEX мониторинга в цикле...")
    while True:
        try:
            logger.info("🏪 Проверка данных CEX...")
            result = await check_cex(session)
            
            # Детальное логирование результатов
            for symbol, data in result.items():
                if 'error' not in str(data):
                    logger.info(f"✅ CEX данные для {symbol}: {data}")
                else:
                    logger.warning(f"⚠️ CEX ошибка для {symbol}: {data}")
            
            await asyncio.sleep(config.monitoring_config['check_interval'])
        except Exception as e:
            logger.error(f"❌ Ошибка в cex_loop: {e}")
            await asyncio.sleep(30)

async def check_cex(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """
    Проверка данных CEX (Binance, Bybit, OKX, HTX, Gate)
    Все ошибки обрабатываются централизованно через error_handler
    """
    logger.info("Проверка данных CEX...")
    results = {}
    
    for symbol, token in TOKENS.items():
        try:
            cex_data = {}
            
            # Получаем список бирж для токена из конфигурации
            token_config = TOKENS.get(symbol, {})
            exchanges = token_config.get('exchanges', [])
            
            # Проверка Bybit
            if 'bybit' in exchanges or symbol in ['FUEL', 'VIRTUAL']:
                bybit_data = await check_bybit_price(session, symbol)
                cex_data['bybit'] = bybit_data
            else:
                cex_data['bybit'] = {'error': 'Not traded on Bybit'}
            
            # Проверка OKX
            if 'okx' in exchanges or symbol in ['ARC', 'VIRTUAL']:
                okx_data = await check_okx_price(session, symbol)
                cex_data['okx'] = okx_data
            else:
                cex_data['okx'] = {'error': 'Not traded on OKX'}
            
            # Проверка HTX
            if 'htx' in exchanges or symbol in ['ARC', 'VIRTUAL']:
                htx_data = await check_htx_price(session, symbol)
                cex_data['htx'] = htx_data
            else:
                cex_data['htx'] = {'error': 'Not traded on HTX'}
            
            # Проверка Gate.io
            if 'gate' in exchanges or symbol in ['FUEL', 'VIRTUAL', 'BID']:
                gate_data = await check_gate_price(session, symbol)
                cex_data['gate'] = gate_data
            else:
                cex_data['gate'] = {'error': 'Not traded on Gate.io'}
            
            # Проверка MEXC
            if 'mexc' in exchanges or symbol in ['BID', 'MANTA', 'SAHARA']:
                mexc_data = await check_mexc_price(session, symbol)
                cex_data['mexc'] = mexc_data
            else:
                cex_data['mexc'] = {'error': 'Not traded on MEXC'}
            
            # Проверка Binance
            if 'binance' in exchanges or symbol in ['MANTA', 'SAHARA']:
                binance_data = await check_binance_price(session, symbol)
                cex_data['binance'] = binance_data
            else:
                cex_data['binance'] = {'error': 'Not traded on Binance'}
            
            # Проверка Upbit
            if 'upbit' in exchanges or symbol == 'SAHARA':
                upbit_data = await check_upbit_price(session, symbol)
                cex_data['upbit'] = upbit_data
            else:
                cex_data['upbit'] = {'error': 'Not traded on Upbit'}
            
            # Проверка BitMart
            if 'bitmart' in exchanges:
                bitmart_data = await check_bitmart_price(session, symbol)
                cex_data['bitmart'] = bitmart_data
            else:
                cex_data['bitmart'] = {'error': 'Not traded on BitMart'}
            
            # Проверка AscendEX
            if 'ascendex' in exchanges:
                ascendex_data = await check_ascendex_price(session, symbol)
                cex_data['ascendex'] = ascendex_data
            else:
                cex_data['ascendex'] = {'error': 'Not traded on AscendEX'}
            
            # Проверка BingX
            if 'bingx' in exchanges:
                bingx_data = await check_bingx_price(session, symbol)
                cex_data['bingx'] = bingx_data
            else:
                cex_data['bingx'] = {'error': 'Not traded on BingX'}
            
            # Проверка LBank
            if 'lbank' in exchanges:
                lbank_data = await check_lbank_price(session, symbol)
                cex_data['lbank'] = lbank_data
            else:
                cex_data['lbank'] = {'error': 'Not traded on LBank'}
            
            # Проверка Bitget
            if 'bitget' in exchanges:
                bitget_data = await check_bitget_price(session, symbol)
                cex_data['bitget'] = bitget_data
            else:
                cex_data['bitget'] = {'error': 'Not traded on Bitget'}
            
            # Проверка KuCoin
            if 'kucoin' in exchanges:
                kucoin_data = await check_kucoin_price(session, symbol)
                cex_data['kucoin'] = kucoin_data
            else:
                cex_data['kucoin'] = {'error': 'Not traded on KuCoin'}
            
            # Проверка Kraken
            if 'kraken' in exchanges:
                kraken_data = await check_kraken_price(session, symbol)
                cex_data['kraken'] = kraken_data
            else:
                cex_data['kraken'] = {'error': 'Not traded on Kraken'}
            
            # Проверка Bitunix
            if 'bitunix' in exchanges:
                bitunix_data = await check_bitunix_price(session, symbol)
                cex_data['bitunix'] = bitunix_data
            else:
                cex_data['bitunix'] = {'error': 'Not traded on Bitunix'}
            
            # Проверка Raydium (DEX)
            if 'raydium' in exchanges:
                raydium_data = await check_raydium_price(session, symbol)
                cex_data['raydium'] = raydium_data
            else:
                cex_data['raydium'] = {'error': 'Not traded on Raydium'}
            
            # Проверка Aerodrome (DEX)
            if 'aerodrome' in exchanges:
                aerodrome_data = await check_aerodrome_price(session, symbol)
                cex_data['aerodrome'] = aerodrome_data
            else:
                cex_data['aerodrome'] = {'error': 'Not traded on Aerodrome'}
            
            results[symbol] = cex_data
            
            # Сохраняем данные в БД
            if cex_data and not all('error' in str(v) for v in cex_data.values()):
                # Находим лучшие данные (без ошибок)
                best_data = {}
                for exchange, data in cex_data.items():
                    if isinstance(data, dict) and 'error' not in data:
                        if 'price' in data:
                            best_data['price'] = data['price']
                        if 'volume_24h' in data:
                            best_data['volume_24h'] = data['volume_24h']
                        if 'market_cap' in data:
                            best_data['market_cap'] = data['market_cap']
                        break
                
                if best_data:
                    save_token_data(symbol, best_data)
                    logger.info(f"✅ Сохранены CEX данные для {symbol}: {best_data}")
            
            logger.info(f"CEX данные для {symbol}: {results[symbol]}")
            
            # Проверяем алерты для этого токена
            await check_alerts(symbol, {'cex': cex_data})
            
        except Exception as e:
            logger.error(f"Ошибка проверки CEX для {symbol}: {e}")
            results[symbol] = {'error': str(e)}
    
    logger.info("CEX мониторинг завершён")
    return results

async def check_bybit_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение цены с Bybit"""
    try:
        logger.debug(f"Запрос Bybit API для {symbol}")
        url = f"{config.api_config['bybit']['base_url']}/v5/market/tickers"
        params = {'category': 'spot', 'symbol': f'{symbol}USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                logger.debug(f"Bybit ответ для {symbol}: {data}")
                if data['retCode'] == 0 and data['result']['list']:
                    ticker = data['result']['list'][0]
                    return {
                        'price': float(ticker['lastPrice']),
                        'volume_24h': float(ticker['volume24h']),
                        'price_change_24h': float(ticker['price24hPcnt']) * 100
                    }
            else:
                logger.warning(f"Bybit API HTTP ошибка: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка Bybit API: {e}")
    
    return {'error': 'Failed to fetch data'}

async def check_okx_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с OKX"""
    try:
        url = f"{config.api_config['okx']['base_url']}/market/ticker"
        params = {'instId': f'{symbol}-USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data['code'] == '0' and data['data']:
                    ticker = data['data'][0]
                    return {
                        'price': float(ticker['last']),
                        'volume_24h': float(ticker['vol24h']),
                        'price_change_24h': float(ticker['change24h']) * 100,
                        'high_24h': float(ticker['high24h']),
                        'low_24h': float(ticker['low24h'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_htx_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с HTX (Huobi)"""
    try:
        url = f"{config.api_config['htx']['base_url']}/market/detail/merged"
        params = {'symbol': f'{symbol.lower()}usdt'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data['status'] == 'ok':
                    tick = data['tick']
                    return {
                        'price': float(tick['close']),
                        'volume_24h': float(tick['vol']),
                        'price_change_24h': ((float(tick['close']) - float(tick['open'])) / float(tick['open'])) * 100,
                        'high_24h': float(tick['high']),
                        'low_24h': float(tick['low'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_gate_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с Gate.io"""
    try:
        url = f"{config.api_config['gate']['base_url']}/spot/tickers"
        params = {'currency_pair': f'{symbol}_USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data:
                    ticker = data[0]
                    return {
                        'price': float(ticker['last']),
                        'volume_24h': float(ticker['quote_volume']),
                        'price_change_24h': float(ticker['change_percentage']),
                        'high_24h': float(ticker['high_24h']),
                        'low_24h': float(ticker['low_24h'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_mexc_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с MEXC"""
    try:
        url = f"https://www.mexc.com/api/platform/spot/market/ticker"
        params = {'symbol': f'{symbol}_USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == 200 and data.get('data'):
                    ticker = data['data']
                    return {
                        'price': float(ticker['last']),
                        'volume_24h': float(ticker['volume']),
                        'price_change_24h': float(ticker['changeRate']) * 100,
                        'high_24h': float(ticker['high']),
                        'low_24h': float(ticker['low'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_binance_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с Binance"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        params = {'symbol': f'{symbol}USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if 'lastPrice' in data:
                    return {
                        'price': float(data['lastPrice']),
                        'volume_24h': float(data['volume']),
                        'price_change_24h': float(data['priceChangePercent']),
                        'high_24h': float(data['highPrice']),
                        'low_24h': float(data['lowPrice'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_upbit_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с Upbit"""
    try:
        url = "https://api.upbit.com/v1/ticker"
        params = {'markets': f'KRW-{symbol}'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data and len(data) > 0:
                    ticker = data[0]
                    # Конвертируем KRW в USD (примерный курс)
                    krw_to_usd = 0.00075  # Примерный курс
                    return {
                        'price': float(ticker['trade_price']) * krw_to_usd,
                        'volume_24h': float(ticker['acc_trade_volume_24h']) * float(ticker['trade_price']) * krw_to_usd,
                        'price_change_24h': float(ticker['signed_change_rate']) * 100,
                        'high_24h': float(ticker['high_price']) * krw_to_usd,
                        'low_24h': float(ticker['low_price']) * krw_to_usd
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_bitmart_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с BitMart"""
    try:
        url = "https://api-cloud.bitmart.com/spot/v1/ticker"
        params = {'symbol': f'{symbol}_USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == 1000 and data.get('data'):
                    ticker = data['data']
                    return {
                        'price': float(ticker['last_price']),
                        'volume_24h': float(ticker['base_volume_24h']),
                        'price_change_24h': float(ticker['fluctuation']),
                        'high_24h': float(ticker['high_24h']),
                        'low_24h': float(ticker['low_24h'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_ascendex_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с AscendEX"""
    try:
        url = "https://ascendex.com/api/pro/v1/ticker"
        params = {'symbol': f'{symbol}/USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == 0 and data.get('data'):
                    ticker = data['data']
                    return {
                        'price': float(ticker['close']),
                        'volume_24h': float(ticker['volume']),
                        'price_change_24h': float(ticker['change']),
                        'high_24h': float(ticker['high']),
                        'low_24h': float(ticker['low'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_bingx_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с BingX"""
    try:
        url = "https://open-api.bingx.com/openApi/spot/v1/ticker/24hr"
        params = {'symbol': f'{symbol}USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == 0 and data.get('data'):
                    ticker = data['data']
                    return {
                        'price': float(ticker['lastPrice']),
                        'volume_24h': float(ticker['volume']),
                        'price_change_24h': float(ticker['priceChangePercent']),
                        'high_24h': float(ticker['highPrice']),
                        'low_24h': float(ticker['lowPrice'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_lbank_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с LBank"""
    try:
        url = "https://api.lbank.info/v2/ticker.do"
        params = {'symbol': f'{symbol}_usdt'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('result') and len(data['result']) > 0:
                    ticker = data['result'][0]
                    return {
                        'price': float(ticker['ticker']['latest']),
                        'volume_24h': float(ticker['ticker']['vol']),
                        'price_change_24h': float(ticker['ticker']['change']),
                        'high_24h': float(ticker['ticker']['high']),
                        'low_24h': float(ticker['ticker']['low'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_bitget_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с Bitget"""
    try:
        url = "https://api.bitget.com/api/spot/v1/market/ticker"
        params = {'symbol': f'{symbol}USDT_SPBL'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == '00000' and data.get('data'):
                    ticker = data['data']
                    return {
                        'price': float(ticker['last']),
                        'volume_24h': float(ticker['baseVolume']),
                        'price_change_24h': float(ticker['usdtRate']),
                        'high_24h': float(ticker['high24h']),
                        'low_24h': float(ticker['low24h'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_kucoin_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с KuCoin"""
    try:
        url = "https://api.kucoin.com/api/v1/market/orderbook/level1"
        params = {'symbol': f'{symbol}-USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == '200000' and data.get('data'):
                    ticker = data['data']
                    return {
                        'price': float(ticker['price']),
                        'volume_24h': float(ticker.get('size', 0)),
                        'price_change_24h': 0,  # KuCoin не предоставляет изменение цены в этом endpoint
                        'high_24h': 0,
                        'low_24h': 0
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_kraken_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с Kraken"""
    try:
        url = "https://api.kraken.com/0/public/Ticker"
        params = {'pair': f'{symbol}USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('error') == [] and data.get('result'):
                    ticker_key = list(data['result'].keys())[0]
                    ticker = data['result'][ticker_key]
                    return {
                        'price': float(ticker['c'][0]),
                        'volume_24h': float(ticker['v'][1]),
                        'price_change_24h': float(ticker['p'][1]) - float(ticker['p'][0]),
                        'high_24h': float(ticker['h'][1]),
                        'low_24h': float(ticker['l'][1])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_bitunix_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с Bitunix"""
    try:
        url = "https://api.bitunix.com/api/v1/market/ticker"
        params = {'symbol': f'{symbol}USDT'}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == 0 and data.get('data'):
                    ticker = data['data']
                    return {
                        'price': float(ticker['last']),
                        'volume_24h': float(ticker['volume']),
                        'price_change_24h': float(ticker['change']),
                        'high_24h': float(ticker['high']),
                        'low_24h': float(ticker['low'])
                    }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_raydium_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с Raydium (DEX)"""
    try:
        # Raydium API для получения данных о пулах
        url = "https://api.raydium.io/v2/sdk/liquidity/mainnet.json"
        
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                # Ищем пул для токена
                for pool in data.get('official', []):
                    if symbol in pool.get('name', ''):
                        return {
                            'price': float(pool.get('price', 0)),
                            'volume_24h': float(pool.get('volume24h', 0)),
                            'price_change_24h': 0,  # Raydium не предоставляет изменение цены
                            'high_24h': 0,
                            'low_24h': 0
                        }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

async def check_aerodrome_price(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение данных с Aerodrome (Base DEX)"""
    try:
        # Aerodrome API для получения данных о пулах
        url = "https://api.aerodrome.finance/v1/pools"
        
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                # Ищем пул для токена
                for pool in data:
                    if symbol in pool.get('token0_symbol', '') or symbol in pool.get('token1_symbol', ''):
                        return {
                            'price': float(pool.get('token0_price', 0)),
                            'volume_24h': float(pool.get('volume_24h', 0)),
                            'price_change_24h': 0,  # Aerodrome не предоставляет изменение цены
                            'high_24h': 0,
                            'low_24h': 0
                        }
            return {'error': f'HTTP {response.status}'}
    except Exception as e:
        return {'error': str(e)}

# Кэш для DEX данных
DEX_CACHE = {}
DEX_CACHE_TTL = 300  # 5 минут

async def dex_loop(session: aiohttp.ClientSession):
    """Бесконечный цикл мониторинга DEX данных"""
    logger.info("🔄 Запуск DEX мониторинга в цикле...")
    while True:
        try:
            logger.info("🔄 Проверка данных DEX...")
            result = await check_dex(session)
            
            # Детальное логирование результатов
            for symbol, data in result.items():
                if 'error' not in str(data):
                    logger.info(f"✅ DEX данные для {symbol}: {data}")
                else:
                    logger.warning(f"⚠️ DEX ошибка для {symbol}: {data}")
            
            await asyncio.sleep(config.monitoring_config['check_interval'])
        except Exception as e:
            logger.error(f"❌ Ошибка в dex_loop: {e}")
            await asyncio.sleep(30)

@handle_errors("check_dex")
@performance_decorator("check_dex")
@recovery_decorator("dex_monitor")
async def check_dex(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """
    Проверка данных DEX (DefiLlama, Dexscreener, GeckoTerminal)
    Все ошибки обрабатываются централизованно через error_handler
    """
    logger.info("Проверка данных DEX...")
    results = {}
    current_time = time.time()
    
    for symbol, token in TOKENS.items():
        try:
            # Проверяем кэш
            cache_key = f"dex_{symbol}"
            if cache_key in DEX_CACHE:
                cache_entry = DEX_CACHE[cache_key]
                if current_time - cache_entry['timestamp'] < DEX_CACHE_TTL:
                    logger.info(f"DEX данные для {symbol} из кэша")
                    results[symbol] = cache_entry['data']
                    continue
            
            # Проверка DexScreener
            dexscreener_data = await check_dexscreener(session, token)
            
            # Проверка DefiLlama TVL
            defillama_data = await check_defillama_tvl(session, token)
            
            # Проверка Aerodrome (только для BID)
            aerodrome_data = None
            if symbol == 'BID':
                aerodrome_data = await check_aerodrome(session, token)
            
            dex_result = {
                'dexscreener': dexscreener_data,
                'defillama': defillama_data
            }
            
            if aerodrome_data:
                dex_result['aerodrome'] = aerodrome_data
            
            # Сохраняем в кэш
            DEX_CACHE[cache_key] = {
                'timestamp': current_time,
                'data': dex_result
            }
            
            results[symbol] = dex_result
            
            # Сохраняем данные в БД
            if dex_result and not all('error' in str(v) for v in dex_result.values()):
                # Находим лучшие данные (без ошибок)
                best_data = {}
                for dex_name, data in dex_result.items():
                    if isinstance(data, dict) and 'error' not in data:
                        if 'price' in data:
                            best_data['price'] = data['price']
                        if 'volume_24h' in data:
                            best_data['volume_24h'] = data['volume_24h']
                        if 'tvl' in data:
                            best_data['tvl'] = data['tvl']
                        if 'liquidity_usd' in data:
                            best_data['liquidity_usd'] = data['liquidity_usd']
                        break
                
                if best_data:
                    save_token_data(symbol, best_data)
                    logger.info(f"✅ Сохранены DEX данные для {symbol}: {best_data}")
            
            logger.info(f"DEX данные для {symbol}: {results[symbol]}")
            
            # Проверяем алерты для этого токена
            await check_alerts(symbol, {'dex': dex_result})
            
        except Exception as e:
            logger.error(f"Ошибка проверки DEX для {symbol}: {e}")
            results[symbol] = {'error': str(e)}
    
    logger.info("DEX мониторинг завершён")
    return results

async def get_dexscreener_data(symbol: str) -> Optional[Dict[str, Any]]:
    """Получение данных с DexScreener для конкретного символа"""
    try:
        # Получаем контракт для символа из конфигурации
        token_config = TOKENS.get(symbol)
        if not token_config:
            logger.warning(f"Токен {symbol} не найден в конфигурации")
            return None
        
        contract = token_config.get('contract', '')
        logger.debug(f"Запрос DexScreener для {symbol} (контракт: {contract})")
        
        # Создаем сессию для запроса
        async with aiohttp.ClientSession() as session:
            # Сначала пробуем поиск по контракту (более точный)
            if contract:
                try:
                    contract_url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
                    async with session.get(contract_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.debug(f"DexScreener по контракту для {symbol}: {data}")
                            
                            if data.get('pairs') and len(data['pairs']) > 0:
                                # Находим пару с наибольшим объемом
                                best_pair = max(data['pairs'], key=lambda x: float(x.get('volume', {}).get('h24', 0)))
                                logger.debug(f"Лучшая пара по контракту для {symbol}: {best_pair}")
                                
                                return {
                                    'price': float(best_pair['priceUsd']),
                                    'volume_24h': float(best_pair['volume']['h24']),
                                    'price_change_24h': float(best_pair['priceChange']['h24']),
                                    'liquidity_usd': float(best_pair['liquidity']['usd'])
                                }
                except Exception as e:
                    logger.warning(f"Ошибка поиска по контракту для {symbol}: {e}")
            
            # Если поиск по контракту не удался, пробуем по символу
            search_url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
            async with session.get(search_url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"DexScreener поиск для {symbol}: {data}")
                    
                    if not data.get('pairs'):
                        logger.warning(f"DexScreener: нет торговых пар для {symbol}")
                        return None
                    
                    # Находим пару с наибольшим объемом
                    best_pair = max(data['pairs'], key=lambda x: float(x.get('volume', {}).get('h24', 0)))
                    logger.debug(f"Лучшая пара по символу для {symbol}: {best_pair}")
                    
                    return {
                        'price': float(best_pair['priceUsd']),
                        'volume_24h': float(best_pair['volume']['h24']),
                        'price_change_24h': float(best_pair['priceChange']['h24']),
                        'liquidity_usd': float(best_pair['liquidity']['usd'])
                    }
                else:
                    logger.warning(f"DexScreener вернул статус {response.status}")
                    return None
                    
    except Exception as e:
        logger.error(f"Ошибка получения данных DexScreener для {symbol}: {e}")
        return None

async def check_dexscreener(session: aiohttp.ClientSession, token: Dict) -> Dict[str, Any]:
    """Получение данных с DexScreener"""
    try:
        symbol = token['symbol']
        chain = token.get('chain', '')
        
        # Обработка мультичейн токенов
        if chain == 'multi':
            contracts = token.get('contracts', {})
            logger.debug(f"Мультичейн токен {symbol} с контрактами: {contracts}")
            
            # Пробуем контракты в порядке приоритета: BSC, Base, Ethereum
            contract_priority = ['bsc', 'base', 'ethereum']
            
            for chain_name in contract_priority:
                if chain_name in contracts:
                    contract = contracts[chain_name]
                    logger.debug(f"Пробуем контракт {chain_name} для {symbol}: {contract}")
                    
                    try:
                        contract_url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
                        async with session.get(contract_url) as response:
                            if response.status == 200:
                                data = await response.json()
                                logger.debug(f"DexScreener по контракту {chain_name} для {symbol}: {data}")
                                
                                if data.get('pairs') and len(data['pairs']) > 0:
                                    # Находим пару с наибольшим объемом
                                    best_pair = max(data['pairs'], key=lambda x: float(x.get('volume', {}).get('h24', 0)))
                                    logger.debug(f"Лучшая пара по контракту {chain_name} для {symbol}: {best_pair}")
                                    
                                    return {
                                        'price': float(best_pair['priceUsd']),
                                        'volume_24h': float(best_pair['volume']['h24']),
                                        'price_change_24h': float(best_pair['priceChange']['h24']),
                                        'liquidity_usd': float(best_pair['liquidity']['usd']),
                                        'chain': chain_name,
                                        'contract': contract
                                    }
                    except Exception as e:
                        logger.warning(f"Ошибка поиска по контракту {chain_name} для {symbol}: {e}")
                        continue
            
            # Если все контракты не сработали, пробуем поиск по символу
            logger.debug(f"Все контракты не сработали для {symbol}, пробуем поиск по символу")
        else:
            # Обычные токены с одним контрактом
            contract = token.get('contract', '')
            logger.debug(f"Запрос DexScreener для {symbol} (контракт: {contract})")
            
            # Сначала пробуем поиск по контракту (более точный)
            if contract:
                try:
                    contract_url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
                    async with session.get(contract_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.debug(f"DexScreener по контракту для {symbol}: {data}")
                            
                            if data.get('pairs') and len(data['pairs']) > 0:
                                # Находим пару с наибольшим объемом
                                best_pair = max(data['pairs'], key=lambda x: float(x.get('volume', {}).get('h24', 0)))
                                logger.debug(f"Лучшая пара по контракту для {symbol}: {best_pair}")
                                
                                return {
                                    'price': float(best_pair['priceUsd']),
                                    'volume_24h': float(best_pair['volume']['h24']),
                                    'price_change_24h': float(best_pair['priceChange']['h24']),
                                    'liquidity_usd': float(best_pair['liquidity']['usd']),
                                    'contract': contract
                                }
                except Exception as e:
                    logger.warning(f"Ошибка поиска по контракту для {symbol}: {e}")
        
        # Если поиск по контракту не удался, пробуем по символу
        search_url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
        async with session.get(search_url) as response:
            if response.status == 200:
                data = await response.json()
                logger.debug(f"DexScreener поиск по символу для {symbol}: {data}")
                
                if not data.get('pairs'):
                    logger.warning(f"DexScreener: нет торговых пар для {symbol}")
                    return {'error': 'No trading pairs found'}
                
                # Находим пару с наибольшим объемом
                best_pair = max(data['pairs'], key=lambda x: float(x.get('volume', {}).get('h24', 0)))
                logger.debug(f"Лучшая пара по символу для {symbol}: {best_pair}")
                
                return {
                    'price': float(best_pair['priceUsd']),
                    'volume_24h': float(best_pair['volume']['h24']),
                    'price_change_24h': float(best_pair['priceChange']['h24']),
                    'liquidity_usd': float(best_pair['liquidity']['usd'])
                }
            else:
                logger.warning(f"DexScreener HTTP ошибка: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка DexScreener: {e}")
    
    return {'error': 'Failed to fetch data'}

async def check_defillama_tvl(session: aiohttp.ClientSession, token: Dict) -> Dict[str, Any]:
    """Проверка TVL с DefiLlama"""
    try:
        if not await rate_limit_check('defillama'):
            logger.warning("Rate limit для DefiLlama, пропуск")
            return {'error': 'Rate limited'}
        
        symbol = token['symbol']
        
        # Пробуем найти протокол
        protocols_url = "https://api.llama.fi/protocols"
        
        async def fetch_protocols():
            async with session.get(protocols_url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    raise Exception(f"HTTP {resp.status}")
        
        protocols = await retry_request(fetch_protocols)
        
        # Ищем протокол по символу
        protocol = None
        for p in protocols:
            if symbol.lower() in p.get('symbol', '').lower() or symbol.lower() in p.get('name', '').lower():
                protocol = p
                break
        
        if not protocol:
            logger.info(f"DefiLlama: протокол не найден для {symbol}")
            return {'error': 'Protocol not found'}
        
        # Получаем TVL
        tvl_url = f"https://api.llama.fi/protocol/{protocol['slug']}"
        
        async def fetch_tvl():
            async with session.get(tvl_url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    raise Exception(f"HTTP {resp.status}")
        
        tvl_data = await retry_request(fetch_tvl)
        
        if 'tvl' in tvl_data:
            return {
                'tvl': tvl_data['tvl'],
                'protocol_name': protocol['name'],
                'protocol_slug': protocol['slug']
            }
        else:
            return {'error': 'No TVL data'}
            
    except Exception as e:
        logger.error(f"Ошибка DefiLlama для {token['symbol']}: {e}")
        return {'error': 'Failed to fetch data'}

async def social_loop(session: aiohttp.ClientSession = None):
    """Бесконечный цикл мониторинга социальных сетей"""
    logger.info("📱 Запуск социального мониторинга в цикле...")
    while True:
        try:
            logger.info("📱 Проверка социальных сетей...")
            result = await check_social(session)
            logger.info(f"✅ Социальный мониторинг завершен: {result}")
            await asyncio.sleep(config.social_config.get('fetch_interval', 900))  # 15 минут по умолчанию
        except Exception as e:
            logger.error(f"❌ Ошибка в social_loop: {e}")
            await asyncio.sleep(60)

@handle_errors("check_social")
@performance_decorator("check_social")
@recovery_decorator("social_monitor")
async def check_social(session: aiohttp.ClientSession = None):
    """
    Проверка социальных данных (Twitter, Telegram, Discord)
    Все ошибки обрабатываются централизованно через error_handler
    """
    logger.info("[SOCIAL] Start social monitoring...")
    try:
        # Проверяем наличие API ключей
        telegram_api_id = os.getenv('TELEGRAM_API_ID')
        telegram_api_hash = os.getenv('TELEGRAM_API_HASH')
        telegram_phone = os.getenv('TELEGRAM_PHONE')
        discord_bot_token = os.getenv('DISCORD_BOT_TOKEN')
        discord_user_token = os.getenv('DISCORD_USER_TOKEN')
        
        has_telegram_api = (telegram_api_id and telegram_api_hash and telegram_phone and 
                           telegram_api_id != 'your_telegram_api_id_here')
        has_discord_token = ((discord_bot_token and discord_bot_token != 'your_discord_bot_token_here') or
                            (discord_user_token and discord_user_token != 'your_discord_user_token_here'))
        
        tasks = []
        
        # Twitter
        tasks.append(check_twitter(session))
        
        # Telegram (только если есть API ключи)
        if has_telegram_api:
            tasks.append(check_telegram())
        else:
            logger.info("[SOCIAL] Telegram API не настроен, пропускаем")
        
        # Discord (только если есть токен)
        if has_discord_token:
            logger.info("[SOCIAL] Discord токен найден, запускаем мониторинг")
            tasks.append(check_discord())
        else:
            logger.info("[SOCIAL] Discord токен не настроен, пропускаем")
        
        # GitHub (всегда доступен)
        logger.info("[SOCIAL] Запускаем GitHub мониторинг")
        tasks.append(check_github())
        
        # Запускаем доступные задачи
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            logger.info("[SOCIAL] Нет доступных источников для мониторинга")
            
    except Exception as e:
        logger.error(f"[SOCIAL] Общая ошибка мониторинга: {e}")
    logger.info("Social мониторинг завершён")
    return {}  # Возвращаем пустой словарь для устойчивости мониторинга

def translate_text(text: str, dest: str = 'en') -> str:
    """Перевод текста с помощью googletrans"""
    if not TRANSLATOR_AVAILABLE:
        logger.warning("Перевод недоступен, возвращаем оригинальный текст")
        return text
    
    try:
        translator = Translator()
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        logger.error(f"Ошибка перевода: {e}")
        return text

async def check_twitter(session: aiohttp.ClientSession = None):
    """Реальный мониторинг Twitter через Twint - только реальные данные"""
    try:
        logger.info("🔄 Запуск реального Twitter мониторинга через Twint...")
        
        # Проверяем доступность twint
        try:
            import twint
            logger.info("✅ Twint доступен")
        except ImportError:
            logger.error("❌ Twint не установлен - Twitter мониторинг отключен")
            return
        
        # Получаем список аккаунтов для мониторинга
        twitter_accounts = config.social_config.get('twitter_accounts', [])
        if not twitter_accounts:
            logger.warning("⚠️ Twitter аккаунты не настроены")
            return
        
        logger.info(f"📊 Мониторинг {len(twitter_accounts)} Twitter аккаунтов")
        
        for account in twitter_accounts:
            try:
                username = account.replace('@', '')
                logger.info(f"🔍 Проверяем аккаунт: @{username}")
                
                # Twitter мониторинг временно отключен (будет включен при покупке официального API)
                logger.info(f"📡 Twitter мониторинг отключен для @{username}")
                continue
                
            except Exception as e:
                log_error(f"Мониторинг Twitter аккаунта {account}", e, {"account": account})
        
        logger.info("✅ Twitter мониторинг завершен")
        
    except Exception as e:
        log_error("Twitter мониторинг", e)
        logger.error("❌ Критическая ошибка в Twitter мониторинге")

async def get_twitter_tweets_snscrape(username: str) -> List:
    """Получение твитов через snscrape - стабильная альтернатива twint"""
    try:
        import snscrape.modules.twitter as sntwitter
        import asyncio
        from datetime import datetime, timedelta
        
        tweets_list = []
        
        # Создаем поисковый запрос для пользователя
        query = f"from:{username}"
        
        # Получаем твиты за последние 24 часа
        try:
            # Используем snscrape для получения твитов
            scraper = sntwitter.TwitterSearchScraper(query)
            
            # Получаем последние 10 твитов
            for i, tweet in enumerate(scraper.get_items()):
                if i >= 10:  # Лимит твитов
                    break
                    
                # Проверяем, что твит не старше 24 часов
                tweet_date = tweet.date
                if tweet_date < datetime.now(tweet_date.tzinfo) - timedelta(hours=24):
                    break
                
                # Создаем объект твита в нужном формате
                tweet_obj = type('Tweet', (), {
                    'id': tweet.id,
                    'username': username,
                    'tweet': tweet.rawContent,
                    'date': tweet_date,
                    'likes': tweet.likeCount,
                    'retweets': tweet.retweetCount,
                    'replies': tweet.replyCount,
                    'url': tweet.url
                })()
                
                tweets_list.append(tweet_obj)
            
            logger.info(f"✅ Получено {len(tweets_list)} твитов для @{username} через snscrape")
            return tweets_list
            
        except Exception as scrape_error:
            logger.error(f"❌ Snscrape ошибка для @{username}: {scrape_error}")
            return []
            
    except Exception as e:
        log_error(f"Snscrape получение твитов для @{username}", e, {"username": username})
        return []

async def analyze_tweet_relevance(tweet_text: str, username: str) -> Dict[str, Any]:
    """Анализ релевантности твита"""
    try:
        text_lower = tweet_text.lower()
        
        # Ключевые слова для токенов
        token_keywords = {
            'FUEL': ['fuel', 'fuel network', 'fuelvm', 'sway'],
            'ARC': ['arc', 'arcdotfun', 'arc protocol'],
            'BID': ['bid', 'creatorbid', 'creator bid'],
            'MANTA': ['manta', 'manta network', 'manta protocol'],
            'ANON': ['anon', 'hey anon', 'anonymous'],
            'URO': ['uro', 'urolithin', 'pumpdot'],
            'XION': ['xion', 'burnt', 'burnt labs'],
            'AI16Z': ['ai16z', 'eliza', 'elizaos'],
            'SAHARA': ['sahara', 'sahara labs', 'sahara ai'],
            'VIRTUAL': ['virtual', 'virtuals', 'virtuals.io']
        }
        
        # Ключевые слова для алертов
        alert_keywords = {
            'CRITICAL': ['launch', 'mainnet', 'airdrop', 'token', 'listing', 'partnership', 'announcement'],
            'HIGH': ['update', 'release', 'upgrade', 'migration', 'staking', 'governance'],
            'MEDIUM': ['development', 'progress', 'milestone', 'community', 'ecosystem'],
            'LOW': ['news', 'info', 'reminder', 'community']
        }
        
        # Определяем релевантный токен
        relevant_token = None
        for token, keywords in token_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                relevant_token = token
                break
        
        if not relevant_token:
            return {'is_relevant': False}
        
        # Определяем уровень алерта
        alert_level = 'LOW'
        for level, keywords in alert_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                alert_level = level
                break
        
        return {
            'is_relevant': True,
            'token_symbol': relevant_token,
            'alert_level': alert_level,
            'keywords_found': [k for k in token_keywords[relevant_token] if k in text_lower]
        }
        
    except Exception as e:
        log_error("Анализ релевантности твита", e, {"tweet_text": tweet_text[:100]})
        return {'is_relevant': False}

async def analyze_tweet_with_ai(tweet_text: str, token_symbol: str) -> Dict[str, Any]:
    """AI анализ твита"""
    try:
        if not OPENAI_API_KEY:
            return {'ai_analysis': 'OpenAI API не настроен'}
        
        prompt = f"""
        Проанализируй этот твит о криптовалюте {token_symbol}:
        
        Текст: {tweet_text}
        
        Предоставь анализ в формате JSON:
        {{
            "sentiment": "positive/negative/neutral",
            "importance": "high/medium/low",
            "impact_on_price": "bullish/bearish/neutral",
            "key_points": ["пункт1", "пункт2"],
            "recommendation": "краткая рекомендация"
        }}
        """
        
        analysis = await analyze_with_chatgpt(prompt, "tweet_analysis")
        
        if analysis and 'choices' in analysis:
            try:
                import json
                content = analysis['choices'][0]['message']['content']
                return json.loads(content)
            except:
                return {'ai_analysis': content}
        
        return {'ai_analysis': 'Ошибка AI анализа'}
        
    except Exception as e:
        log_error("AI анализ твита", e, {"token_symbol": token_symbol})
        return {'ai_analysis': 'Ошибка AI анализа'}

async def send_twitter_alert_to_telegram(tweet_text: str, username: str, token_symbol: str, 
                                       alert_level: str, link: str, ai_analysis: Dict[str, Any]):
    """Отправка Twitter алерта в Telegram"""
    try:
        # Создаем сообщение
        message = f"""
🚨 **{alert_level} ALERT: {token_symbol}**

**Твит от @{username}:**
{tweet_text}

**AI Анализ:**
• Настроение: {ai_analysis.get('sentiment', 'N/A')}
• Важность: {ai_analysis.get('importance', 'N/A')}
• Влияние на цену: {ai_analysis.get('impact_on_price', 'N/A')}
• Ключевые моменты: {', '.join(ai_analysis.get('key_points', []))}

**Рекомендация:** {ai_analysis.get('recommendation', 'N/A')}

🔗 [Ссылка на твит]({link})
        """
        
        # Отправляем в Telegram
        await send_alert(alert_level, message, token_symbol, {
            'source': 'Twitter',
            'username': username,
            'link': link,
            'ai_analysis': ai_analysis
        })
        
        logger.info(f"✅ Twitter алерт отправлен в Telegram для {token_symbol}")
        
    except Exception as e:
        log_error("Отправка Twitter алерта в Telegram", e, {
            'username': username,
            'token_symbol': token_symbol
        })

def was_tweet_processed(tweet_hash: str) -> bool:
    """Проверяет, был ли твит уже обработан"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 1 FROM processed_tweets WHERE tweet_hash = ?
            ''', (tweet_hash,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка проверки обработанного твита: {e}")
        return False

def mark_tweet_as_processed(tweet_hash: str):
    """Отмечает твит как обработанный"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO processed_tweets (tweet_hash, processed_at)
                VALUES (?, CURRENT_TIMESTAMP)
            ''', (tweet_hash,))
    except Exception as e:
        logger.error(f"Ошибка отметки твита как обработанного: {e}")
        
        logger.info("✅ Twitter мониторинг завершен")
                    
    except Exception as e:
        log_error("Twitter мониторинг", e)

async def check_telegram():
    """Мониторинг Telegram через Telethon"""
    try:
        # Проверяем наличие токенов
        api_id = os.getenv('TELEGRAM_API_ID')
        api_hash = os.getenv('TELEGRAM_API_HASH')
        phone = os.getenv('TELEGRAM_PHONE')
        
        # Проверяем корректность API ID
        if not api_id or api_id == 'your_telegram_api_id':
            logger.warning("TELEGRAM_API_ID не настроен или имеет значение по умолчанию")
            return
            
        try:
            api_id_int = int(api_id)
        except ValueError:
            logger.error(f"Некорректный TELEGRAM_API_ID: {api_id}. Должен быть числом")
            return
        
        if not all([api_id, api_hash, phone]) or api_hash == 'your_telegram_api_hash' or phone == 'your_phone_number':
            logger.warning("Telegram токены не настроены корректно, пропускаем")
            return
            
        # Инициализация клиента
        client = TelegramClient('crypto_monitor_session', api_id_int, api_hash)
        
        try:
            await client.start(phone=phone)
            logger.info("Telegram клиент подключен")
            
            # Получаем список каналов для мониторинга
            channels = config.social_config.get('telegram_channels', [])
            if not channels:
                logger.info("Telegram каналы не настроены")
                return
                
            for channel_id in channels:
                try:
                    # Получаем последние сообщения из канала
                    channel = await client.get_entity(channel_id)
                    messages = await client.get_messages(channel, limit=50)
                    
                    for message in messages:
                        if not message.text:
                            continue
                            
                        text = message.text.lower()
                        # Фильтрация по ключевым словам
                        token_terms = [k.lower() for k in config.social_config['keywords']]
                        alert_terms = sum([config.social_config['alert_keywords'][lvl] for lvl in config.social_config['alert_keywords']], [])
                        
                        if any(term in text for term in token_terms) and any(word in text for word in alert_terms):
                            # Определяем уровень алерта
                            level = None
                            for lvl, words in config.social_config['alert_keywords'].items():
                                if any(word in text for word in words):
                                    level = lvl
                                    break
                            if not level:
                                level = 'INFO'
                                
                            # Перевод
                            translated = translate_text(message.text, dest=config.social_config['translate_to'])
                            # Ссылка на сообщение
                            link = f"https://t.me/{channel.username}/{message.id}" if channel.username else ""
                            
                            # Отправка алерта
                            await send_social_alert(
                                level,
                                'Telegram',
                                message.text,
                                translated,
                                link,
                                token='FUEL' if 'fuel' in text else ('ARC' if 'arc' in text else ('BID' if 'bid' in text or 'creatorbid' in text else ('MANTA' if 'manta' in text else ('ANON' if 'anon' in text or 'hey anon' in text else '')))),
                                keywords=[w for w in token_terms if w in text] + [w for w in alert_terms if w in text]
                            )
                            
                except Exception as e:
                    logger.error(f"Ошибка мониторинга канала {channel_id}: {e}")
                    
        finally:
            await client.disconnect()
            
    except Exception as e:
        logger.error(f"[SOCIAL] Telegram monitoring error: {e}")

async def check_discord():
    """Улучшенный мониторинг Discord с AI-анализом"""
    try:
        logger.info("🔍 [DISCORD] Начинаем мониторинг Discord серверов...")
        
        # Получаем user token из конфигурации
        discord_token = config.social_config.get('discord_token')
        if not discord_token:
            logger.warning("Discord токен не настроен, пропускаем")
            return
            
        # Временно отключаем Discord мониторинг из-за проблем с токеном
        logger.warning("Discord мониторинг временно отключен из-за проблем с токеном")
        return

        try:
            import discord
        except ImportError:
            logger.error("discord.py-self не установлен. Установите: pip3 install -U discord.py-self")
            return

        # Проверяем формат токена
        if not discord_token.startswith('MTA') and not discord_token.startswith('MTI'):
            logger.error("Неверный формат Discord токена. Ожидается user token")
            return

        # Инициализация клиента (селфбот)
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.message_content = True
        intents.guild_messages = True
        intents.direct_messages = True
        
        client = discord.Client(intents=intents)

        # Целевые каналы для мониторинга
        target_channels = [
            'announcements', 'general', 'chat', 'community', 
            'info', 'launch', 'news', 'updates', 'alpha', 'beta',
            'testnet', 'mainnet', 'mint', 'airdrop', 'whitelist',
            'trading', 'price', 'market', 'analysis'
        ]
        
        # Кэш для отслеживания уже обработанных сообщений
        cache_file = 'discord_messages_cache.json'
        processed_messages = {}
        
        try:
            with open(cache_file, 'r') as f:
                processed_messages = json.load(f)
        except FileNotFoundError:
            processed_messages = {}

        done = False
        messages_processed = 0

        @client.event
        async def on_ready():
            nonlocal done, messages_processed
            logger.info(f"🤖 Discord селфбот подключен как {client.user}")
            
            try:
                available_servers = client.guilds
                logger.info(f"📋 Доступные серверы: {[s.name for s in available_servers]}")
                
                for server in available_servers:
                    server_name_lower = server.name.lower()
                    # Расширенная проверка релевантных серверов
                    relevant_keywords = ['fuel', 'arc', 'crypto', 'blockchain', 'defi', 'nft', 'web3', 'dao']
                    
                    if any(keyword.lower() in server_name_lower for keyword in relevant_keywords):
                        logger.info(f"🎯 Мониторинг сервера: {server.name}")
                        
                        for channel in server.text_channels:
                            if not isinstance(channel, discord.TextChannel):
                                continue
                                
                            # Проверяем, является ли канал целевым
                            channel_name_lower = channel.name.lower()
                            is_target = any(target in channel_name_lower for target in target_channels)
                            
                            if is_target:
                                logger.info(f"📢 Сканируем канал: {channel.name}")
                                
                                try:
                                    # Получаем последние сообщения (увеличиваем лимит)
                                    messages = await channel.history(limit=50).flatten()
                                    
                                    for message in messages:
                                        if not message.content or len(message.content.strip()) < 10:
                                            continue
                                            
                                        # Проверяем, не обрабатывали ли мы уже это сообщение
                                        message_key = f"{server.id}_{channel.id}_{message.id}"
                                        if message_key in processed_messages:
                                            continue
                                            
                                        text = message.content.lower()
                                        token_terms = [k.lower() for k in config.social_config['keywords']]
                                        alert_terms = sum([config.social_config['alert_keywords'][lvl] for lvl in config.social_config['alert_keywords']], [])
                                        
                                        # Улучшенная логика определения важности
                                        if any(term in text for term in token_terms):
                                            # Определяем уровень важности
                                            level = 'INFO'
                                            for lvl, words in config.social_config['alert_keywords'].items():
                                                if any(word in text for word in words):
                                                    level = lvl.upper()
                                                    break
                                            
                                            # AI-анализ важности сообщения
                                            try:
                                                ai_analysis = await analyze_discord_message_with_ai(message.content, server.name, channel.name)
                                                if ai_analysis.get('should_alert', False):
                                                    level = ai_analysis.get('level', level)
                                                    logger.info(f"🤖 AI рекомендует уровень: {level}")
                                            except Exception as e:
                                                logger.warning(f"Ошибка AI-анализа Discord сообщения: {e}")
                                            
                                            # Переводим сообщение
                                            translated = translate_text(message.content, dest=config.social_config['translate_to'])
                                            
                                            # Формируем ссылку
                                            link = f"https://discord.com/channels/{server.id}/{channel.id}/{message.id}"
                                            
                                            # Определяем токен
                                            token = ''
                                            if 'fuel' in text:
                                                token = 'FUEL'
                                            elif 'arc' in text:
                                                token = 'ARC'
                                            elif 'bid' in text or 'creatorbid' in text:
                                                token = 'BID'
                                            elif 'manta' in text:
                                                token = 'MANTA'
                                            elif 'anon' in text or 'hey anon' in text:
                                                token = 'ANON'
                                            
                                            # Отправляем алерт
                                            await send_social_alert(
                                                level,
                                                'Discord',
                                                message.content,
                                                translated,
                                                link,
                                                token=token,
                                                keywords=[w for w in token_terms if w in text] + [w for w in alert_terms if w in text]
                                            )
                                            
                                            # Помечаем сообщение как обработанное
                                            processed_messages[message_key] = {
                                                'timestamp': datetime.now().isoformat(),
                                                'level': level,
                                                'server': server.name,
                                                'channel': channel.name
                                            }
                                            
                                            messages_processed += 1
                                            
                                except Exception as e:
                                    logger.error(f"Ошибка мониторинга канала {channel.name}: {e}")
                                    
            except Exception as e:
                logger.error(f"Ошибка мониторинга Discord серверов: {e}")
            finally:
                # Сохраняем кэш
                try:
                    with open(cache_file, 'w') as f:
                        json.dump(processed_messages, f, indent=2)
                except Exception as e:
                    logger.error(f"Ошибка сохранения кэша Discord: {e}")
                
                logger.info(f"✅ Discord мониторинг завершен. Обработано сообщений: {messages_processed}")
                done = True
                await client.close()

        # Улучшенное подключение с несколькими попытками
        connection_success = False
        
        # Попытка 1: Стандартный способ
        try:
            logger.info("🔄 Попытка подключения к Discord (способ 1)...")
            await client.start(discord_token)
            connection_success = True
        except Exception as e:
            logger.warning(f"Способ 1 не удался: {e}")
            
            # Попытка 2: Альтернативный способ
            try:
                logger.info("🔄 Попытка подключения к Discord (способ 2)...")
                await client.login(discord_token)
                await client.connect()
                connection_success = True
            except Exception as e2:
                logger.warning(f"Способ 2 не удался: {e2}")
                
                # Попытка 3: С дополнительными параметрами
                try:
                    logger.info("🔄 Попытка подключения к Discord (способ 3)...")
                    client = discord.Client(intents=intents, self_bot=True)
                    await client.start(discord_token)
                    connection_success = True
                except Exception as e3:
                    logger.error(f"Все способы подключения не удались: {e3}")
        
        if connection_success:
            timeout = 60
            start_time = time.time()
            while not done and (time.time() - start_time) < timeout:
                await asyncio.sleep(1)
            if not done:
                logger.warning("Discord мониторинг завершен по таймауту")
                await client.close()
        else:
            logger.error("Не удалось подключиться к Discord")
            
    except Exception as e:
        logger.error(f"[SOCIAL] Discord monitoring error: {e}")

async def analyze_discord_message_with_ai(message_content: str, server_name: str, channel_name: str) -> Dict[str, Any]:
    """AI-анализ важности Discord сообщения"""
    try:
        if not OPENAI_API_KEY or OPENAI_API_KEY == 'your_openai_api_key_here':
            return {'should_alert': True, 'level': 'INFO'}
        
        prompt = f"""
        Проанализируй это сообщение из Discord сервера криптовалютного проекта:

        Сервер: {server_name}
        Канал: {channel_name}
        Сообщение: {message_content}

        Оцени важность этого сообщения для криптовалют FUEL и ARC:

        КРИТЕРИИ ВАЖНОСТИ:
        - CRITICAL: анонсы релизов, критические обновления, проблемы безопасности
        - HIGH: новые функции, партнерства, листинги, важные обновления
        - MEDIUM: общие новости, обсуждения, технические детали
        - LOW: обычные чаты, мемы, спам

        Ответь в формате JSON:
        {{
            "should_alert": true/false,
            "level": "CRITICAL/HIGH/MEDIUM/LOW",
            "reason": "обоснование на русском"
        }}
        """
        
        response = await analyze_with_chatgpt(prompt, "discord_analysis")
        
        if response and 'choices' in response:
            analysis_text = response['choices'][0]['message']['content']
            try:
                import json
                import re
                
                # Убираем markdown обрамление если есть
                cleaned_text = analysis_text.strip()
                if cleaned_text.startswith('```json'):
                    cleaned_text = cleaned_text[7:]  # Убираем ```json
                if cleaned_text.startswith('```'):
                    cleaned_text = cleaned_text[3:]  # Убираем ```
                if cleaned_text.endswith('```'):
                    cleaned_text = cleaned_text[:-3]  # Убираем ```
                
                cleaned_text = cleaned_text.strip()
                
                analysis = json.loads(cleaned_text)
                return analysis
            except json.JSONDecodeError:
                logger.error(f"Ошибка парсинга JSON от ChatGPT для Discord: {analysis_text}")
                return {'should_alert': True, 'level': 'INFO'}
        else:
            return {'should_alert': True, 'level': 'INFO'}
            
    except Exception as e:
        logger.error(f"Ошибка AI-анализа Discord сообщения: {e}")
        return {'should_alert': True, 'level': 'INFO'}

async def analyze_github_changes_with_ai(commit_data: Dict[str, Any], repo_info: Dict[str, str]) -> Dict[str, Any]:
    """AI анализ изменений в GitHub с помощью OpenAI"""
    try:
        logger.info(f"🤖 Начинаем AI анализ коммита {commit_data['sha'][:8]} в {repo_info['owner']}/{repo_info['repo']}")
        
        if not OPENAI_API_KEY or OPENAI_API_KEY == 'your_openai_api_key_here':
            logger.warning("❌ [GITHUB AI] OpenAI API ключ не настроен")
            return {
                'importance': 'low',
                'summary': 'AI анализ недоступен - нет API ключа',
                'impact': 'Неизвестно',
                'should_alert': False,
                'reason': 'No OpenAI API key'
            }
        
        # Формируем контекст для AI анализа
        files_info = ""
        if 'files' in commit_data and commit_data['files']:
            files_info = "\nИзмененные файлы:\n"
            for file_info in commit_data['files'][:10]:  # Показываем первые 10 файлов
                files_info += f"- {file_info['filename']} (+{file_info.get('additions', 0)}/-{file_info.get('deletions', 0)})\n"
        
        # Безопасное извлечение данных коммита
        author_name = commit_data.get('commit', {}).get('author', {}).get('name', 'Unknown')
        author_date = commit_data.get('commit', {}).get('author', {}).get('date', 'Unknown')
        commit_message = commit_data.get('commit', {}).get('message', 'No message')
        
        context = f"""
        Репозиторий: {repo_info['owner']}/{repo_info['repo']}
        Коммит: {commit_data['sha'][:8]}
        Автор: {author_name}
        Дата: {author_date}
        Сообщение: {commit_message}
        
        Статистика изменений:
        - Файлов изменено: {len(commit_data.get('files', []))}
        - Строк добавлено: {commit_data.get('stats', {}).get('additions', 0)}
        - Строк удалено: {commit_data.get('stats', {}).get('deletions', 0)}
        - Общий размер: {commit_data.get('stats', {}).get('total', 0)} строк{files_info}
        """
        
        # Промпт для анализа
        prompt = f"""
        Проанализируй это изменение в GitHub репозитории криптовалютного проекта:

        {context}

        Оцени важность этого изменения для криптовалют FUEL и ARC:

        КРИТЕРИИ ВАЖНОСТИ:
        - CRITICAL: релизы, критические исправления безопасности, крупные обновления протокола
        - HIGH: новые функции, значительные изменения в коде, обновления документации
        - MEDIUM: мелкие исправления, обновления зависимостей, рефакторинг
        - LOW: правки опечаток, косметические изменения, обновления README

        КРИТЕРИИ ВЛИЯНИЯ:
        - POSITIVE: новые функции, улучшения производительности, исправления багов
        - NEGATIVE: удаление функций, потенциальные проблемы безопасности
        - NEUTRAL: рефакторинг, документация, косметические изменения

        Ответь в формате JSON:
        {{
            "importance": "critical/high/medium/low",
            "impact": "positive/negative/neutral", 
            "should_alert": true/false,
            "summary": "краткое описание изменений на русском",
            "reason": "обоснование важности на русском",
            "affected_tokens": ["FUEL", "ARC"],
            "technical_details": "технические детали изменений"
        }}
        """
        
        logger.info("📤 Отправляем запрос в OpenAI...")
        response = await analyze_with_chatgpt(prompt, "github_analysis")
        
        if response and 'choices' in response:
            analysis_text = response['choices'][0]['message']['content']
            logger.info(f"📥 Получен ответ от OpenAI: {analysis_text[:200]}...")
            
            try:
                # Парсим JSON ответ (обрабатываем markdown формат)
                import json
                import re
                
                # Убираем markdown обрамление если есть
                cleaned_text = analysis_text.strip()
                if cleaned_text.startswith('```json'):
                    cleaned_text = cleaned_text[7:]  # Убираем ```json
                if cleaned_text.startswith('```'):
                    cleaned_text = cleaned_text[3:]  # Убираем ```
                if cleaned_text.endswith('```'):
                    cleaned_text = cleaned_text[:-3]  # Убираем ```
                
                cleaned_text = cleaned_text.strip()
                
                analysis = json.loads(cleaned_text)
                logger.info(f"✅ AI анализ успешен: важность={analysis.get('importance')}, влияние={analysis.get('impact')}")
                return analysis
            except json.JSONDecodeError:
                logger.error(f"❌ Ошибка парсинга JSON от ChatGPT: {analysis_text}")
                return {
                    'importance': 'medium',
                    'summary': 'Ошибка AI анализа',
                    'impact': 'neutral',
                    'should_alert': True,
                    'reason': 'AI analysis failed'
                }
        else:
            logger.warning("⚠️ OpenAI не вернул ответ")
            return {
                'importance': 'medium',
                'summary': 'AI анализ недоступен',
                'impact': 'neutral',
                'should_alert': True,
                'reason': 'AI analysis unavailable'
            }
            
    except Exception as e:
        logger.error(f"Ошибка AI анализа GitHub изменений: {e}")
        return {
            'importance': 'medium',
            'summary': 'Ошибка анализа',
            'impact': 'neutral',
            'should_alert': True,
            'reason': f'Analysis error: {str(e)}'
        }

async def check_github():
    """Мониторинг GitHub репозиториев с AI анализом"""
    try:
        logger.info("🔍 [GITHUB] Начинаем мониторинг GitHub репозиториев...")
        
        # Получаем список GitHub аккаунтов для мониторинга
        github_accounts = config.social_config.get('github_accounts', [])
        if not github_accounts:
            logger.info("GitHub аккаунты не настроены")
            return
            
        # Кэш для отслеживания уже обработанных коммитов
        cache_file = 'github_commits_cache.json'
        processed_commits = {}
        
        try:
            with open(cache_file, 'r') as f:
                processed_commits = json.load(f)
        except FileNotFoundError:
            processed_commits = {}
            
        async with aiohttp.ClientSession() as session:
            for repo_url in github_accounts:
                try:
                    # Извлекаем owner/repo из URL
                    if 'github.com' in repo_url:
                        parts = repo_url.split('github.com/')[-1].split('/')
                        if len(parts) >= 2:
                            owner = parts[0]
                            repo = parts[1]
                            repo_info = {'owner': owner, 'repo': repo}
                            
                            # GitHub API для получения последних коммитов с детальной информацией
                            api_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
                            headers = {
                                'User-Agent': 'CryptoMonitor/1.0',
                                'Accept': 'application/vnd.github.v3+json'
                            }
                            
                            # Добавляем токен если есть
                            github_token = os.getenv('GITHUB_TOKEN')
                            if github_token:
                                headers['Authorization'] = f'token {github_token}'
                            
                            async with session.get(api_url, headers=headers) as response:
                                if response.status == 200:
                                    commits = await response.json()
                                    
                                    if commits:
                                        latest_commit = commits[0]
                                        commit_message = latest_commit['commit']['message']
                                        commit_date = latest_commit['commit']['author']['date']
                                        
                                        # Получаем детальную информацию о коммите
                                        commit_sha = latest_commit['sha']
                                        commit_detail_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
                                        
                                        async with session.get(commit_detail_url, headers=headers) as detail_response:
                                            if detail_response.status == 200:
                                                detailed_commit = await detail_response.json()
                                            else:
                                                detailed_commit = latest_commit
                                        
                                        # Проверяем, не слишком ли старый коммит (последние 24 часа)
                                        commit_time = datetime.fromisoformat(commit_date.replace('Z', '+00:00'))
                                        if datetime.now(commit_time.tzinfo) - commit_time < timedelta(hours=24):
                                            
                                            # Проверяем, не обрабатывали ли мы уже этот коммит
                                            repo_key = f"{owner}/{repo}"
                                            commit_sha = latest_commit['sha']
                                            
                                            if repo_key not in processed_commits:
                                                processed_commits[repo_key] = []
                                            
                                            if commit_sha in processed_commits[repo_key]:
                                                logger.info(f"Коммит {commit_sha[:8]} уже обработан для {repo_key}")
                                                continue
                                            
                                            # AI анализ важности изменений
                                            ai_analysis = await analyze_github_changes_with_ai(detailed_commit, repo_info)
                                            logger.info(f"📊 Результат AI анализа: {ai_analysis}")
                                            
                                            # Проверяем, нужно ли отправлять алерт
                                            if ai_analysis.get('should_alert', False):
                                                # Определяем уровень алерта на основе AI анализа
                                                importance = ai_analysis.get('importance', 'medium')
                                                level_map = {
                                                    'critical': 'CRITICAL',
                                                    'high': 'HIGH', 
                                                    'medium': 'MEDIUM',
                                                    'low': 'INFO'
                                                }
                                                level = level_map.get(importance, 'MEDIUM')
                                                
                                                # Перевод сообщения коммита
                                                translated = translate_text(commit_message, dest=config.social_config['translate_to'])
                                                
                                                # Ссылка на коммит
                                                commit_link = f"https://github.com/{owner}/{repo}/commit/{latest_commit['sha']}"
                                                
                                                # Формируем AI-улучшенное сообщение
                                                ai_summary = ai_analysis.get('summary', '')
                                                ai_reason = ai_analysis.get('reason', '')
                                                technical_details = ai_analysis.get('technical_details', '')
                                                impact = ai_analysis.get('impact', 'neutral')
                                                
                                                # Эмодзи для разных типов влияния
                                                impact_emoji = {
                                                    'positive': '🚀',
                                                    'negative': '⚠️',
                                                    'neutral': '📝'
                                                }.get(impact, '📝')
                                                
                                                # Формируем короткое сообщение
                                                impact_emoji = {
                                                    'positive': '🚀',
                                                    'negative': '⚠️',
                                                    'neutral': '📝'
                                                }.get(impact, '📝')
                                                
                                                # Короткое резюме на русском
                                                short_summary = ai_summary[:200] + "..." if len(ai_summary) > 200 else ai_summary
                                                
                                                alert_message = f"{impact_emoji} <b>GitHub: {owner}/{repo}</b>\n\n"
                                                alert_message += f"{short_summary}\n\n"
                                                alert_message += f"🔗 {commit_link}"
                                                
                                                # Отправляем в Telegram
                                                await send_github_alert(alert_message, level, commit_link, repo_info)
                                                
                                                logger.info(f"GitHub алерт отправлен: {importance} - {owner}/{repo}")
                                            else:
                                                logger.info(f"GitHub изменение пропущено (не важно): {owner}/{repo}")
                                            
                                            # Сохраняем коммит как обработанный
                                            processed_commits[repo_key].append(commit_sha)
                                            
                                            # Ограничиваем размер кэша (храним последние 100 коммитов)
                                            if len(processed_commits[repo_key]) > 100:
                                                processed_commits[repo_key] = processed_commits[repo_key][-100:]
                                                
                                else:
                                    logger.warning(f"GitHub API error для {repo_url}: {response.status}")
                                    
                except Exception as e:
                    logger.error(f"Ошибка мониторинга GitHub репозитория {repo_url}: {e}")
        
        # Сохраняем кэш обработанных коммитов
        try:
            with open(cache_file, 'w') as f:
                json.dump(processed_commits, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения GitHub кэша: {e}")
                    
    except Exception as e:
        logger.error(f"[SOCIAL] GitHub monitoring error: {e}")

async def send_github_alert(message: str, level: str, commit_link: str, repo_info: Dict[str, str]):
    """Отправка GitHub алерта в Telegram"""
    try:
        # Сохранение в БД
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO social_alerts (timestamp, source, level, original_text, translated_text, link, token, keywords, important_news)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            'GitHub',
            level,
            f"Repository: {repo_info['owner']}/{repo_info['repo']}",
            message,
            commit_link,
            'FUEL' if 'fuel' in repo_info['repo'].lower() else ('ARC' if 'arc' in repo_info['repo'].lower() else ''),
            json.dumps(['github', 'development', 'update']),
            1 if level in ['CRITICAL', 'HIGH'] else 0
        ))
        
        conn.commit()
        conn.close()
        
        # Отправляем в Telegram
        telegram_url = f"https://api.telegram.org/bot{config.api_config['telegram']['bot_token']}/sendMessage"
        payload = {
            'chat_id': config.api_config['telegram']['chat_id'],
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(telegram_url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ошибка отправки GitHub алерта: {response.status}")
                    
        logger.info(f"GitHub алерт отправлен: {level} - {repo_info['owner']}/{repo_info['repo']}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки GitHub алерта: {e}")

async def send_social_alert(level: str, source: str, original_text: str, translated_text: str, link: str = "", token: str = "", keywords: List[str] = None):
    """Отправка социального алерта в Telegram и сохранение в БД с AI анализом"""
    try:
        # AI анализ новости если доступен
        if NEWS_ANALYZER_AVAILABLE:
            try:
                # Анализируем оригинальный текст
                analysis = await analyze_crypto_news(original_text, source)
                
                # Проверяем, нужно ли отправлять алерт
                if not await should_alert_news(analysis):
                    logger.info(f"AI анализатор рекомендует пропустить новость: {analysis.get('reason', '')}")
                    return
                
                # Используем AI-форматированное сообщение
                alert_message = await format_news_alert(analysis, original_text)
                
                # Определяем уровень на основе AI анализа
                ai_level = analysis.get('impact', 'low')
                level = 'HIGH' if ai_level == 'high' else 'MEDIUM' if ai_level == 'medium' else 'INFO'
                
                logger.info(f"AI анализ новости: {ai_level} - {analysis.get('summary', '')[:50]}...")
                
            except Exception as e:
                logger.warning(f"Ошибка AI анализа новости: {e}, используем стандартный формат")
                alert_message = None
        else:
            alert_message = None
        
        # Если AI недоступен или произошла ошибка, используем стандартный формат
        if not alert_message:
            emoji_map = {
                'INFO': '📱',
                'MEDIUM': '⚠️',
                'HIGH': '🚨',
                'CRITICAL': '🔥'
            }
            
            emoji = emoji_map.get(level, '📊')
            
            alert_message = f"{emoji} <b>{level.upper()} - {source.upper()}</b>\n\n"
            alert_message += f"<b>Оригинал:</b>\n{original_text[:500]}...\n\n"
            alert_message += f"<b>Перевод:</b>\n{translated_text[:500]}...\n\n"
            
            if token:
                alert_message += f"<b>Токен:</b> {token}\n"
            if keywords:
                alert_message += f"<b>Ключевые слова:</b> {', '.join(keywords[:5])}\n"
            if link:
                alert_message += f"<b>Ссылка:</b> {link}\n"
        
        # Сохранение в БД
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO social_alerts (timestamp, source, level, original_text, translated_text, link, token, keywords, important_news)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            source,
            level,
            original_text,
            translated_text,
            link,
            token,
            json.dumps(keywords or []),
            1 if level in ['CRITICAL', 'HIGH'] else 0
        ))
        
        conn.commit()
        conn.close()
        
        # Отправляем в Telegram
        telegram_url = f"https://api.telegram.org/bot{config.api_config['telegram']['bot_token']}/sendMessage"
        payload = {
            'chat_id': config.api_config['telegram']['chat_id'],
            'text': alert_message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(telegram_url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ошибка отправки Telegram алерта: {response.status}")
                    
        logger.info(f"Социальный алерт отправлен: {level} - {source}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки социального алерта: {e}")

async def analytics_loop(session: aiohttp.ClientSession):
    """Бесконечный цикл мониторинга аналитики"""
    logger.info("📈 Запуск аналитического мониторинга в цикле...")
    while True:
        try:
            logger.info("📈 Проверка аналитических данных...")
            result = await check_analytics(session)
            
            # Детальное логирование результатов
            for symbol, data in result.items():
                if 'error' not in str(data):
                    logger.info(f"✅ Аналитика для {symbol}: {data}")
                else:
                    logger.warning(f"⚠️ Аналитика ошибка для {symbol}: {data}")
            
            await asyncio.sleep(config.monitoring_config['check_interval'] * 2)  # Аналитика реже
        except Exception as e:
            logger.error(f"❌ Ошибка в analytics_loop: {e}")
            await asyncio.sleep(60)

@handle_errors("check_analytics")
@performance_decorator("check_analytics")
@recovery_decorator("analytics_monitor")
async def check_analytics(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """
    Проверка аналитических данных (DeBank, Arkham, BubbleMaps)
    Все ошибки обрабатываются централизованно через error_handler
    """
    logger.info("Проверка аналитических данных...")
    results = {}
    
    for symbol, token in TOKENS.items():
        try:
            symbol_analytics = {}
            
            # Проверка DeBank (если доступно)
            debank_data = await check_debank_analytics(session, token)
            if debank_data and 'error' not in debank_data:
                symbol_analytics['debank'] = debank_data
            
            # Проверка Arkham (если доступно)
            arkham_data = await check_arkham_analytics(session, token)
            if arkham_data and 'error' not in arkham_data:
                symbol_analytics['arkham'] = arkham_data
            
            # Проверка BubbleMaps (всегда доступно)
            bubblemaps_data = await check_bubblemaps_analytics(session, token)
            if bubblemaps_data and 'error' not in bubblemaps_data:
                symbol_analytics['bubblemaps'] = bubblemaps_data
            
            if symbol_analytics:
                results[symbol] = symbol_analytics
                logger.info(f"Аналитические данные для {symbol}: {list(symbol_analytics.keys())}")
            else:
                results[symbol] = {'note': 'No analytics data available'}
            
        except Exception as e:
            logger.error(f"Ошибка проверки аналитики для {symbol}: {e}")
            results[symbol] = {'error': str(e)}
    
    logger.info("Аналитический мониторинг завершён")
    return results

async def check_debank_analytics(session: aiohttp.ClientSession, token: Dict) -> Dict[str, Any]:
    """Проверка аналитики портфелей (заблокировано - платный API)"""
    try:
        # Заблокировано: DeBank требует платный API ключ
        # В будущем можно раскомментировать и добавить API ключ
        
        # Альтернатива: используем Etherscan для базовой аналитики
        if token['chain'] == 'ethereum':
            etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
            if etherscan_api_key and etherscan_api_key != 'your_etherscan_api_key_here':
                # Получаем количество держателей с Etherscan
                url = f"https://api.etherscan.io/api"
                params = {
                    'module': 'token',
                    'action': 'tokenholderlist',
                    'contractaddress': token['contract'],
                    'page': 1,
                    'offset': 100,
                    'apikey': etherscan_api_key
                }
                
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data['status'] == '1':
                            holders = data['result']
                            total_holders = len(holders)
                            
                            # Простая аналитика на основе держателей
                            return {
                                'total_holders': total_holders,
                                'top_10_concentration': sum(float(h['TokenHolderQuantity']) for h in holders[:10]) / sum(float(h['TokenHolderQuantity']) for h in holders) if holders else 0,
                                'source': 'etherscan_api',
                                'note': 'Basic portfolio analysis from Etherscan'
                            }
        
        # Fallback: базовая информация
        return {
            'note': 'Portfolio analytics disabled - requires paid API',
            'status': 'disabled'
        }
                
    except Exception as e:
        logger.error(f"Ошибка аналитики портфелей: {e}")
        return {'error': 'Failed to fetch data'}

async def check_arkham_analytics(session: aiohttp.ClientSession, token: Dict) -> Dict[str, Any]:
    """Проверка аналитики держателей (заблокировано - платный API)"""
    try:
        # Заблокировано: Arkham требует платный API ключ
        # В будущем можно раскомментировать и добавить API ключ
        
        # Альтернатива: используем CoinGecko для базовой информации
        symbol = token['symbol']
        url = f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}"
        
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                # Базовая информация о токене
                community_data = data.get('community_data', {})
                market_data = data.get('market_data', {})
                
                return {
                    'reddit_subscribers': community_data.get('reddit_subscribers', 0),
                    'twitter_followers': community_data.get('twitter_followers', 0),
                    'market_cap_rank': market_data.get('market_cap_rank', 0),
                    'source': 'coingecko_api',
                    'note': 'Basic token analytics from CoinGecko'
                }
            else:
                logger.warning(f"CoinGecko API error: {resp.status}")
                return {'error': f'HTTP {resp.status}'}
                
    except Exception as e:
        logger.error(f"Ошибка аналитики держателей: {e}")
        return {'error': 'Failed to fetch data'}

async def check_bubblemaps_analytics(session: aiohttp.ClientSession, token: Dict) -> Dict[str, Any]:
    """Проверка визуализации держателей (заблокировано - нет API)"""
    try:
        # Заблокировано: BubbleMaps не имеет публичного API
        # В будущем можно добавить веб-скрапинг или найти альтернативы
        
        # Альтернатива: используем Etherscan для базовой информации о держателях
        if token['chain'] == 'ethereum':
            etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
            if etherscan_api_key and etherscan_api_key != 'your_etherscan_api_key_here':
                url = f"https://api.etherscan.io/api"
                params = {
                    'module': 'token',
                    'action': 'tokenholderlist',
                    'contractaddress': token['contract'],
                    'page': 1,
                    'offset': 10,  # Только топ-10 держателей
                    'apikey': etherscan_api_key
                }
                
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data['status'] == '1':
                            holders = data['result']
                            
                            # Простая аналитика топ держателей
                            top_holders = []
                            for holder in holders[:5]:  # Топ-5
                                top_holders.append({
                                    'address': holder['TokenHolderAddress'],
                                    'balance': float(holder['TokenHolderQuantity']),
                                    'percentage': float(holder['TokenHolderShare'])
                                })
                            
                            return {
                                'top_holders': top_holders,
                                'total_holders': len(holders),
                                'source': 'etherscan_api',
                                'note': 'Basic holder analysis from Etherscan'
                            }
        
        # Fallback: базовая информация
        return {
            'note': 'Holder visualization disabled - no public API available',
            'status': 'disabled'
        }
                
    except Exception as e:
        logger.error(f"Ошибка визуализации держателей: {e}")
        return {'error': 'Failed to fetch data'}

def calculate_total_volume(symbol: str, data: Dict[str, Any]) -> float:
    """Расчет общего объема торгов со всех источников (исправлено)"""
    total_volume = 0.0
    
    try:
        # Суммируем объемы с CEX
        cex_data = data.get('cex', {})
        for exchange in ['bybit', 'okx', 'htx', 'gate']:
            if exchange in cex_data and 'volume_24h' in cex_data[exchange] and 'error' not in cex_data[exchange]:
                volume = float(cex_data[exchange]['volume_24h'])
                if volume > 0:  # Проверяем что объем не нулевой
                    total_volume += volume
        
        # Добавляем объем с DEX
        dex_data = data.get('dex', {})
        if 'dexscreener' in dex_data and 'volume_24h' in dex_data['dexscreener']:
            dex_volume = float(dex_data['dexscreener']['volume_24h'])
            if dex_volume > 0:  # Проверяем что объем не нулевой
                total_volume += dex_volume
        
        # Если все объемы нулевые, возвращаем 0
        if total_volume == 0:
            logger.warning(f"Все объемы для {symbol} равны нулю")
        
        logger.info(f"Общий объем {symbol}: {total_volume:,.2f} USD")
        return total_volume
        
    except Exception as e:
        logger.error(f"Ошибка расчета общего объема для {symbol}: {e}")
        return 0.0

async def get_crypto_news(symbol: str) -> str:
    """Получение последних новостей для токена"""
    try:
        # Используем CryptoPanic API для получения новостей
        url = "https://cryptopanic.com/api/v1/posts/"
        params = {
            'auth_token': os.getenv('CRYPTOPANIC_API_KEY', ''),
            'currencies': symbol,
            'filter': 'hot',
            'public': 'true'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('results'):
                        # Берем первую новость
                        news = data['results'][0]
                        return f"📰 {news['title']} - {news['url']}"
        
        # Fallback: возвращаем общую информацию
        return f"📊 Активность {symbol} отслеживается на всех доступных биржах"
        
    except Exception as e:
        logger.error(f"Ошибка получения новостей: {e}")
        return f"📊 Мониторинг {symbol} активен"

# Импорт нового модуля notifier
try:
    from notifier import send_alert_legacy
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False
    logger.warning("Модуль notifier недоступен, используем fallback")

@handle_errors("send_alert")
@performance_decorator("send_alert")
async def send_alert(level, message, token_symbol=None, context=None):
    """
    Отправка алерта через telegram_bot.py
    """
    try:
        logger.debug(f"Подготовка алерта: уровень={level}, токен={token_symbol}")
        
        # Импортируем функцию из telegram_bot.py
        try:
            from telegram_bot import send_alert_unified
            return await send_alert_unified(level, message, token_symbol, context)
        except ImportError:
            logger.error("Не удалось импортировать send_alert_unified из telegram_bot.py")
            return False
        
    except Exception as e:
        logger.error(f"Ошибка отправки алерта: {e}")
        return False



def save_token_data(symbol: str, data: Dict[str, Any]):
    """Сохраняет данные токена в БД"""
    try:
        # Используем with для соединения
        with sqlite3.connect(DB_PATH) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO token_data (symbol, price, volume_24h, market_cap, holders_count, top_holders, tvl, social_mentions)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    data.get('price'),
                    data.get('volume_24h'),
                    data.get('market_cap'),
                    data.get('holders_count'),
                    json.dumps(data.get('top_holders')) if data.get('top_holders') else None,
                    data.get('tvl'),
                    data.get('social_mentions')
                ))
        # conn.commit() не нужен, with сам коммитит
    except Exception as e:
        logger.error(f"Ошибка сохранения данных токена: {e}")

# --- Новый блок: функция для вычисления резкого изменения объема ---
def get_last_volume(symbol: str, minutes: int = 60) -> float:
    """Получает последний объем за N минут"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT volume_24h FROM realtime_data
                WHERE symbol = ? AND timestamp >= datetime('now', ? || ' minutes')
                ORDER BY timestamp DESC LIMIT 1
            ''', (symbol, -minutes))
            row = cursor.fetchone()
            return row[0] if row else 0.0
    except Exception as e:
        logger.error(f"Ошибка получения объема: {e}")
        return 0.0

def was_alert_sent(symbol: str, volume: float, threshold: float = 0.01) -> bool:
    """Проверяет, был ли отправлен алерт по объему (улучшенная версия)"""
    try:
        cache_key = f"{symbol}_volume_{int(volume)}"
        current_time = time.time()
        
        # Проверяем кэш
        if cache_key in alert_cache:
            last_time = alert_cache[cache_key]
            # Не отправляем повторный алерт в течение 30 минут
            if current_time - last_time < 1800:  # 30 минут
                return True
        
        # Проверяем БД
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM alerts
                WHERE token_symbol = ? AND message LIKE ?
                AND timestamp >= datetime('now', '-30 minutes')
            ''', (symbol, f'%{volume:.0f}%'))
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Кэшируем результат
                alert_cache[cache_key] = current_time
                return True
                
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки алерта по объему: {e}")
        return False

def get_last_price(symbol: str, minutes: int = 60) -> float:
    """Получает последнюю цену за N минут"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT price FROM realtime_data
                WHERE symbol = ? AND timestamp >= datetime('now', ? || ' minutes')
                ORDER BY timestamp DESC LIMIT 1
            ''', (symbol, -minutes))
            row = cursor.fetchone()
            return row[0] if row else 0.0
    except Exception as e:
        logger.error(f"Ошибка получения цены: {e}")
        return 0.0

def was_price_alert_sent(symbol: str, price: float, threshold: float = 0.01) -> bool:
    """Проверяет, был ли отправлен алерт по цене (улучшенная версия)"""
    try:
        cache_key = f"{symbol}_price_{int(price * 1000000)}"  # Умножаем на 1M для точности
        current_time = time.time()
        
        # Проверяем кэш
        if cache_key in alert_cache:
            last_time = alert_cache[cache_key]
            # Не отправляем повторный алерт в течение 15 минут
            if current_time - last_time < 900:  # 15 минут
                return True
        
        # Проверяем БД
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM alerts
                WHERE token_symbol = ? AND message LIKE ?
                AND timestamp >= datetime('now', '-15 minutes')
            ''', (symbol, f'%{price:.6f}%'))
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Кэшируем результат
                alert_cache[cache_key] = current_time
                return True
                
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки алерта по цене: {e}")
        return False

def was_recent_alert_sent(symbol: str, alert_type: str, minutes: int = 120) -> bool:
    """Проверяет, был ли отправлен алерт определенного типа недавно (увеличенное время блокировки)"""
    try:
        cache_key = f"{symbol}_{alert_type}"
        current_time = time.time()
        
        # Проверяем кэш с увеличенным временем блокировки
        if cache_key in last_alert_time:
            last_time = last_alert_time[cache_key]
            # Увеличиваем время блокировки до 2 часов по умолчанию
            block_time = minutes * 60
            if current_time - last_time < block_time:
                logger.debug(f"Алерт {alert_type} для {symbol} заблокирован кэшем (блокировка: {block_time//3600}ч)")
                return True
        
        # Проверяем БД с более точным запросом
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM alerts
                WHERE token_symbol = ? AND level = ?
                AND timestamp >= datetime('now', ? || ' minutes')
                ORDER BY timestamp DESC
            ''', (symbol, alert_type, -minutes))
            count = cursor.fetchone()[0]
            
            if count > 0:
                last_alert_time[cache_key] = current_time
                logger.debug(f"Алерт {alert_type} для {symbol} найден в БД ({count} записей)")
                return True
                
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки недавних алертов: {e}")
        return False

def get_token_alert_cooldown(symbol: str) -> int:
    """Возвращает время блокировки алертов для конкретного токена (в минутах)"""
    # Специальные правила для токенов с частыми уведомлениями
    high_frequency_tokens = ['BID', 'SAHARA', 'AI16Z', 'URO']
    
    if symbol in high_frequency_tokens:
        return 240  # 4 часа для токенов с частыми уведомлениями
    else:
        return 120  # 2 часа по умолчанию

def should_send_alert(symbol: str, alert_type: str, alert_level: str = 'INFO') -> bool:
    """Универсальная функция проверки возможности отправки алерта"""
    try:
        # Получаем время блокировки для токена
        cooldown_minutes = get_token_alert_cooldown(symbol)
        
        # Проверяем недавние алерты
        if was_recent_alert_sent(symbol, alert_type, cooldown_minutes):
            return False
        
        # Дополнительная проверка для критических алертов
        if alert_level == 'ERROR':
            # Для критических алертов уменьшаем время блокировки
            critical_cooldown = 60  # 1 час
            if was_recent_alert_sent(symbol, f"{alert_type}_critical", critical_cooldown):
                return False
        
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки возможности отправки алерта: {e}")
        return True  # В случае ошибки разрешаем отправку

# --- Изменяем check_alerts ---
async def check_alerts(symbol: str, data: Dict[str, Any]):
    """Проверка условий для алертов с новой логикой отслеживания от последнего значения"""
    try:
        logger.debug(f"Проверка алертов для {symbol}")
        
        # Получаем пороги из конфигурации
        price_threshold = config.monitoring_config['price_change_threshold']  # 10%
        volume_threshold = config.monitoring_config['volume_change_threshold']  # 50%
        
        # Собираем все доступные данные с указанием источника
        available_data = []
        
        # Проверяем CEX данные
        if 'cex' in data and data['cex']:
            for exchange, exchange_data in data['cex'].items():
                if isinstance(exchange_data, dict) and 'error' not in exchange_data:
                    if 'price' in exchange_data and 'volume_24h' in exchange_data:
                        try:
                            # Безопасное преобразование в float с валидацией
                            price_raw = exchange_data['price']
                            volume_raw = exchange_data['volume_24h']
                            
                            # Проверяем, что данные не являются строками с текстом
                            if isinstance(price_raw, str) and not price_raw.replace('.', '').replace('-', '').isdigit():
                                logger.warning(f"Некорректная цена для {symbol} с {exchange}: {price_raw}")
                                continue
                                
                            if isinstance(volume_raw, str) and not volume_raw.replace('.', '').replace('-', '').isdigit():
                                logger.warning(f"Некорректный объем для {symbol} с {exchange}: {volume_raw}")
                                continue
                            
                            price = float(price_raw)
                            volume = float(volume_raw)
                            
                            # Валидация данных
                            if price > 0 and volume > 0:
                                available_data.append({
                                    'source': f"cex_{exchange}",
                                    'price': price,
                                    'volume': volume,
                                    'data': exchange_data
                                })
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Ошибка преобразования данных для {symbol} с {exchange}: {e}")
                            continue
        
        # Проверяем DEX данные
        if 'dex' in data and data['dex']:
            for dex_name, dex_data in data['dex'].items():
                if isinstance(dex_data, dict) and 'error' not in dex_data:
                    if 'price' in dex_data and 'volume_24h' in dex_data:
                        try:
                            # Безопасное преобразование в float с валидацией
                            price_raw = dex_data['price']
                            volume_raw = dex_data['volume_24h']
                            
                            # Проверяем, что данные не являются строками с текстом
                            if isinstance(price_raw, str) and not price_raw.replace('.', '').replace('-', '').isdigit():
                                logger.warning(f"Некорректная цена DEX для {symbol} с {dex_name}: {price_raw}")
                                continue
                                
                            if isinstance(volume_raw, str) and not volume_raw.replace('.', '').replace('-', '').isdigit():
                                logger.warning(f"Некорректный объем DEX для {symbol} с {dex_name}: {volume_raw}")
                                continue
                            
                            price = float(price_raw)
                            volume = float(volume_raw)
                            
                            if price > 0 and volume > 0:
                                available_data.append({
                                    'source': f"dex_{dex_name}",
                                    'price': price,
                                    'volume': volume,
                                    'data': dex_data
                                })
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Ошибка преобразования DEX данных для {symbol} с {dex_name}: {e}")
                            continue
        
        # Проверяем realtime данные
        if 'realtime_data' in data and data['realtime_data']:
            realtime = data['realtime_data']
            if 'price' in realtime and 'volume_24h' in realtime:
                try:
                    # Безопасное преобразование в float с валидацией
                    price_raw = realtime['price']
                    volume_raw = realtime['volume_24h']
                    
                    # Проверяем, что данные не являются строками с текстом
                    if isinstance(price_raw, str) and not price_raw.replace('.', '').replace('-', '').isdigit():
                        logger.warning(f"Некорректная цена realtime для {symbol}: {price_raw}")
                        return
                        
                    if isinstance(volume_raw, str) and not volume_raw.replace('.', '').replace('-', '').isdigit():
                        logger.warning(f"Некорректный объем realtime для {symbol}: {volume_raw}")
                        return
                    
                    price = float(price_raw)
                    volume = float(volume_raw)
                    
                    if price > 0 and volume > 0:
                        available_data.append({
                            'source': 'realtime',
                            'price': price,
                            'volume': volume,
                            'data': realtime
                        })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Ошибка преобразования realtime данных для {symbol}: {e}")
                    return
        
        if not available_data:
            logger.debug(f"Нет валидных данных для {symbol}")
            return
        
        logger.debug(f"Доступные данные для {symbol}: {len(available_data)} источников")
        
        # УЛУЧШЕННЫЙ ВЫБОР ИСТОЧНИКА ДАННЫХ
        # Приоритизируем надежные биржи
        reliable_exchanges = ['binance', 'bybit', 'okx', 'gate', 'htx']
        
        # Ищем данные с надежных бирж
        reliable_data = [data for data in available_data if any(exchange in data['source'] for exchange in reliable_exchanges)]
        
        if reliable_data:
            # Используем данные с надежных бирж
            best_data = max(reliable_data, key=lambda x: x['volume'])
            current_price = best_data['price']
            current_volume = sum(data['volume'] for data in reliable_data)  # Суммируем только надежные источники
            logger.debug(f"Используем данные с надежных бирж для {symbol}: {best_data['source']} = ${current_price}")
        else:
            # Fallback на все доступные данные
            total_volume = sum(data['volume'] for data in available_data)
            best_data = max(available_data, key=lambda x: x['volume'])
            current_price = best_data['price']
            current_volume = total_volume
            logger.debug(f"Fallback на все источники для {symbol}: {best_data['source']} = ${current_price}")
        
        # ДОПОЛНИТЕЛЬНАЯ ВАЛИДАЦИЯ ЦЕНЫ
        if current_price <= 0 or current_volume <= 0:
            logger.warning(f"Некорректные данные для {symbol}: цена=${current_price}, объем=${current_volume}")
            return
        best_exchange = "all_exchanges"  # Указываем, что это суммарные данные
        
        logger.debug(f"Суммарные данные для {symbol}: цена с {best_data['source']} = ${current_price}, общий объем = ${current_volume:,.0f}")
        
        # Получаем пиковые значения
        peak = get_peak_values(symbol)
        current_time = int(time.time())
        
        # Инициализация пиковых значений при первом запуске
        if peak['last_alert_time'] == 0:
            set_peak_values(symbol, current_price, current_volume)
            logger.debug(f"Инициализированы пиковые значения для {symbol}: цена=${current_price}, объем=${current_volume}")
            # Устанавливаем начальные значения для алертов
            set_peak_values(symbol, current_price, current_volume, 'price')
            set_peak_values(symbol, current_price, current_volume, 'volume')
            
            # При первом запуске устанавливаем начальные значения для новой системы алертов
            set_last_token_value(symbol, current_price, current_volume)
            logger.info(f"Инициализированы начальные значения для {symbol}: цена=${current_price:.6f}, объем=${current_volume:,.0f}")
            
            return
        
        # Проверяем, нужно ли обновить пиковые значения
        if should_update_peak(symbol, current_price, current_volume):
            set_peak_values(symbol, current_price, current_volume)
            logger.debug(f"Обновлены пиковые значения для {symbol}: цена=${current_price}, объем=${current_volume}")
        
        # НОВАЯ СИСТЕМА АЛЕРТОВ: Отслеживание от последнего значения
        
        # Обновляем последние значения токена
        set_last_token_value(symbol, current_price, current_volume)
        
        # Проверяем изменение цены от последнего значения
        if should_send_price_alert_from_last(symbol, current_price, price_threshold):
            last_price = get_last_token_value(symbol, 'price')
            price_change = calculate_change_from_last(current_price, last_price)
            
            # Определяем направление изменения
            if price_change > 0:
                direction = "🚀"
                alert_level = "INFO"
            else:
                direction = "🔻"
                alert_level = "WARNING"
            
            # Формируем сообщение
            alert_message = f"{direction} {symbol} изменился на {abs(price_change):.2f}% от последнего значения\n"
            alert_message += f"💰 Текущая цена: ${current_price:.6f}\n"
            alert_message += f"📊 Объем 24ч: ${current_volume:,.0f}\n"
            alert_message += f"🏪 Источник: {best_data['source']}"
            
            # Отправляем алерт
            await send_alert(alert_level, alert_message, symbol, {
                'price': current_price,
                'volume_24h': current_volume,
                'price_change': price_change,
                'exchange': best_data['source'],
                'last_price': last_price
            })
            
            # Обновляем последнее значение для следующего сравнения
            set_last_token_value(symbol, current_price, current_volume)
            
            logger.info(f"Отправлен алерт по цене для {symbol}: {price_change:+.2f}% от последнего значения")
        
        # Проверяем изменение объема от последнего значения
        if should_send_volume_alert_from_last(symbol, current_volume, volume_threshold):
            last_volume = get_last_token_value(symbol, 'volume')
            volume_change = calculate_change_from_last(current_volume, last_volume)
            
            # Определяем направление изменения
            if volume_change > 0:
                direction = "🚀"
                alert_level = "INFO"
            else:
                direction = "🔻"
                alert_level = "WARNING"
            
            # Формируем сообщение
            alert_message = f"{direction} {symbol} объем изменился на {abs(volume_change):.2f}% от последнего значения\n"
            alert_message += f"📊 Текущий объем: ${current_volume:,.0f}\n"
            alert_message += f"💰 Цена: ${current_price:.6f}\n"
            alert_message += f"🏪 Источник: {best_data['source']}"
            
            # Отправляем алерт
            await send_alert(alert_level, alert_message, symbol, {
                'volume_24h': current_volume,
                'price': current_price,
                'volume_change': volume_change,
                'exchange': best_data['source'],
                'last_volume': last_volume
            })
            
            # Обновляем последнее значение для следующего сравнения
            set_last_token_value(symbol, current_price, current_volume)
            
            logger.info(f"Отправлен алерт по объему для {symbol}: {volume_change:+.2f}% от последнего значения")
        
        logger.debug(f"Проверка алертов завершена для {symbol}")
        
    except Exception as e:
        logger.error(f"Ошибка проверки алертов для {symbol}: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")

async def update_fuel_price_realtime():
    """
    Асинхронно обновляет цену FUEL/USDT с Gate.io в глобальных данных каждые 5 секунд (исправлено)
    """
    url = f"{config.api_config['gate']['base_url']}/spot/tickers?currency_pair=FUEL_USDT"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and data:
                            price = float(data[0]['last'])
                            # Обновляем только глобальные данные, НЕ сохраняем в БД
                            realtime_data['FUEL']['price'] = price
                            realtime_data['FUEL']['last_update'] = datetime.now()
                            realtime_data['FUEL']['source'] = 'Gate.io'
                            logger.info(f"[REALTIME] FUEL price updated from Gate.io: {price}")
                    else:
                        logger.warning(f"[REALTIME] Gate.io FUEL HTTP {resp.status}")
        except Exception as e:
            logger.warning(f"[REALTIME] Gate.io FUEL price error: {e}")
        await asyncio.sleep(5)

async def update_arc_price_realtime():
    """
    Асинхронно обновляет цену ARC/USDT с HTX в глобальных данных каждые 5 секунд (исправлено)
    """
    url = f"https://api.htx.com/market/detail/merged?symbol=arcusdt"
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('status') == 'ok' and 'tick' in data:
                            price = float(data['tick']['close'])
                            # Обновляем только глобальные данные, НЕ сохраняем в БД
                            realtime_data['ARC']['price'] = price
                            realtime_data['ARC']['last_update'] = datetime.now()
                            realtime_data['ARC']['source'] = 'HTX'
                            logger.info(f"[REALTIME] ARC price updated from HTX: {price}")
                    else:
                        logger.warning(f"[REALTIME] HTX ARC HTTP {resp.status}")
        except Exception as e:
            logger.warning(f"[REALTIME] HTX ARC price error: {e}")
        await asyncio.sleep(5)

# Очистка старых кэшей каждые 2 часа
async def cleanup_alert_cache():
    """Очистка старых записей в кэше алертов и БД (улучшенная версия)"""
    while True:
        try:
            current_time = time.time()
            # Удаляем записи старше 4 часов для менее агрессивной очистки
            expired_keys = [k for k, v in alert_cache.items() if current_time - v > 14400]
            for key in expired_keys:
                del alert_cache[key]
            
            expired_time_keys = [k for k, v in last_alert_time.items() if current_time - v > 14400]
            for key in expired_time_keys:
                del last_alert_time[key]
                
            if expired_keys or expired_time_keys:
                logger.debug(f"Очищен кэш алертов: удалено {len(expired_keys)} + {len(expired_time_keys)} записей")
            
            # Очищаем старые алерты из БД (старше 7 дней)
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            DELETE FROM alerts 
                            WHERE timestamp < datetime('now', '-7 days')
                        ''')
                        deleted_count = cursor.rowcount
                        if deleted_count > 0:
                            logger.debug(f"Удалено {deleted_count} старых алертов из БД")
            except Exception as db_error:
                logger.error(f"Ошибка очистки БД алертов: {db_error}")
            
        except Exception as e:
            logger.error(f"Ошибка очистки кэша алертов: {e}")
        
        await asyncio.sleep(3600)  # 1 час вместо 30 минут

async def telegram_tokens_loop():
    """Цикл обновления токенов из Telegram бота"""
    while True:
        try:
            # Обновляем realtime_data токенами из Telegram бота
            update_realtime_data_with_telegram_tokens()
            
            # Ждем 2 минуты перед следующим обновлением
            await asyncio.sleep(120)
        except Exception as e:
            logger.error(f"Ошибка в цикле обновления токенов из Telegram: {e}")
            await asyncio.sleep(60)

# --- AI/ML Sentiment Analysis ---
def analyze_sentiment(text: str) -> Dict[str, float]:
    """Анализ настроений текста с использованием эвристических правил"""
    try:
        # Приводим к нижнему регистру
        text_lower = text.lower()
        
        # Позитивные слова и фразы
        positive_words = [
            'bullish', 'moon', 'pump', 'surge', 'rally', 'breakout', 'uptrend',
            'buy', 'long', 'hodl', 'diamond hands', 'to the moon', 'lambo',
            'success', 'win', 'profit', 'gains', 'positive', 'good', 'great',
            'amazing', 'excellent', 'perfect', 'love', 'like', 'support',
            'partnership', 'adoption', 'growth', 'development', 'launch',
            'mainnet', 'upgrade', 'innovation', 'revolutionary', 'breakthrough'
        ]
        
        # Негативные слова и фразы
        negative_words = [
            'bearish', 'dump', 'crash', 'sell', 'short', 'paper hands',
            'rug', 'scam', 'fake', 'dead', 'dumpster', 'trash', 'garbage',
            'lose', 'loss', 'negative', 'bad', 'terrible', 'awful', 'hate',
            'dislike', 'problem', 'issue', 'bug', 'exploit', 'hack', 'vulnerability',
            'suspended', 'banned', 'delisted', 'bankruptcy', 'liquidation'
        ]
        
        # Подсчитываем позитивные и негативные слова
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        # Вычисляем настроение от -1 до 1
        total_words = positive_count + negative_count
        if total_words == 0:
            sentiment = 0.0  # Нейтральное
        else:
            sentiment = (positive_count - negative_count) / total_words
        
        # Нормализуем к диапазону 0-1
        normalized_sentiment = (sentiment + 1) / 2
        
        # Вычисляем уверенность на основе количества найденных слов
        confidence = min(total_words / 10, 1.0)
        
        return {
            'sentiment': normalized_sentiment,
            'confidence': confidence,
            'positive_count': positive_count,
            'negative_count': negative_count
        }
        
    except Exception as e:
        logger.error(f"Ошибка анализа настроений: {e}")
        return {
            'sentiment': 0.5,
            'confidence': 0.0,
            'positive_count': 0,
            'negative_count': 0
        }

# Кэш для данных настроений
sentiment_cache = {}

def get_cached_sentiment_data(cache_key: str) -> Optional[Dict[str, Any]]:
    """Получение кэшированных данных настроений"""
    try:
        if cache_key in sentiment_cache:
            cached_data, timestamp, duration = sentiment_cache[cache_key]
            if time.time() - timestamp < duration:
                return cached_data
            else:
                # Удаляем устаревшие данные
                del sentiment_cache[cache_key]
        return None
    except Exception as e:
        logger.error(f"Ошибка получения кэша настроений: {e}")
        return None

def set_cached_sentiment_data(cache_key: str, data: Dict[str, Any], duration: int):
    """Сохранение данных настроений в кэш"""
    try:
        sentiment_cache[cache_key] = (data, time.time(), duration)
        
        # Ограничиваем размер кэша (максимум 100 записей)
        if len(sentiment_cache) > 100:
            # Удаляем самые старые записи
            oldest_key = min(sentiment_cache.keys(), 
                           key=lambda k: sentiment_cache[k][1])
            del sentiment_cache[oldest_key]
            
    except Exception as e:
        logger.error(f"Ошибка сохранения кэша настроений: {e}")

async def fetch_reddit_sentiment(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение настроений из Reddit"""
    try:
        reddit_data = []
        
        for subreddit in config.social_config['reddit_subreddits']:
            try:
                # Используем Reddit JSON API (без аутентификации для публичных данных)
                url = f"https://www.reddit.com/{subreddit}/search.json"
                params = {
                    'q': symbol,
                    't': 'day',
                    'limit': 25
                }
                
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'data' in data and 'children' in data['data']:
                            for post in data['data']['children']:
                                post_data = post['data']
                                text = f"{post_data.get('title', '')} {post_data.get('selftext', '')}"
                                sentiment = analyze_sentiment(text)
                                
                                reddit_data.append({
                                    'title': post_data.get('title', ''),
                                    'text': text,
                                    'score': post_data.get('score', 0),
                                    'sentiment': sentiment,
                                    'subreddit': subreddit,
                                    'url': f"https://reddit.com{post_data.get('permalink', '')}"
                                })
                                
            except Exception as e:
                logger.warning(f"Ошибка получения данных из {subreddit}: {e}")
                continue
        
        if reddit_data:
            # Агрегируем результаты
            total_sentiment = sum(item['sentiment']['sentiment'] for item in reddit_data)
            avg_sentiment = total_sentiment / len(reddit_data)
            total_score = sum(item['score'] for item in reddit_data)
            
            return {
                'sentiment_score': (avg_sentiment + 1) / 2,  # Нормализуем к 0-1
                'posts_count': len(reddit_data),
                'total_score': total_score,
                'source': 'reddit',
                'posts': reddit_data[:5]  # Топ 5 постов
            }
        
        return {}
        
    except Exception as e:
        logger.error(f"Ошибка Reddit sentiment: {e}")
        return {}

async def fetch_coingecko_social_data(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение социальных данных из CoinGecko API"""
    try:
        # Маппинг символов для CoinGecko
        symbol_mapping = {
            'FUEL': 'fuel-network',
            'ARC': 'ai-rig-complex',  # AI Rig Complex
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'SOL': 'solana'
        }
        
        coin_id = symbol_mapping.get(symbol, symbol.lower())
        

        
        async with session.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}", timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                community_data = data.get('community_data', {})
                developer_data = data.get('developer_data', {})
                
                # Расчет настроений на основе различных метрик
                twitter_followers = community_data.get('twitter_followers', 0)
                reddit_subscribers = community_data.get('reddit_subscribers', 0)
                reddit_accounts_active = community_data.get('reddit_accounts_active_48h', 0)
                reddit_posts = community_data.get('reddit_average_posts_48h', 0)
                reddit_comments = community_data.get('reddit_average_comments_48h', 0)
                
                # Простая оценка настроений на основе активности
                total_community = twitter_followers + reddit_subscribers
                activity_score = (reddit_accounts_active + reddit_posts + reddit_comments) / max(total_community, 1)
                
                if total_community > 1000000:  # > 1M подписчиков
                    base_sentiment = 0.7
                elif total_community > 100000:  # > 100K подписчиков
                    base_sentiment = 0.6
                elif total_community > 10000:  # > 10K подписчиков
                    base_sentiment = 0.5
                else:
                    base_sentiment = 0.4
                
                # Корректируем на основе активности
                final_sentiment = min(1.0, base_sentiment + (activity_score * 0.3))
                
                return {
                    'sentiment_score': final_sentiment,
                    'social_volume': total_community,
                    'social_contributors': reddit_accounts_active,
                    'social_engagement': reddit_posts + reddit_comments,
                    'twitter_followers': twitter_followers,
                    'reddit_subscribers': reddit_subscribers,
                    'source': 'coingecko'
                }
            else:
                logger.warning(f"CoinGecko API error for {symbol}: {response.status}")
                return {}
                
    except Exception as e:
        logger.error(f"Ошибка CoinGecko API для {symbol}: {e}")
        return {}



async def fetch_crypto_news_sentiment(session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
    """Получение настроений из крипто-новостей"""
    try:
        # Проверяем кэш
        cache_key = f"news_sentiment_{symbol}"
        cached_data = get_cached_sentiment_data(cache_key)
        if cached_data:
            return cached_data
        
        # Получаем новости
        news_data = await fetch_crypto_news(symbol)
        if not news_data:
            return {}
        
        # Анализируем настроения заголовков
        sentiments = []
        for news in news_data[:10]:  # Анализируем первые 10 новостей
            title = news.get('title', '')
            if title:
                sentiment = analyze_sentiment(title)
                sentiments.append(sentiment['sentiment'])
        
        if not sentiments:
            return {}
        
        # Вычисляем среднее настроение
        avg_sentiment = sum(sentiments) / len(sentiments)
        
        result = {
            'sentiment': avg_sentiment,
            'confidence': min(len(sentiments) / 10, 1.0),  # Уверенность на основе количества новостей
            'sources_count': len(sentiments),
            'last_updated': datetime.now().isoformat()
        }
        
        # Кэшируем результат на 30 минут
        set_cached_sentiment_data(cache_key, result, 1800)
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка получения настроений новостей для {symbol}: {e}")
        return {}



async def analyze_social_sentiment(symbol: str) -> Dict[str, Any]:
    """Анализ настроений в социальных сетях"""
    try:
        logger.debug(f"Начало анализа настроений для {symbol}")
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            # Получаем данные из разных источников
            reddit_data = await fetch_reddit_sentiment(session, symbol)
            coingecko_data = await fetch_coingecko_social_data(session, symbol)
            news_data = await fetch_crypto_news_sentiment(session, symbol)
            
            logger.debug(f"Получены данные настроений для {symbol}: Reddit={bool(reddit_data)}, Coingecko={bool(coingecko_data)}, News={bool(news_data)}")
            
            # Объединяем данные
            combined_sentiment = {
                'reddit': reddit_data,
                'coingecko': coingecko_data,
                'news': news_data,
                'overall_sentiment': 'neutral',
                'confidence': 0.5,
                'sources_count': 0
            }
            
            # Анализируем общее настроение
            sentiments = []
            confidences = []
            
            for source, data in [('reddit', reddit_data), ('coingecko', coingecko_data), ('news', news_data)]:
                if data and 'error' not in data:
                    if 'sentiment' in data:
                        sentiments.append(data['sentiment'])
                    if 'confidence' in data:
                        confidences.append(data['confidence'])
                    combined_sentiment['sources_count'] += 1
            
            if sentiments:
                # Определяем общее настроение
                bullish_count = sentiments.count('bullish')
                bearish_count = sentiments.count('bearish')
                neutral_count = sentiments.count('neutral')
                
                if bullish_count > bearish_count and bullish_count > neutral_count:
                    combined_sentiment['overall_sentiment'] = 'bullish'
                elif bearish_count > bullish_count and bearish_count > neutral_count:
                    combined_sentiment['overall_sentiment'] = 'bearish'
                else:
                    combined_sentiment['overall_sentiment'] = 'neutral'
                
                # Средняя уверенность
                if confidences:
                    combined_sentiment['confidence'] = sum(confidences) / len(confidences)
            
            execution_time = time.time() - start_time
            logger.debug(f"Анализ настроений {symbol} завершен за {execution_time:.2f}с: {combined_sentiment['overall_sentiment']} (уверенность: {combined_sentiment['confidence']:.2f})")
            
            return combined_sentiment
            
    except Exception as e:
        logger.error(f"Ошибка анализа настроений для {symbol}: {e}")
        return {'error': str(e)}

# --- Risk Management ---
async def calculate_risk_score(symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Расчет риска токена на основе различных факторов с детализацией и кэшированием"""
    try:
        # Проверяем кэш
        data_hash = calculate_data_hash(data)
        cached_result = get_cached_risk_score(symbol, data_hash)
        if cached_result:
            return cached_result
        
        risk_factors = {}
        total_risk = 0.0
        details = []
        
        # 1. Волатильность цены (0-20 баллов) - УМЕНЬШЕН ВЕС
        price_data = get_price_history(symbol, hours=24)
        if len(price_data) > 1:
            prices = [float(p[1]) for p in price_data]
            volatility = calculate_volatility(prices)
            risk_factors['volatility'] = min(20, volatility * 80)  # Уменьшен коэффициент
            total_risk += risk_factors['volatility']
            details.append(f"📈 Волатильность: {risk_factors['volatility']:.1f}/20 (коэф: {volatility:.3f})")
        else:
            risk_factors['volatility'] = 10  # Средний риск если нет данных
            total_risk += risk_factors['volatility']
            details.append(f"📈 Волатильность: {risk_factors['volatility']:.1f}/20 (нет данных)")
        
        # 2. Ликвидность (0-25 баллов) - УВЕЛИЧЕН ВЕС
        volume_24h = data.get('volume_24h', 0)
        if volume_24h < 50000:  # < 50k USD
            risk_factors['liquidity'] = 25
            details.append(f"💧 Ликвидность: 25/25 (объем: ${volume_24h:,.0f} - КРИТИЧЕСКИ НИЗКИЙ)")
        elif volume_24h < 200000:  # < 200k USD
            risk_factors['liquidity'] = 20
            details.append(f"💧 Ликвидность: 20/25 (объем: ${volume_24h:,.0f} - ОЧЕНЬ НИЗКИЙ)")
        elif volume_24h < 1000000:  # < 1M USD
            risk_factors['liquidity'] = 15
            details.append(f"💧 Ликвидность: 15/25 (объем: ${volume_24h:,.0f} - НИЗКИЙ)")
        elif volume_24h < 5000000:  # < 5M USD
            risk_factors['liquidity'] = 10
            details.append(f"💧 Ликвидность: 10/25 (объем: ${volume_24h:,.0f} - СРЕДНИЙ)")
        elif volume_24h < 20000000:  # < 20M USD
            risk_factors['liquidity'] = 5
            details.append(f"💧 Ликвидность: 5/25 (объем: ${volume_24h:,.0f} - ХОРОШИЙ)")
        else:
            risk_factors['liquidity'] = 0
            details.append(f"💧 Ликвидность: 0/25 (объем: ${volume_24h:,.0f} - ОТЛИЧНЫЙ)")
        total_risk += risk_factors['liquidity']
        
        # 3. Социальные настроения (0-15 баллов) - УЛУЧШЕНА ЛОГИКА
        sentiment_data = await analyze_social_sentiment(symbol)
        sentiment_score = sentiment_data.get('sentiment', 0.5)
        sentiment_confidence = sentiment_data.get('confidence', 0.0)
        sentiment_sources = sentiment_data.get('sources', {})
        
        # Детализация источников настроений
        sentiment_details = []
        if sentiment_sources:
            for source, data in sentiment_sources.items():
                source_score = data.get('sentiment_score', 0.5)
                source_count = data.get('message_count', 0) or data.get('posts_count', 0) or data.get('articles_count', 0) or 0
                sentiment_details.append(f"{source}: {source_score:.2f} ({source_count} сообщений)")
        
        if sentiment_score < 0.3:
            risk_factors['sentiment'] = 15
            details.append(f"📱 Соц. настроения: 15/15 (очень негативные: {sentiment_score:.2f})")
        elif sentiment_score < 0.4:
            risk_factors['sentiment'] = 10
            details.append(f"📱 Соц. настроения: 10/15 (негативные: {sentiment_score:.2f})")
        elif sentiment_score < 0.6:
            risk_factors['sentiment'] = 5
            details.append(f"📱 Соц. настроения: 5/15 (нейтральные: {sentiment_score:.2f})")
        else:
            risk_factors['sentiment'] = 0
            details.append(f"📱 Соц. настроения: 0/15 (позитивные: {sentiment_score:.2f})")
        
        # Добавляем детали источников
        if sentiment_details:
            details.append(f"   📊 Источники: {', '.join(sentiment_details)}")
        else:
            details.append(f"   📊 Источники: нет данных")
        
        details.append(f"   🎯 Уверенность: {sentiment_confidence:.2f}")
        total_risk += risk_factors['sentiment']
        
        # 4. Концентрация держателей (0-15 баллов) - УЛУЧШЕНА ЛОГИКА
        holders_count = data.get('holders_count', 0)
        market_cap = data.get('market_cap', 0)
        
        if holders_count > 0:
            if holders_count < 500:
                risk_factors['concentration'] = 15
                details.append(f"👥 Концентрация: 15/15 (держателей: {holders_count} - ОЧЕНЬ ВЫСОКАЯ)")
            elif holders_count < 2000:
                risk_factors['concentration'] = 12
                details.append(f"👥 Концентрация: 12/15 (держателей: {holders_count} - ВЫСОКАЯ)")
            elif holders_count < 10000:
                risk_factors['concentration'] = 8
                details.append(f"👥 Концентрация: 8/15 (держателей: {holders_count} - СРЕДНЯЯ)")
            else:
                risk_factors['concentration'] = 3
                details.append(f"👥 Концентрация: 3/15 (держателей: {holders_count} - НИЗКАЯ)")
        else:
            # Если нет данных о держателях, используем объем как индикатор
            if volume_24h < 1000000:  # < 1M USD
                risk_factors['concentration'] = 12
                details.append(f"👥 Концентрация: 12/15 (мало держателей/низкий объем)")
            else:
                risk_factors['concentration'] = 8
                details.append(f"👥 Концентрация: 8/15 (средняя концентрация)")
        total_risk += risk_factors['concentration']
        
        # 5. Возраст токена (0-10 баллов) - УЛУЧШЕНА ЛОГИКА
        age_days = data.get('age_days', 180)
        if age_days < 7:
            risk_factors['age'] = 10
            details.append(f"🕒 Возраст токена: 10/10 (новый токен < 7 дней)")
        elif age_days < 30:
            risk_factors['age'] = 8
            details.append(f"🕒 Возраст токена: 8/10 (молодой токен < 30 дней)")
        elif age_days < 90:
            risk_factors['age'] = 6
            details.append(f"🕒 Возраст токена: 6/10 (молодой токен < 90 дней)")
        elif age_days < 365:
            risk_factors['age'] = 4
            details.append(f"🕒 Возраст токена: 4/10 (средний возраст < 1 года)")
        else:
            risk_factors['age'] = 2
            details.append(f"🕒 Возраст токена: 2/10 (зрелый токен > 1 года)")
        total_risk += risk_factors['age']
        
        # 6. Технические индикаторы (0-10 баллов) - УЛУЧШЕНА ЛОГИКА
        technical_risk = 0
        technical_details = []
        
        # RSI
        rsi = data.get('rsi', 50)
        if rsi > 85:
            technical_risk += 4
            technical_details.append(f"RSI очень перекуплен ({rsi:.1f})")
        elif rsi > 75:
            technical_risk += 2
            technical_details.append(f"RSI перекуплен ({rsi:.1f})")
        elif rsi < 15:
            technical_risk += 4
            technical_details.append(f"RSI очень перепродан ({rsi:.1f})")
        elif rsi < 25:
            technical_risk += 2
            technical_details.append(f"RSI перепродан ({rsi:.1f})")
        
        # Ценовое изменение за 24ч
        price_change_24h = data.get('price_change_24h', 0)
        if abs(price_change_24h) > 50:
            technical_risk += 4
            technical_details.append(f"Экстремальное изменение цены ({price_change_24h:+.1f}%)")
        elif abs(price_change_24h) > 30:
            technical_risk += 3
            technical_details.append(f"Резкое изменение цены ({price_change_24h:+.1f}%)")
        elif abs(price_change_24h) > 15:
            technical_risk += 2
            technical_details.append(f"Значительное изменение цены ({price_change_24h:+.1f}%)")
        
        # Максимальный риск 10 баллов
        technical_risk = min(10, technical_risk)
        risk_factors['technical'] = technical_risk
        total_risk += technical_risk
        
        if technical_details:
            details.append(f"📊 Тех. индикаторы: {technical_risk}/10 ({', '.join(technical_details)})")
        else:
            details.append(f"📊 Тех. индикаторы: {technical_risk}/10 (нормальные)")
        
        # 7. НОВЫЙ ФАКТОР: On-chain активность (0-5 баллов)
        onchain_risk = 0
        onchain_details = []
        
        large_transfers = data.get('large_transfers', [])
        if len(large_transfers) > 10:
            onchain_risk += 3
            onchain_details.append(f"Много крупных переводов ({len(large_transfers)})")
        elif len(large_transfers) > 5:
            onchain_risk += 2
            onchain_details.append(f"Крупные переводы ({len(large_transfers)})")
        
        total_transactions = data.get('total_transactions', 0)
        if total_transactions > 1000:
            onchain_risk += 2
            onchain_details.append(f"Высокая активность ({total_transactions} транзакций)")
        
        risk_factors['onchain'] = onchain_risk
        total_risk += onchain_risk
        
        if onchain_details:
            details.append(f"🔗 On-chain активность: {onchain_risk}/5 ({', '.join(onchain_details)})")
        else:
            details.append(f"🔗 On-chain активность: {onchain_risk}/5 (нормальная)")
        
        # Определение уровня риска
        if total_risk >= 75:
            risk_level = 'CRITICAL'
        elif total_risk >= 55:
            risk_level = 'HIGH'
        elif total_risk >= 35:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'
        
        # Логируем детализацию только один раз
        logger.warning(f"⚠️ {symbol} риск: {risk_level} ({total_risk:.1f}/100)")
        for detail in details:
            logger.info(f"   {detail}")
        
        result = {
            'total_risk': total_risk,
            'risk_level': risk_level,
            'risk_factors': risk_factors,
            'details': details,
            'recommendation': get_risk_recommendation(risk_level)
        }
        
        # Сохраняем в кэш
        set_cached_risk_score(symbol, data_hash, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка расчета риска для {symbol}: {e}")
        return {'total_risk': 100, 'risk_level': 'UNKNOWN', 'risk_factors': {}, 'details': ['Ошибка расчета'], 'recommendation': 'Unable to calculate risk'}

def get_risk_recommendation(risk_level: str) -> str:
    """Рекомендации по уровню риска"""
    recommendations = {
        'CRITICAL': '🚨 Очень высокий риск! Избегайте инвестиций',
        'HIGH': '⚠️ Высокий риск. Только для опытных инвесторов',
        'MEDIUM': '📊 Средний риск. Требует тщательного анализа',
        'LOW': '✅ Низкий риск. Подходит для консервативных инвесторов'
    }
    return recommendations.get(risk_level, 'Неизвестный уровень риска')

def calculate_volatility(prices: List[float]) -> float:
    """Расчет волатильности цен"""
    if len(prices) < 2:
        return 0.0
    
    returns = []
    for i in range(1, len(prices)):
        if prices[i-1] != 0:
            returns.append((prices[i] - prices[i-1]) / prices[i-1])
    
    if not returns:
        return 0.0
    
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    return (variance ** 0.5) * (24 ** 0.5)  # Годовая волатильность

def get_price_history(symbol: str, hours: int = 24) -> List[tuple]:
    """Получение истории цен из БД"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, price FROM token_data
            WHERE symbol = ? AND timestamp >= datetime('now', ?)
            ORDER BY timestamp ASC
        ''', (symbol, f'-{hours} hours'))
        data = cursor.fetchall()
        conn.close()
        return data
    except Exception as e:
        logger.error(f"Ошибка получения истории цен: {e}")
        return []

# --- Portfolio Analytics ---
def calculate_portfolio_metrics(portfolio: Dict[str, float]) -> Dict[str, Any]:
    """Расчет метрик портфеля"""
    try:
        total_value = sum(portfolio.values())
        if total_value == 0:
            return {'error': 'Portfolio is empty'}
        
        # Распределение по токенам
        allocation = {symbol: value/total_value for symbol, value in portfolio.items()}
        
        # Концентрация (индекс Херфиндаля)
        concentration = sum(allocation[symbol] ** 2 for symbol in allocation)
        
        # Диверсификация
        diversification = 1 - concentration
        
        # Получаем данные о рисках из кэша или используем среднее значение
        portfolio_risk = 0
        for symbol in portfolio:
            # Используем кэшированный риск если есть, иначе среднее значение
            if symbol in risk_cache:
                portfolio_risk += risk_cache[symbol]['data']['total_risk'] * allocation[symbol]
            else:
                # Средний риск если нет данных
                portfolio_risk += 50 * allocation[symbol]
        
        return {
            'total_value': total_value,
            'allocation': allocation,
            'concentration': concentration,
            'diversification': diversification,
            'portfolio_risk': portfolio_risk,
            'risk_level': get_portfolio_risk_level(portfolio_risk)
        }
        
    except Exception as e:
        logger.error(f"Ошибка расчета метрик портфеля: {e}")
        return {'error': str(e)}

def get_portfolio_risk_level(risk_score: float) -> str:
    """Определение уровня риска портфеля"""
    if risk_score >= 70:
        return 'CRITICAL'
    elif risk_score >= 50:
        return 'HIGH'
    elif risk_score >= 30:
        return 'MEDIUM'
    else:
        return 'LOW'

async def track_portfolio(portfolio: Dict[str, float]) -> Dict[str, Any]:
    """Трекинг портфеля с алертами"""
    try:
        results = {}
        
        for symbol, amount in portfolio.items():
            # Получаем текущую цену
            current_price = await get_current_price(symbol)
            if current_price:
                current_value = amount * current_price
                
                # Получаем историческую цену (24 часа назад)
                historical_price = await get_historical_price(symbol, hours=24)
                
                if historical_price:
                    price_change_24h = ((current_price - historical_price) / historical_price) * 100
                    value_change_24h = current_value - (amount * historical_price)
                    
                    results[symbol] = {
                        'amount': amount,
                        'current_price': current_price,
                        'current_value': current_value,
                        'price_change_24h': price_change_24h,
                        'value_change_24h': value_change_24h,
                        'percentage_of_portfolio': (current_value / sum(portfolio.values())) * 100 if sum(portfolio.values()) > 0 else 0
                    }
                    
                    # Алерты на значительные изменения (убрали дублирование)
                    # Алерты теперь отправляются только в check_portfolio_alerts
                    pass
        
        # Общие метрики портфеля
        portfolio_metrics = calculate_portfolio_metrics(portfolio)
        results['portfolio_metrics'] = portfolio_metrics
        
        # Сохраняем в БД
        await save_portfolio_data(results)
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка трекинга портфеля: {e}")
        return {}

async def get_current_price(symbol: str) -> Optional[float]:
    """Получение текущей цены токена"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT price FROM token_data 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (symbol,))
            
            result = cursor.fetchone()
            return result[0] if result else None
            
    except Exception as e:
        logger.error(f"Ошибка получения текущей цены для {symbol}: {e}")
        return None

async def get_historical_price(symbol: str, hours: int = 24) -> Optional[float]:
    """Получение исторической цены токена"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT price FROM token_data 
                WHERE symbol = ? 
                AND timestamp <= datetime('now', '-{} hours')
                ORDER BY timestamp DESC 
                LIMIT 1
            '''.format(hours), (symbol,))
            
            result = cursor.fetchone()
            return result[0] if result else None
            
    except Exception as e:
        logger.error(f"Ошибка получения исторической цены для {symbol}: {e}")
        return None

async def save_portfolio_data(portfolio_data: Dict[str, Any]):
    """Сохранение данных портфеля в БД"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Создаем таблицу если не существует
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS portfolio_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    amount REAL,
                    current_price REAL,
                    current_value REAL,
                    price_change_24h REAL,
                    value_change_24h REAL,
                    percentage_of_portfolio REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Сохраняем данные по каждому токену
            for symbol, data in portfolio_data.items():
                if symbol == 'portfolio_metrics':
                    continue
                    
                cursor.execute('''
                    INSERT INTO portfolio_tracking 
                    (symbol, amount, current_price, current_value, price_change_24h, value_change_24h, percentage_of_portfolio)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    data['amount'],
                    data['current_price'],
                    data['current_value'],
                    data['price_change_24h'],
                    data['value_change_24h'],
                    data['percentage_of_portfolio']
                ))
                
    except Exception as e:
        logger.error(f"Ошибка сохранения данных портфеля: {e}")

async def get_portfolio_history(symbol: str, days: int = 7) -> List[Dict[str, Any]]:
    """Получение истории портфеля"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM portfolio_tracking 
                WHERE symbol = ? 
                AND timestamp >= datetime('now', '-{} days')
                ORDER BY timestamp ASC
            '''.format(days), (symbol,))
            
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
            
    except Exception as e:
        logger.error(f"Ошибка получения истории портфеля: {e}")
        return []

def clear_old_portfolio_alerts():
    """Очищает старые портфельные алерты из базы данных"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Удаляем старые алерты портфеля
            cursor.execute('''
                DELETE FROM alerts 
                WHERE level IN ('PORTFOLIO_LOSS', 'PORTFOLIO_PROFIT') 
                OR message LIKE '%ПОРТФОЛИО АЛЕРТ%'
            ''')
            deleted_count = cursor.rowcount
            logger.info(f"Очищено {deleted_count} старых портфельных алертов из БД")
            
            # Очищаем кэш портфельных алертов
            global portfolio_alert_references
            portfolio_alert_references.clear()
            logger.info("Очищен кэш портфельных алертов")
            
    except Exception as e:
        logger.error(f"Ошибка очистки старых портфельных алертов: {e}")

# Глобальные переменные для отслеживания портфельных алертов
portfolio_alert_references = {}  # {symbol: {'last_alert_price': float, 'last_alert_time': int}}

def get_portfolio_alert_reference(symbol: str) -> Optional[Dict[str, Any]]:
    """Получает последнюю точку отсчета для портфельного алерта"""
    return portfolio_alert_references.get(symbol)

def set_portfolio_alert_reference(symbol: str, price: float):
    """Устанавливает новую точку отсчета для портфельного алерта"""
    portfolio_alert_references[symbol] = {
        'last_alert_price': price,
        'last_alert_time': int(time.time())
    }

async def check_portfolio_alerts(portfolio_data: Dict[str, Any]):
    """Проверка алертов портфеля с порогом 30% и правильной дедупликацией"""
    try:
        total_pnl = portfolio_data.get('total_pnl', 0)
        total_pnl_percentage = portfolio_data.get('total_pnl_percentage', 0)
        
        alerts = []
        
        # Алерты по общему PnL (оставляем старые пороги для общего портфеля)
        if total_pnl_percentage < -10:
            alerts.append(f"📉 Портфолио в убытке: {total_pnl_percentage:.2f}%")
        elif total_pnl_percentage > 10:
            alerts.append(f"📈 Портфолио в прибыли: {total_pnl_percentage:.2f}%")
        
        # Алерты по отдельным позициям с новым порогом 30%
        for symbol, position in portfolio_data.items():
            if symbol == 'portfolio_metrics':
                continue
                
            if 'price_change_24h' in position:
                price_change = position['price_change_24h']
                current_price = position.get('current_price', 0)
                
                # Получаем последнюю точку отсчета для этого токена
                reference = get_portfolio_alert_reference(symbol)
                
                if reference and current_price > 0:
                    last_alert_price = reference['last_alert_price']
                    last_alert_time = reference['last_alert_time']
                    current_time = time.time()
                    
                    # Вычисляем изменение от последней точки алерта
                    if last_alert_price > 0:
                        change_from_last_alert = abs((current_price - last_alert_price) / last_alert_price) * 100
                        
                        # Проверяем, прошло ли достаточно времени с последнего алерта (минимум 1 час)
                        time_since_last_alert = current_time - last_alert_time
                        
                        if change_from_last_alert >= 30 and time_since_last_alert >= 3600:  # 30% и 1 час
                            if price_change > 0:
                                alert_text = f"🚀 {symbol} вырос на {change_from_last_alert:.1f}% с последнего алерта (текущий рост: {price_change:.1f}%)"
                                set_portfolio_alert_reference(symbol, current_price)  # Обновляем точку отсчета
                                alerts.append(alert_text)
                                logger.info(f"Портфельный алерт: {symbol} вырос на {change_from_last_alert:.1f}%")
                            else:
                                alert_text = f"🔻 {symbol} упал на {change_from_last_alert:.1f}% с последнего алерта (текущий убыток: {price_change:.1f}%)"
                                set_portfolio_alert_reference(symbol, current_price)  # Обновляем точку отсчета
                                alerts.append(alert_text)
                                logger.info(f"Портфельный алерт: {symbol} упал на {change_from_last_alert:.1f}%")
                elif current_price > 0:
                    # Первый алерт для этого токена - устанавливаем точку отсчета
                    if abs(price_change) >= 30:  # Только если изменение больше 30%
                        if price_change > 0:
                            alert_text = f"🚀 {symbol} вырос на {price_change:.1f}% (первый алерт)"
                        else:
                            alert_text = f"🔻 {symbol} упал на {abs(price_change):.1f}% (первый алерт)"
                        
                        set_portfolio_alert_reference(symbol, current_price)
                        alerts.append(alert_text)
                        logger.info(f"Первый портфельный алерт для {symbol}: {price_change:.1f}%")
        
        # Отправляем алерты
        for alert in alerts:
            alert_message = f"💼 ПОРТФОЛИО АЛЕРТ: {alert}"
            await send_alert('INFO', alert_message)
            logger.info(f"Отправлен алерт портфолио: {alert}")
            
    except Exception as e:
        logger.error(f"Ошибка проверки алертов портфолио: {e}")

async def portfolio_loop():
    """Бесконечный цикл трекинга портфолио"""
    logger.info("💼 Запуск трекинга портфолио в цикле...")
    
    # Пример портфолио (можно загружать из конфигурации)
    sample_portfolio = {
        'FUEL': 1000.0,
        'ARC': 500.0,
        'VIRTUAL': 200.0,
        'BID': 100.0
    }
    
    while True:
        try:
            logger.info("💼 Обновление портфолио...")
            portfolio_summary = await track_portfolio(sample_portfolio)
            
            if portfolio_summary:
                logger.info(f"✅ Портфолио обновлен: ${portfolio_summary.get('total_value', 0):,.2f}")
                
                # Проверяем алерты портфолио
                await check_portfolio_alerts(portfolio_summary)
            
            await asyncio.sleep(900)  # Обновляем каждые 15 минут вместо 5
            
        except Exception as e:
            logger.error(f"❌ Ошибка в portfolio_loop: {e}")
            await asyncio.sleep(60)

# --- News Aggregator ---
async def fetch_crypto_news(symbol: str) -> List[Dict[str, Any]]:
    """Получает новости о криптовалюте из множества источников"""
    try:
        # Расширенный список источников новостей
        news_sources = [
            # RSS ленты
            'https://cointelegraph.com/rss',
            'https://coindesk.com/arc/outboundfeeds/rss/',
            'https://decrypt.co/feed',
            'https://www.coindesk.com/arc/outboundfeeds/rss/',
            'https://bitcoinmagazine.com/.rss/full/',
            'https://www.theblock.co/rss.xml',
            'https://www.newsbtc.com/feed/',
            'https://ambcrypto.com/feed/',
            'https://cryptonews.com/news/feed/',
            'https://www.cryptoglobe.com/feed/',
            
            # API источники
            f"https://api.coingecko.com/api/v3/news/{symbol.lower()}",
            f"https://cryptopanic.com/api/v1/posts/?auth_token=free&currencies={symbol}",
        ]
        
        news_items = []
        
        async with aiohttp.ClientSession() as session:
            for url in news_sources:
                try:
                    if 'api.coingecko.com' in url:
                        # Coingecko API
                        async with session.get(url, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                for item in data.get('data', []):
                                    news_items.append({
                                        'title': item.get('title', ''),
                                        'description': item.get('description', ''),
                                        'link': item.get('url', ''),
                                        'source': 'Coingecko',
                                        'published_at': item.get('published_at', ''),
                                        'sentiment': item.get('sentiment', 'neutral')
                                    })
                    elif 'cryptopanic.com' in url:
                        # CryptoPanic API
                        async with session.get(url, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                for item in data.get('results', []):
                                    news_items.append({
                                        'title': item.get('title', ''),
                                        'description': item.get('metadata', {}).get('description', ''),
                                        'link': item.get('url', ''),
                                        'source': 'CryptoPanic',
                                        'published_at': item.get('published_at', ''),
                                        'sentiment': item.get('vote', 'neutral')
                                    })

                    else:
                        # RSS ленты
                        rss_items = await parse_rss_news(session, url)
                        news_items.extend(rss_items)
                        
                except Exception as e:
                    logger.warning(f"Ошибка получения новостей из {url}: {e}")
                    continue
        
        # Сортируем по дате публикации
        news_items.sort(key=lambda x: x.get('published_at', ''), reverse=True)
        
        # Удаляем дубликаты по заголовку
        seen_titles = set()
        unique_news = []
        for item in news_items:
            title = item.get('title', '').lower().strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(item)
        
        return unique_news[:20]  # Возвращаем топ-20 новостей
        
    except Exception as e:
        logger.error(f"Ошибка получения новостей для {symbol}: {e}")
        return []

async def aggregate_similar_news(news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Агрегирует похожие новости в группы"""
    try:
        from difflib import SequenceMatcher
        
        # Группируем новости по схожести заголовков
        news_groups = []
        processed = set()
        
        for i, news1 in enumerate(news_items):
            if i in processed:
                continue
                
            group = [news1]
            processed.add(i)
            
            for j, news2 in enumerate(news_items[i+1:], i+1):
                if j in processed:
                    continue
                    
                # Проверяем схожесть заголовков
                similarity = SequenceMatcher(None, 
                    news1.get('title', '').lower(), 
                    news2.get('title', '').lower()
                ).ratio()
                
                if similarity > 0.7:  # Порог схожести
                    group.append(news2)
                    processed.add(j)
            
            if len(group) > 1:
                # Создаем агрегированную новость
                aggregated = {
                    'title': group[0]['title'],
                    'description': f"Найдено {len(group)} похожих новостей",
                    'link': group[0]['link'],
                    'source': f"Агрегировано из {len(group)} источников",
                    'published_at': group[0]['published_at'],
                    'sentiment': 'neutral',
                    'related_news': group,
                    'count': len(group)
                }
                news_groups.append(aggregated)
            else:
                news_groups.append(news1)
        
        return news_groups
        
    except Exception as e:
        logger.error(f"Ошибка агрегации новостей: {e}")
        return news_items

async def prioritize_news(news_items: List[Dict[str, Any]], symbol: str) -> List[Dict[str, Any]]:
    """Приоритизирует новости по важности"""
    try:
        prioritized = []
        
        for news in news_items:
            score = 0
            title = news.get('title', '').lower()
            description = news.get('description', '').lower()
            source = news.get('source', '').lower()
            
            # Базовые очки за источник
            source_scores = {
                'cointelegraph': 10,
                'coindesk': 9,
                'decrypt': 8,
                'bitcoinmagazine': 7,
                'theblock': 8,
                'newsbtc': 6,
                'ambcrypto': 5,
                'cryptonews': 6,
                'cryptoglobe': 5,
                'coingecko': 7,
                'cryptopanic': 6,

            }
            
            for source_name, source_score in source_scores.items():
                if source_name in source:
                    score += source_score
                    break
            
            # Очки за ключевые слова
            high_priority = ['listing', 'delisting', 'hack', 'exploit', 'mainnet', 'airdrop', 'whitelist', 'nft', 'mint']
            medium_priority = ['partnership', 'launch', 'update', 'announcement', 'ama', 'interview']
            low_priority = ['price', 'market', 'analysis', 'recap']
            
            for keyword in high_priority:
                if keyword in title or keyword in description:
                    score += 15
                    break
                    
            for keyword in medium_priority:
                if keyword in title or keyword in description:
                    score += 10
                    break
                    
            for keyword in low_priority:
                if keyword in title or keyword in description:
                    score += 5
                    break
            
            # Очки за упоминание токена
            if symbol.lower() in title or symbol.lower() in description:
                score += 20
            
            # Очки за свежесть (новости за последние 24 часа)
            try:
                pub_date = datetime.fromisoformat(news.get('published_at', '').replace('Z', '+00:00'))
                if (datetime.now(pub_date.tzinfo) - pub_date).days <= 1:
                    score += 10
            except:
                pass
            
            # Очки за настроение
            sentiment = news.get('sentiment', 'neutral')
            if sentiment == 'positive':
                score += 5
            elif sentiment == 'negative':
                score += 8  # Негативные новости важнее
            
            news['priority_score'] = score
            prioritized.append(news)
        
        # Сортируем по приоритету
        prioritized.sort(key=lambda x: x.get('priority_score', 0), reverse=True)
        
        return prioritized
        
    except Exception as e:
        logger.error(f"Ошибка приоритизации новостей: {e}")
        return news_items

async def analyze_news_trends(symbol: str, days: int = 7) -> Dict[str, Any]:
    """Анализирует тренды в новостях за период"""
    try:
        # Получаем исторические новости из БД
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sentiment, COUNT(*) as count, DATE(timestamp) as date
                FROM social_alerts 
                WHERE source = 'news_analysis' AND token = ? 
                AND timestamp >= datetime('now', '-{} days')
                GROUP BY sentiment, DATE(timestamp)
                ORDER BY date DESC
            '''.format(days), (symbol,))
            
            results = cursor.fetchall()
        
        # Анализируем тренды
        sentiment_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
        daily_trends = {}
        
        for sentiment, count, date in results:
            sentiment_counts[sentiment] += count
            if date not in daily_trends:
                daily_trends[date] = {'positive': 0, 'negative': 0, 'neutral': 0}
            daily_trends[date][sentiment] = count
        
        # Определяем общий тренд
        total_news = sum(sentiment_counts.values())
        if total_news > 0:
            positive_ratio = sentiment_counts['positive'] / total_news
            negative_ratio = sentiment_counts['negative'] / total_news
            
            if positive_ratio > 0.6:
                overall_trend = 'bullish'
            elif negative_ratio > 0.6:
                overall_trend = 'bearish'
            else:
                overall_trend = 'neutral'
        else:
            overall_trend = 'neutral'
        
        return {
            'symbol': symbol,
            'period_days': days,
            'total_news': total_news,
            'sentiment_distribution': sentiment_counts,
            'daily_trends': daily_trends,
            'overall_trend': overall_trend,
            'positive_ratio': sentiment_counts['positive'] / total_news if total_news > 0 else 0,
            'negative_ratio': sentiment_counts['negative'] / total_news if total_news > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"Ошибка анализа трендов новостей для {symbol}: {e}")
        return {}

async def check_news_impact_on_price(symbol: str, news_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализирует влияние новостей на цену"""
    try:
        # Получаем данные о цене за последние 24 часа
        price_history = get_price_history(symbol, hours=24)
        
        if not price_history:
            return {'impact': 'unknown', 'reason': 'Нет данных о цене'}
        
        # Получаем время публикации новости
        try:
            news_time = datetime.fromisoformat(news_data.get('published_at', '').replace('Z', '+00:00'))
        except:
            return {'impact': 'unknown', 'reason': 'Некорректная дата новости'}
        
        # Анализируем изменение цены после новости
        prices_before = [p for t, p in price_history if t < news_time]
        prices_after = [p for t, p in price_history if t >= news_time]
        
        if not prices_before or not prices_after:
            return {'impact': 'unknown', 'reason': 'Недостаточно данных о цене'}
        
        avg_price_before = sum(prices_before) / len(prices_before)
        avg_price_after = sum(prices_after) / len(prices_after)
        
        price_change_percent = ((avg_price_after - avg_price_before) / avg_price_before) * 100
        
        # Определяем влияние
        if abs(price_change_percent) < 2:
            impact = 'minimal'
        elif abs(price_change_percent) < 5:
            impact = 'moderate'
        else:
            impact = 'significant'
        
        return {
            'impact': impact,
            'price_change_percent': price_change_percent,
            'avg_price_before': avg_price_before,
            'avg_price_after': avg_price_after,
            'news_time': news_time.isoformat(),
            'analysis_period_hours': 24
        }
        
    except Exception as e:
        logger.error(f"Ошибка анализа влияния новостей на цену {symbol}: {e}")
        return {'impact': 'error', 'reason': str(e)}

async def send_news_alert(news_data: Dict[str, Any], symbol: str, priority: str = 'medium'):
    """Отправляет алерт о новости с учетом приоритета и дедупликации"""
    try:
        # Проверяем, что новость релевантна для данного токена
        if not is_news_relevant_for_token(news_data, symbol):
            logger.info(f"Новость не релевантна для {symbol}: {news_data.get('title', '')[:50]}...")
            return
        
        # Генерируем хеш новости для дедупликации
        news_hash = generate_news_hash(news_data)
        
        # Проверяем, не была ли уже отправлена эта новость
        if was_news_alert_sent(news_hash, symbol, hours=24):
            logger.info(f"Новость уже была отправлена для {symbol}: {news_data.get('title', '')[:50]}...")
            return
        
        # Форматируем сообщение в зависимости от приоритета
        if priority == 'high':
            emoji = "🚨"
            tag = "[🚨 СРОЧНО]"
        elif priority == 'medium':
            emoji = "⚠️"
            tag = "[⚠️ ВАЖНО]"
        else:
            emoji = "ℹ️"
            tag = "[ℹ️ ИНФО]"
        
        # Анализируем влияние на цену
        price_impact = await check_news_impact_on_price(symbol, news_data)
        
        # Формируем сообщение
        message = f"""{tag} {emoji} НОВОСТЬ О {symbol} {emoji}

📰 {news_data.get('title', 'Без заголовка')}

📝 {news_data.get('description', 'Без описания')}

🏷️ Источник: {news_data.get('source', 'Неизвестно')}
📅 Дата: {news_data.get('published_at', 'Неизвестно')}
⭐ Приоритет: {priority.upper()}
💰 Влияние на цену: {price_impact.get('impact', 'Неизвестно')}

🔗 Подробнее: {news_data.get('link', 'Ссылка недоступна')}"""
        
        # Отправляем алерт
        await send_alert(
            priority.upper(),
            message,
            symbol,
            {
                'source': 'news_analysis',
                'url': news_data.get('link', ''),
                'sentiment': news_data.get('sentiment', 'neutral'),
                'priority_score': news_data.get('priority_score', 0),
                'price_impact': price_impact
            }
        )
        
        # Сохраняем информацию об отправленной новости
        save_news_alert_sent(news_hash, symbol, priority)
        
        logger.info(f"Отправлен алерт о новости {symbol}: {priority}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки алерта о новости: {e}")

async def official_sources_loop():
    """Бесконечный цикл мониторинга официальных источников"""
    logger.info("📰 Запуск мониторинга официальных источников в цикле...")
    while True:
        try:
            logger.info("📰 Проверка официальных источников...")
            await check_official_sources()
            logger.info("✅ Мониторинг официальных источников завершен")
            await asyncio.sleep(config.social_config.get('fetch_interval', 900))  # 15 минут
        except Exception as e:
            logger.error(f"❌ Ошибка в official_sources_loop: {e}")
            await asyncio.sleep(60)

async def check_official_sources():
    """Мониторинг только официальных источников токенов"""
    try:
        logger.info("Запуск мониторинга официальных источников")
        
        # Загружаем конфигурацию токенов
        with open('tokens.json', 'r') as f:
            tokens_config = json.load(f)
        
        for symbol, token_data in tokens_config['tokens'].items():
            try:
                logger.info(f"Мониторинг официальных источников для {symbol}")
                
                social_accounts = token_data.get('social_accounts', {})
                
                # Мониторинг Twitter
                if 'twitter' in social_accounts:
                    await check_twitter_official(symbol, social_accounts['twitter'])
                
                # Мониторинг Discord
                if 'discord' in social_accounts:
                    await check_discord_official(symbol, social_accounts['discord'])
                
                # Мониторинг Telegram
                if 'telegram' in social_accounts:
                    await check_telegram_official(symbol, social_accounts['telegram'])
                
                # Мониторинг GitHub
                if 'github' in social_accounts:
                    await check_github_official(symbol, social_accounts['github'])
                
                # Мониторинг основателей
                if 'founders' in social_accounts:
                    await check_founders_official(symbol, social_accounts['founders'])
                
            except Exception as e:
                logger.error(f"Ошибка мониторинга официальных источников для {symbol}: {e}")
                continue
        
        logger.info("Мониторинг официальных источников завершен")
        
    except Exception as e:
        logger.error(f"Ошибка мониторинга официальных источников: {e}")

async def check_twitter_official(symbol: str, twitter_accounts: List[str]):
    """Мониторинг официальных Twitter аккаунтов"""
    try:
        logger.info(f"Мониторинг Twitter для {symbol}: {twitter_accounts}")
        
        for account in twitter_accounts:
            try:
                # Убираем @ из имени аккаунта
                username = account.replace('@', '')
                
                # RSS feed для Twitter (через nitter.net)
                rss_url = f"https://nitter.net/{username}/rss"
                
                logger.info(f"Проверяем Twitter аккаунт: {username}")
                
                # Получаем посты через RSS
                async with aiohttp.ClientSession() as session:
                    posts = await parse_rss_news(session, rss_url)
                    
                    if posts:
                        # Фильтруем только новые посты (за последние 24 часа)
                        recent_posts = []
                        for post in posts:
                            try:
                                # Парсим дату поста
                                pub_date = post.get('pub_date', '')
                                if pub_date:
                                    # Пытаемся распарсить дату
                                    from email.utils import parsedate_to_datetime
                                    post_datetime = parsedate_to_datetime(pub_date)
                                    
                                    # Проверяем, что пост не старше 24 часов
                                    if datetime.now() - post_datetime < timedelta(hours=24):
                                        recent_posts.append(post)
                            except Exception as e:
                                logger.warning(f"Ошибка парсинга даты поста: {e}")
                                continue
                        
                        # Отправляем алерты для новых постов
                        for post in recent_posts[:3]:  # Максимум 3 поста
                            await send_official_post_alert(post, symbol, 'Twitter', username)
                    
                    else:
                        logger.info(f"Посты не найдены для {username}")
                        
            except Exception as e:
                logger.error(f"Ошибка мониторинга Twitter аккаунта {account}: {e}")
                continue
            
    except Exception as e:
        logger.error(f"Ошибка мониторинга Twitter для {symbol}: {e}")

async def check_discord_official(symbol: str, discord_servers: List[str]):
    """Мониторинг официальных Discord серверов"""
    try:
        logger.info(f"Мониторинг Discord для {symbol}: {discord_servers}")
        
        for server_url in discord_servers:
            try:
                logger.info(f"Проверяем Discord сервер: {server_url}")
                
                # Извлекаем invite code из URL
                if 'discord.gg/' in server_url:
                    invite_code = server_url.split('discord.gg/')[-1]
                    
                    # Получаем информацию о сервере через Discord API
                    invite_url = f"https://discord.com/api/v10/invites/{invite_code}?with_counts=true"
                    
                    async with aiohttp.ClientSession() as session:
                        headers = {
                            'User-Agent': 'CryptoMonitor/1.0'
                        }
                        
                        async with session.get(invite_url, headers=headers, timeout=10) as response:
                            if response.status == 200:
                                server_data = await response.json()
                                
                                # Отправляем информацию о сервере (статистика)
                                await send_discord_server_alert(server_data, symbol, invite_code)
                                
                            else:
                                logger.warning(f"Discord API error {response.status} для {invite_code}")
                                
            except Exception as e:
                logger.error(f"Ошибка мониторинга Discord сервера {server_url}: {e}")
                continue
            
    except Exception as e:
        logger.error(f"Ошибка мониторинга Discord для {symbol}: {e}")

async def check_telegram_official(symbol: str, telegram_channels: List[str]):
    """Мониторинг официальных Telegram каналов"""
    try:
        logger.info(f"Мониторинг Telegram для {symbol}: {telegram_channels}")
        
        for channel in telegram_channels:
            logger.info(f"Проверяем Telegram канал: {channel}")
            
            # В будущем здесь будет реальный мониторинг Telegram
            # await fetch_telegram_messages(channel, symbol)
            
    except Exception as e:
        logger.error(f"Ошибка мониторинга Telegram для {symbol}: {e}")

async def check_github_official(symbol: str, github_repos: List[str]):
    """Мониторинг официальных GitHub репозиториев"""
    try:
        logger.info(f"Мониторинг GitHub для {symbol}: {github_repos}")
        
        for repo_url in github_repos:
            try:
                # Извлекаем owner/repo из URL с улучшенной обработкой
                owner = None
                repo = None
                
                if 'github.com' in repo_url:
                    # Убираем протокол и www
                    clean_url = repo_url.replace('https://', '').replace('http://', '').replace('www.', '')
                    
                    # Извлекаем путь после github.com
                    if 'github.com/' in clean_url:
                        path_part = clean_url.split('github.com/')[1]
                        
                        # Убираем trailing slash и дополнительные параметры
                        path_part = path_part.rstrip('/').split('?')[0].split('#')[0]
                        
                        # Разбиваем на части
                        parts = path_part.split('/')
                        
                        if len(parts) >= 2:
                            owner = parts[0]
                            repo = parts[1]
                        elif len(parts) == 1:
                            # Если только один элемент, это может быть организация
                            owner = parts[0]
                            repo = None
                        else:
                            logger.warning(f"Неверный формат GitHub URL: {repo_url}")
                            continue
                    else:
                        logger.warning(f"Неверный GitHub URL формат: {repo_url}")
                        continue
                else:
                    logger.warning(f"URL не содержит github.com: {repo_url}")
                    continue
                
                if not owner:
                    logger.warning(f"Не удалось извлечь owner из URL: {repo_url}")
                    continue
                
                if repo:
                    logger.info(f"Проверяем GitHub репозиторий: {owner}/{repo}")
                    
                    # Получаем последние коммиты
                    commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
                    
                    async with aiohttp.ClientSession() as session:
                        headers = {
                            'User-Agent': 'CryptoMonitor/1.0',
                            'Accept': 'application/vnd.github.v3+json'
                        }
                        
                        async with session.get(commits_url, headers=headers, timeout=10) as response:
                            if response.status == 200:
                                commits_data = await response.json()
                                
                                # Фильтруем коммиты за последние 24 часа
                                recent_commits = []
                                for commit in commits_data[:10]:  # Проверяем последние 10 коммитов
                                    try:
                                        commit_date = commit['commit']['author']['date']
                                        commit_datetime = datetime.fromisoformat(commit_date.replace('Z', '+00:00'))
                                        
                                        # Проверяем, что коммит не старше 24 часов
                                        if datetime.now(commit_datetime.tzinfo) - commit_datetime < timedelta(hours=24):
                                            recent_commits.append(commit)
                                    except Exception as e:
                                        logger.warning(f"Ошибка парсинга даты коммита: {e}")
                                        continue
                                
                                # Отправляем алерты для новых коммитов
                                for commit in recent_commits[:3]:  # Максимум 3 коммита
                                    await send_github_commit_alert(commit, symbol, owner, repo)
                                
                                if not recent_commits:
                                    logger.info(f"Новых коммитов не найдено для {owner}/{repo}")
                                    
                            else:
                                logger.warning(f"GitHub API error {response.status} для {owner}/{repo}")
                else:
                    logger.info(f"Проверяем GitHub организацию: {owner}")
                    # Для организаций можно добавить мониторинг активности
                    
            except Exception as e:
                logger.error(f"Ошибка мониторинга GitHub репозитория {repo_url}: {e}")
                continue
            
    except Exception as e:
        logger.error(f"Ошибка мониторинга GitHub для {symbol}: {e}")

async def check_founders_official(symbol: str, founder_accounts: List[str]):
    """Мониторинг аккаунтов основателей"""
    try:
        logger.info(f"Мониторинг основателей для {symbol}: {founder_accounts}")
        
        for account in founder_accounts:
            logger.info(f"Проверяем аккаунт основателя: {account}")
            
            # В будущем здесь будет реальный мониторинг основателей
            # await fetch_founder_posts(account, symbol)
            
    except Exception as e:
        logger.error(f"Ошибка мониторинга основателей для {symbol}: {e}")

async def news_loop():
    """Бесконечный цикл мониторинга новостей"""
    logger.info("📢 Запуск мониторинга новостей в цикле...")
    while True:
        try:
            logger.info("📢 Проверка новостей...")
            await check_news()
            logger.info("✅ Мониторинг новостей завершен")
            await asyncio.sleep(config.social_config.get('fetch_interval', 900))  # 15 минут
        except Exception as e:
            logger.error(f"❌ Ошибка в news_loop: {e}")
            await asyncio.sleep(60)

async def check_news():
    """Основная функция мониторинга новостей (общие источники)"""
    try:
        logger.info("Запуск мониторинга общих новостей")
        
        # Получаем новости для каждого токена
        for symbol in ['FUEL', 'ARC', 'VIRTUAL']:
            try:
                # Получаем новости
                news_items = await fetch_crypto_news(symbol)
                
                if not news_items:
                    logger.info(f"Новости для {symbol} не найдены")
                    continue
                
                # Агрегируем похожие новости
                aggregated_news = await aggregate_similar_news(news_items)
                
                # Приоритизируем новости
                prioritized_news = await prioritize_news(aggregated_news, symbol)
                
                # Анализируем тренды
                trends = await analyze_news_trends(symbol)
                
                # Отправляем алерты для важных новостей
                for news in prioritized_news[:5]:  # Топ-5 новостей
                    priority_score = news.get('priority_score', 0)
                    
                    if priority_score >= 30:
                        priority = 'high'
                    elif priority_score >= 20:
                        priority = 'medium'
                    else:
                        priority = 'low'
                    
                    # Отправляем только важные новости
                    if priority in ['high', 'medium']:
                        await send_news_alert(news, symbol, priority)
                
                # Логируем статистику
                logger.info(f"Обработано {len(news_items)} новостей для {symbol}, "
                          f"отправлено {len([n for n in prioritized_news[:5] if n.get('priority_score', 0) >= 20])} алертов")
                
            except Exception as e:
                logger.error(f"Ошибка обработки новостей для {symbol}: {e}")
                continue
        
        logger.info("Мониторинг новостей завершен")
        
    except Exception as e:
        logger.error(f"Ошибка мониторинга новостей: {e}")

# --- Advanced Technical Indicators ---
def calculate_advanced_indicators(prices: List[float]) -> Dict[str, Any]:
    """Расчет продвинутых технических индикаторов"""
    try:
        if len(prices) < 20:
            return {}
        
        # MACD
        ema_12 = calculate_ema(prices, 12)
        ema_26 = calculate_ema(prices, 26)
        macd_line = ema_12 - ema_26
        signal_line = calculate_ema([macd_line], 9)
        macd_histogram = macd_line - signal_line
        
        # Bollinger Bands
        sma_20 = sum(prices[-20:]) / 20
        std_dev = (sum((p - sma_20) ** 2 for p in prices[-20:]) / 20) ** 0.5
        upper_band = sma_20 + (2 * std_dev)
        lower_band = sma_20 - (2 * std_dev)
        
        # Stochastic RSI
        rsi = calculate_rsi(prices)
        stoch_rsi = calculate_stochastic_rsi(prices)
        
        # Volume Weighted Average Price (VWAP)
        # Упрощенная версия без объема
        vwap = sum(prices) / len(prices)
        
        # Сигналы
        signals = {}
        current_price = prices[-1]
        
        # MACD сигналы
        if macd_line > signal_line and macd_histogram > 0:
            signals['macd'] = 'bullish'
        elif macd_line < signal_line and macd_histogram < 0:
            signals['macd'] = 'bearish'
        else:
            signals['macd'] = 'neutral'
        
        # Bollinger Bands сигналы
        if current_price > upper_band:
            signals['bb'] = 'overbought'
        elif current_price < lower_band:
            signals['bb'] = 'oversold'
        else:
            signals['bb'] = 'neutral'
        
        # RSI сигналы
        if rsi > 70:
            signals['rsi'] = 'overbought'
        elif rsi < 30:
            signals['rsi'] = 'oversold'
        else:
            signals['rsi'] = 'neutral'
        
        return {
            'macd': {
                'line': macd_line,
                'signal': signal_line,
                'histogram': macd_histogram,
                'signal_type': signals['macd']
            },
            'bollinger_bands': {
                'upper': upper_band,
                'middle': sma_20,
                'lower': lower_band,
                'signal_type': signals['bb']
            },
            'rsi': rsi,
            'stoch_rsi': stoch_rsi,
            'vwap': vwap,
            'signals': signals
        }
        
    except Exception as e:
        logger.error(f"Ошибка расчета продвинутых индикаторов: {e}")
        return {}

def calculate_ema(prices: List[float], period: int) -> float:
    """Расчет экспоненциальной скользящей средней"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    
    multiplier = 2 / (period + 1)
    ema = prices[0]
    
    for price in prices[1:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    
    return ema

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Расчет RSI"""
    if len(prices) < period + 1:
        return 50
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def calculate_stochastic_rsi(prices: List[float], period: int = 14) -> float:
    """Расчет Stochastic RSI"""
    if len(prices) < period:
        return 50
    
    rsi_values = []
    for i in range(period, len(prices)):
        rsi_values.append(calculate_rsi(prices[i-period:i+1]))
    
    if not rsi_values:
        return 50
    
    min_rsi = min(rsi_values)
    max_rsi = max(rsi_values)
    
    if max_rsi == min_rsi:
        return 50
    
    current_rsi = rsi_values[-1]
    stoch_rsi = (current_rsi - min_rsi) / (max_rsi - min_rsi)
    
    return stoch_rsi * 100

# --- Backtesting Engine ---
def backtest_strategy(symbol: str, strategy: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """Бэктестинг торговых стратегий"""
    try:
        # Получаем исторические данные
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, price, volume_24h FROM token_data
            WHERE symbol = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
        ''', (symbol, start_date, end_date))
        data = cursor.fetchall()
        conn.close()
        
        if len(data) < 20:
            return {'error': 'Недостаточно данных для бэктестинга'}
        
        # Инициализация
        initial_balance = 10000  # $10,000
        balance = initial_balance
        position = 0
        trades = []
        
        prices = [float(row[1]) for row in data]
        
        for i in range(20, len(prices)):
            current_price = prices[i]
            signal = generate_trading_signal(prices[:i+1], strategy)
            
            if signal == 'buy' and position == 0:
                # Покупаем
                position = balance / current_price
                balance = 0
                trades.append({
                    'type': 'buy',
                    'price': current_price,
                    'timestamp': data[i][0],
                    'position': position
                })
            
            elif signal == 'sell' and position > 0:
                # Продаем
                balance = position * current_price
                trades.append({
                    'type': 'sell',
                    'price': current_price,
                    'timestamp': data[i][0],
                    'balance': balance
                })
                position = 0
        
        # Закрываем позицию в конце
        if position > 0:
            final_price = prices[-1]
            balance = position * final_price
        
        # Расчет результатов
        total_return = ((balance - initial_balance) / initial_balance) * 100
        num_trades = len([t for t in trades if t['type'] == 'sell'])
        
        return {
            'initial_balance': initial_balance,
            'final_balance': balance,
            'total_return': total_return,
            'num_trades': num_trades,
            'trades': trades,
            'strategy': strategy,
            'symbol': symbol
        }
        
    except Exception as e:
        logger.error(f"Ошибка бэктестинга: {e}")
        return {'error': str(e)}

def generate_trading_signal(prices: List[float], strategy: str) -> str:
    """Генерация торговых сигналов"""
    if len(prices) < 20:
        return 'hold'
    
    if strategy == 'rsi':
        rsi = calculate_rsi(prices)
        if rsi < 30:
            return 'buy'
        elif rsi > 70:
            return 'sell'
    
    elif strategy == 'macd':
        ema_12 = calculate_ema(prices, 12)
        ema_26 = calculate_ema(prices, 26)
        macd = ema_12 - ema_26
        signal = calculate_ema([macd], 9)
        
        if macd > signal:
            return 'buy'
        elif macd < signal:
            return 'sell'
    
    elif strategy == 'bollinger':
        sma_20 = sum(prices[-20:]) / 20
        std_dev = (sum((p - sma_20) ** 2 for p in prices[-20:]) / 20) ** 0.5
        upper_band = sma_20 + (2 * std_dev)
        lower_band = sma_20 - (2 * std_dev)
        current_price = prices[-1]
        
        if current_price < lower_band:
            return 'buy'
        elif current_price > upper_band:
            return 'sell'
    
    return 'hold'

# --- Performance Monitoring ---
def monitor_system_performance() -> Dict[str, Any]:
    """Мониторинг производительности системы"""
    try:
        import psutil
        import time
        
        # Системные метрики
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Метрики процесса
        process = psutil.Process()
        process_cpu = process.cpu_percent()
        process_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Метрики БД
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Размер БД
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        db_size = (page_count * page_size) / 1024 / 1024  # MB
        
        # Количество записей
        cursor.execute("SELECT COUNT(*) FROM token_data")
        token_records = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM alerts")
        alert_records = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM social_alerts")
        social_records = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'timestamp': time.time(),
            'system': {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': (disk.used / disk.total) * 100
            },
            'process': {
                'cpu_percent': process_cpu,
                'memory_mb': process_memory
            },
            'database': {
                'size_mb': db_size,
                'token_records': token_records,
                'alert_records': alert_records,
                'social_records': social_records
            },
            'status': 'healthy' if cpu_percent < 80 and memory.percent < 80 else 'warning'
        }
        
    except Exception as e:
        logger.error(f"Ошибка мониторинга производительности: {e}")
        return {'error': str(e)}

# --- API Gateway Functions ---
async def get_token_summary(symbol: str) -> Dict[str, Any]:
    """Получение сводки по токену для API"""
    try:
        # Получаем последние данные
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT price, volume_24h, timestamp FROM token_data
            WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1
        ''', (symbol,))
        latest_data = cursor.fetchone()
        
        if not latest_data:
            return {'error': 'No data available'}
        
        price, volume, timestamp = latest_data
        
        # Анализ настроений (синхронная версия)
        try:
            # Получаем данные из БД вместо асинхронного вызова
            cursor.execute('''
                SELECT original_text FROM social_alerts
                WHERE token = ? AND timestamp > datetime('now', '-24 hours')
                ORDER BY timestamp DESC LIMIT 10
            ''', (symbol,))
            social_texts = cursor.fetchall()
            
            if social_texts:
                # Простой анализ настроений на основе ключевых слов
                all_text = ' '.join([text[0] for text in social_texts]).lower()
                positive_words = ['bullish', 'moon', 'pump', 'buy', 'strong', 'good', 'great']
                negative_words = ['bearish', 'dump', 'sell', 'weak', 'bad', 'crash']
                
                positive_count = sum(1 for word in positive_words if word in all_text)
                negative_count = sum(1 for word in negative_words if word in all_text)
                
                if positive_count > negative_count:
                    sentiment = {'overall_sentiment': 'bullish', 'confidence': 0.7}
                elif negative_count > positive_count:
                    sentiment = {'overall_sentiment': 'bearish', 'confidence': 0.7}
                else:
                    sentiment = {'overall_sentiment': 'neutral', 'confidence': 0.5}
            else:
                sentiment = {'overall_sentiment': 'neutral', 'confidence': 0.0}
        except Exception as e:
            sentiment = {'overall_sentiment': 'neutral', 'confidence': 0.0}
        
        # Оценка риска
        risk_data = await calculate_risk_score(symbol, {'volume_24h': volume})
        
        # Технические индикаторы
        price_history = get_price_history(symbol, hours=24)
        prices = [float(p[1]) for p in price_history]
        technical_indicators = calculate_advanced_indicators(prices)
        
        conn.close()
        
        return {
            'symbol': symbol,
            'price': price,
            'volume_24h': volume,
            'last_updated': timestamp,
            'sentiment': sentiment,
            'risk_assessment': risk_data,
            'technical_indicators': technical_indicators,
            'price_change_24h': calculate_price_change(symbol, 24)
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения сводки токена: {e}")
        return {'error': str(e)}

def calculate_price_change(symbol: str, hours: int) -> float:
    """Расчет изменения цены за период"""
    try:
        price_history = get_price_history(symbol, hours)
        if len(price_history) < 2:
            return 0.0
        
        current_price = float(price_history[-1][1])
        old_price = float(price_history[0][1])
        
        if old_price == 0:
            return 0.0
        
        return ((current_price - old_price) / old_price) * 100
        
    except Exception as e:
        logger.error(f"Ошибка расчета изменения цены: {e}")
        return 0.0

async def get_market_overview() -> Dict[str, Any]:
    """Обзор рынка для всех отслеживаемых токенов"""
    try:
        overview = {}
        
        for symbol in TOKENS.keys():
            overview[symbol] = await get_token_summary(symbol)
        
        # Общие метрики рынка
        total_volume = sum(
            overview[symbol].get('volume_24h', 0) 
            for symbol in overview 
            if 'error' not in overview[symbol]
        )
        
        # Среднее настроение
        sentiments = [
            overview[symbol].get('sentiment', {}).get('sentiment', 0)
            for symbol in overview
            if 'error' not in overview[symbol]
        ]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
        
        return {
            'tokens': overview,
            'market_metrics': {
                'total_volume_24h': total_volume,
                'average_sentiment': avg_sentiment,
                'timestamp': datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения обзора рынка: {e}")
        return {'error': str(e)}

async def onchain_loop(session):
    """Бесконечный цикл мониторинга on-chain данных"""
    logger.info("🔄 Запуск onchain мониторинга в цикле...")
    while True:
        try:
            logger.info("📊 Проверка on-chain данных...")
            result = await check_onchain(session)
            logger.info(f"✅ On-chain данные получены: {result}")
            await asyncio.sleep(config.monitoring_config['check_interval'])
        except Exception as e:
            logger.error(f"❌ Ошибка в onchain_loop: {e}")
            await asyncio.sleep(30)  # Пауза при ошибке

async def setup_whale_tracking():
    """Настройка Whale Tracker для мониторинга держателей"""
    try:
        if not config.whale_tracker_config.get('enabled', False):
            logger.info("Whale Tracker отключен")
            return None
        
        # Whale Tracker модуль не реализован
        logger.warning("Whale Tracker модуль не реализован, функционал отключен")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка настройки Whale Tracker: {e}")
        return None

async def main():
    """Главная асинхронная функция запуска мониторинга"""
    import os
    import tempfile
    
    # Создаем файл блокировки для предотвращения запуска нескольких экземпляров
    lock_file = os.path.join(tempfile.gettempdir(), 'crypto_monitor.lock')
    
    # Проверяем, не запущен ли уже монитор
    if os.path.exists(lock_file):
        with open(lock_file, 'r') as f:
            pid = f.read().strip()
        if os.path.exists(f'/proc/{pid}') or os.path.exists(f'/tmp/{pid}'):
            logger.error(f"Монитор уже запущен с PID {pid}")
            return
    
    # Создаем файл блокировки
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))
    
    logger.info("=== Crypto Monitor стартует ===")
    
    # Проверка доступности API и сервисов
    logger.info("🔍 Проверка доступности API и сервисов...")
    
    # Проверка OpenAI API
    if OPENAI_API_KEY and OPENAI_API_KEY != 'your_openai_api_key_here':
        logger.info("✅ OpenAI API ключ настроен")
    else:
        logger.warning("⚠️ OpenAI API ключ не настроен - AI анализ недоступен")
    
    # Проверка Discord токена
    discord_token = config.social_config.get('discord_token')
    if discord_token:
        logger.info("✅ Discord токен настроен")
    else:
        logger.warning("⚠️ Discord токен не настроен - Discord мониторинг недоступен")
    
    # Проверка Telegram API
    telegram_api = config.social_config.get('telegram_api')
    if telegram_api:
        logger.info("✅ Telegram API настроен")
    else:
        logger.warning("⚠️ Telegram API не настроен - Telegram мониторинг недоступен")
    
    # Проверка Twitter scrapers
    try:
        import twint
        logger.info("✅ Twint доступен для Twitter мониторинга")
    except ImportError:
        logger.warning("⚠️ Twint не установлен - Twitter мониторинг ограничен")
    
    try:
        from ntscraper import Nitter
        logger.info("✅ Nitter scraper доступен для Twitter мониторинга")
    except ImportError:
        logger.warning("⚠️ Nitter scraper не установлен - установите: pip install ntscraper")
    
    # Инициализация базы данных
    try:
        init_database()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        log_error("Инициализация БД", e)
        logger.error("❌ Ошибка инициализации БД")
    
    # Загрузка пиковых значений из БД
    try:
        load_peak_values_from_db()
        logger.info("✅ Пиковые значения загружены из БД")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки пиковых значений: {e}")
    
    # Очистка старых портфельных алертов
    try:
        clear_old_portfolio_alerts()
        logger.info("✅ Старые портфельные алерты очищены")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка очистки старых портфельных алертов: {e}")
    
    # Инициализация OpenAI
    try:
        init_openai()
    except Exception as e:
        log_error("Инициализация OpenAI", e)
    
    # Инициализация новых модулей
    if NEW_MODULES_AVAILABLE:
        try:
            # Инициализация менеджеров
            performance_monitor = get_performance_monitor()
            alert_manager = get_alert_manager()
            recovery_manager = get_recovery_manager()
            
            # Регистрация компонентов для восстановления
            recovery_config = RecoveryConfig(
                max_retries=3,
                retry_delay=1.0,
                strategy=RecoveryStrategy.RETRY
            )
            
            recovery_manager.register_component("onchain_monitor", recovery_config)
            recovery_manager.register_component("cex_monitor", recovery_config)
            recovery_manager.register_component("dex_monitor", recovery_config)
            recovery_manager.register_component("social_monitor", recovery_config)
            recovery_manager.register_component("analytics_monitor", recovery_config)
            
            logger.info("✅ Новые модули инициализированы")
        except Exception as e:
            log_error("Инициализация новых модулей", e)
            logger.warning("⚠️ Новые модули не инициализированы")
    else:
        logger.warning("⚠️ Новые модули недоступны")
    
    logger.info("🚀 Запуск основных задач мониторинга...")
    
    # Telegram бот теперь запускается отдельно через telegram_bot.py
    # Отключаем запуск бота здесь для избежания конфликтов
    logger.info("🤖 Telegram бот запускается отдельно через telegram_bot.py")
    
    try:
        async with aiohttp.ClientSession() as session:
            logger.info("📊 Запуск onchain мониторинга...")
            onchain_task = asyncio.create_task(onchain_loop(session))
            logger.info("🏪 Запуск мониторинга CEX...")
            cex_task = asyncio.create_task(cex_loop(session))
            logger.info("🔄 Запуск мониторинга DEX...")
            dex_task = asyncio.create_task(dex_loop(session))
            logger.info("📱 Запуск мониторинга социальных сетей...")
            social_task = asyncio.create_task(social_loop(session))
            logger.info("📈 Запуск мониторинга аналитики...")
            analytics_task = asyncio.create_task(analytics_loop(session))
            logger.info("📰 Запуск мониторинга официальных источников...")
            official_sources_task = asyncio.create_task(official_sources_loop())
            logger.info("📢 Запуск мониторинга новостей...")
            news_task = asyncio.create_task(news_loop())
            logger.info("💼 Запуск трекинга портфолио...")
            portfolio_task = asyncio.create_task(portfolio_loop())
            logger.info("🔌 Запуск WebSocket подключений...")
            websocket_task = asyncio.create_task(start_websocket_connections())
            logger.info("🧹 Запуск очистки кэша алертов...")
            cleanup_task = asyncio.create_task(cleanup_alert_cache())
            logger.info("🤖 Запуск обновления токенов из Telegram...")
            telegram_tokens_task = asyncio.create_task(telegram_tokens_loop())
            
            await asyncio.gather(
                onchain_task, cex_task, dex_task, social_task, 
                analytics_task, official_sources_task, news_task,
                portfolio_task, websocket_task, cleanup_task, telegram_tokens_task
            )
    except Exception as e:
        log_error("Главный цикл мониторинга", e)
        logger.critical(f"❌ Критическая ошибка в main: {e}")
    finally:
        # Удаляем файл блокировки при завершении
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except:
            pass
        logger.info("=== Crypto Monitor завершил работу ===")

# --- Работа с точкой отсчёта алерта ---
def get_alert_reference(reference_key: str):
    """Получает точку отсчёта алерта для токена и биржи"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT last_price, last_volume, last_update FROM alert_reference WHERE reference_key = ?
            ''', (reference_key,))
            row = cursor.fetchone()
            if row:
                return {'last_price': row[0], 'last_volume': row[1], 'last_update': row[2]}
            return None
    except Exception as e:
        logger.error(f"Ошибка получения точки отсчёта алерта: {e}")
        return None

def set_alert_reference(reference_key: str, price: float, volume: float):
    """Устанавливает точку отсчёта алерта для токена и биржи"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO alert_reference (reference_key, last_price, last_volume, last_update)
                    VALUES (?, ?, ?, ?)
                ''', (reference_key, price, volume, int(time.time())))
    except Exception as e:
        logger.error(f"Ошибка установки точки отсчёта алерта: {e}")

def get_token_info(symbol: str) -> Dict[str, Any]:
    """Получение информации о токене"""
    try:
        # Пока возвращаем базовую информацию
        # В будущем можно добавить API для получения возраста токена
        return {
            'symbol': symbol,
            'age_days': 180,  # Примерное значение
            'holders_count': 0  # Будет заполнено из on-chain данных
        }
    except Exception as e:
        logger.error(f"Ошибка получения информации о токене {symbol}: {e}")
        return {}

def update_realtime_data_with_telegram_tokens():
    """Обновляет realtime_data токенами из Telegram бота"""
    try:
        if not TELEGRAM_BOT_AVAILABLE:
            return
        
        # Создаем экземпляр DexScreenerMonitor для получения токенов
        dex_monitor = DexScreenerMonitor()
        
        # Получаем все токены всех пользователей
        all_tokens = []
        try:
            # Получаем список всех пользователей из базы данных
            conn = sqlite3.connect(dex_monitor.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT user_id FROM user_tokens")
            user_ids = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            # Получаем токены для каждого пользователя
            for user_id in user_ids:
                user_tokens = dex_monitor.get_user_tokens(user_id)
                all_tokens.extend(user_tokens)
        except Exception as e:
            logger.error(f"Ошибка получения токенов из базы данных: {e}")
            return
        
        # Обновляем realtime_data для каждого токена
        for token_data in all_tokens:
            token_address = token_data['token_address']
            token_name = token_data.get('token_name', token_address[:8])
            token_symbol = token_data.get('token_symbol', token_address[:8])
            
            # Получаем актуальные данные токена
            try:
                token_info = dex_monitor.get_token_info(token_address)
                if token_info and 'pairs' in token_info and token_info['pairs']:
                    # Берем первую пару (обычно самая ликвидная)
                    pair = token_info['pairs'][0]
                    
                    # Извлекаем данные
                    price_usd = float(pair.get('priceUsd', 0))
                    volume_24h = float(pair.get('volume', {}).get('h24', 0))
                    price_change_24h = float(pair.get('priceChange', {}).get('h24', 0))
                    
                    # Обновляем realtime_data
                    if token_symbol not in realtime_data:
                        realtime_data[token_symbol] = {
                            'price': 0.0,
                            'volume_24h': 0.0,
                            'price_change_24h': 0.0,
                            'last_update': None,
                            'source': None,
                            'technical_indicators': {},
                            'alerts': [],
                            'token_address': token_address,
                            'token_name': token_name
                        }
                    
                    realtime_data[token_symbol].update({
                        'price': price_usd,
                        'volume_24h': volume_24h,
                        'price_change_24h': price_change_24h,
                        'last_update': datetime.now(),
                        'source': 'DexScreener',
                        'token_address': token_address,
                        'token_name': token_name
                    })
                    
                    logger.info(f"Обновлены данные для токена {token_symbol}: цена=${price_usd:.6f}, объем=${volume_24h:.2f}, изменение={price_change_24h:.2f}%")
                    
            except Exception as e:
                logger.error(f"Ошибка обновления данных для токена {token_symbol}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка обновления realtime_data токенами из Telegram: {e}")

# Глобальные переменные для кэширования риск-скоринга
risk_cache = {}
risk_cache_ttl = 300  # 5 минут кэш

def get_cached_risk_score(symbol: str, data_hash: str) -> Optional[Dict[str, Any]]:
    """Получить кэшированный риск-скоринг"""
    if symbol in risk_cache:
        cache_entry = risk_cache[symbol]
        if cache_entry['hash'] == data_hash and time.time() - cache_entry['timestamp'] < risk_cache_ttl:
            return cache_entry['data']
    return None

def set_cached_risk_score(symbol: str, data_hash: str, risk_data: Dict[str, Any]):
    """Сохранить риск-скоринг в кэш"""
    risk_cache[symbol] = {
        'hash': data_hash,
        'timestamp': time.time(),
        'data': risk_data
    }

def calculate_data_hash(data: Dict[str, Any]) -> str:
    """Создать хеш данных для кэширования"""
    # Создаем стабильный хеш из ключевых данных
    key_data = {
        'volume_24h': data.get('volume_24h', 0),
        'price_change_24h': data.get('price_change_24h', 0),
        'holders_count': data.get('holders_count', 0),
        'rsi': data.get('rsi', 0),
        'volatility': data.get('volatility', 0)
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

DEX_ALERT_THRESHOLD_PCT = 10  # Порог изменения в % для алерта

async def get_token_dexscreener_info(session, token):
    """
    Получить данные по токену с Dexscreener (объём, цена, ликвидность).
    """
    try:
        # Используем правильный URL для Dexscreener
        url = f'https://api.dexscreener.com/latest/dex/tokens/{token["contract"]}'
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data and 'pairs' in data and data['pairs']:
                    return data
                else:
                    logger.info(f'[DEXSCREENER] Нет данных для {token["symbol"]}')
                    return None
            else:
                logger.warning(f'[DEXSCREENER] HTTP {resp.status} для {token["symbol"]}')
                return None
    except Exception as e:
        logger.warning(f'[DEXSCREENER] Ошибка для {token["symbol"]}: {e}')
        return None

async def get_token_defillama_info(session, token):
    """
    Получить TVL токена с DefiLlama.
    """
    try:
        # DefiLlama API для TVL
        url = f'https://api.llama.fi/tvl/{token["chain"]}/{token["contract"]}'
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, (int, float)) and data > 0:
                    return {'tvl': data}
                else:
                    logger.info(f'[DEFILLAMA] Нет TVL данных для {token["symbol"]}')
                    return None
            else:
                logger.warning(f'[DEFILLAMA] HTTP {resp.status} для {token["symbol"]}')
                return None
    except Exception as e:
        logger.warning(f'[DEFILLAMA] Ошибка для {token["symbol"]}: {e}')
        return None

async def get_token_geckoterminal_info(session, token):
    """
    Получить данные по токену с GeckoTerminal (цена, ликвидность).
    """
    try:
        # Для примера: https://api.geckoterminal.com/api/v2/simple/networks/{chain}/token_price/{address}
        url = f'https://api.geckoterminal.com/api/v2/simple/networks/{token["chain"]}/token_price/{token["contract"]}'
        async with session.get(url, timeout=10) as resp:
            data = await resp.json()
            return data
    except Exception as e:
        logger.warning(f'[GECKOTERMINAL] Ошибка: {e}')
        return None



TVL_ALERT_THRESHOLD_PCT = 50  # Порог изменения TVL в % для алерта

def get_last_tvl(symbol: str, minutes: int = 60) -> float:
    """Получить TVL токена N минут назад из БД"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tvl, timestamp FROM token_data
            WHERE symbol = ? AND timestamp <= datetime('now', ?)
            ORDER BY timestamp DESC LIMIT 1
        ''', (symbol, f'-{minutes} minutes'))
        row = cursor.fetchone()
        conn.close()
        if row:
            return float(row[0])
        return 0.0
    except Exception as e:
        logger.error(f"Ошибка получения TVL из БД: {e}")
        return 0.0



async def parse_rss_news(session: aiohttp.ClientSession, rss_url: str) -> List[Dict[str, Any]]:
    """Парсинг RSS ленты и извлечение новостей"""
    try:
        async with session.get(rss_url, timeout=10) as resp:
            if resp.status == 200:
                content = await resp.text()
                
                # Проверяем, что контент не пустой и содержит XML
                if not content or len(content.strip()) < 100:
                    logger.warning(f"RSS контент слишком короткий для {rss_url}")
                    return []
                
                # Пытаемся исправить неверный XML
                try:
                    # Удаляем неверные символы в начале
                    if content.startswith('<?xml'):
                        # Ищем начало RSS
                        rss_start = content.find('<rss')
                        if rss_start > 0:
                            content = content[rss_start:]
                    
                    # Очищаем неверные символы
                    content = re.sub(r'[^\x20-\x7E\n\r\t]', '', content)
                    
                    # Парсим XML
                    root = ET.fromstring(content)
                except ET.ParseError as xml_error:
                    logger.warning(f"XML парсинг ошибка для {rss_url}: {xml_error}")
                    # Пробуем альтернативный парсинг
                    try:
                        # Ищем элементы item вручную
                        news_items = []
                        item_pattern = r'<item[^>]*>(.*?)</item>'
                        items = re.findall(item_pattern, content, re.DOTALL)
                        
                        for item_content in items[:10]:  # Максимум 10 новостей
                            title_match = re.search(r'<title[^>]*>(.*?)</title>', item_content, re.DOTALL)
                            description_match = re.search(r'<description[^>]*>(.*?)</description>', item_content, re.DOTALL)
                            link_match = re.search(r'<link[^>]*>(.*?)</link>', item_content, re.DOTALL)
                            pub_date_match = re.search(r'<pubDate[^>]*>(.*?)</pubDate>', item_content, re.DOTALL)
                            
                            if title_match:
                                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                                description = ""
                                if description_match:
                                    soup = BeautifulSoup(description_match.group(1), 'html.parser')
                                    description = soup.get_text().strip()
                                
                                news_items.append({
                                    'title': title,
                                    'description': description,
                                    'link': link_match.group(1).strip() if link_match else '',
                                    'pub_date': pub_date_match.group(1).strip() if pub_date_match else '',
                                    'source': rss_url
                                })
                        
                        return news_items
                    except Exception as alt_error:
                        logger.error(f"Альтернативный RSS парсинг тоже не сработал для {rss_url}: {alt_error}")
                        return []
                
                news_items = []
                
                # Ищем элементы item (стандарт RSS)
                for item in root.findall('.//item'):
                    title = item.find('title')
                    description = item.find('description')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    
                    if title is not None and title.text:
                        # Очищаем HTML теги из заголовка
                        clean_title = re.sub(r'<[^>]+>', '', title.text).strip()
                        
                        # Очищаем HTML теги из описания
                        clean_description = ""
                        if description is not None and description.text:
                            # Удаляем HTML теги
                            soup = BeautifulSoup(description.text, 'html.parser')
                            clean_description = soup.get_text().strip()
                        
                        news_items.append({
                            'title': clean_title,
                            'description': clean_description,
                            'link': link.text if link is not None else '',
                            'pub_date': pub_date.text if pub_date is not None else '',
                            'source': rss_url
                        })
                
                return news_items
            else:
                logger.warning(f"RSS error {resp.status} для {rss_url}")
                return []
                
    except Exception as e:
        logger.error(f"Ошибка парсинга RSS {rss_url}: {e}")
        return []

async def analyze_news_with_ai(news_data: Dict[str, Any], token_symbol: str) -> Optional[Dict[str, Any]]:
    """Анализ новости с помощью ChatGPT"""
    try:
        if not OPENAI_API_KEY:
            logger.warning("OpenAI API ключ не настроен для анализа новости")
            await send_alert('CRITICAL', f"🤖 AI АНАЛИЗ НЕДОСТУПЕН\n\n❌ OpenAI API ключ не настроен\n⚠️ Новость о {token_symbol} не будет обработана")
            return None
        
        # Формируем промпт для анализа
        prompt = f"""
        Проанализируй эту новость о криптовалюте {token_symbol}:

        Заголовок: {news_data['title']}
        Описание: {news_data['description']}
        Источник: {news_data['source']}

        Дай краткий анализ на русском языке в следующем формате:

        КРАТКОЕ СОДЕРЖАНИЕ: [2-3 предложения о чем новость]
        ВЛИЯНИЕ НА ТОКЕН: [как может повлиять на цену {token_symbol} - позитивно/негативно/нейтрально]
        ОБОСНОВАНИЕ: [почему такое влияние ожидается]

        Ответь структурированно и кратко.
        """
        
        response = await analyze_with_chatgpt(prompt, "news_analysis")
        
        if response and 'choices' in response:
            analysis_text = response['choices'][0]['message']['content']
            
            # Парсим ответ
            summary = ""
            impact = ""
            sentiment = "neutral"
            
            lines = analysis_text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('КРАТКОЕ СОДЕРЖАНИЕ:'):
                    summary = line.replace('КРАТКОЕ СОДЕРЖАНИЕ:', '').strip()
                elif line.startswith('ВЛИЯНИЕ НА ТОКЕН:'):
                    impact_text = line.replace('ВЛИЯНИЕ НА ТОКЕН:', '').strip()
                    if 'позитивно' in impact_text.lower():
                        sentiment = 'positive'
                    elif 'негативно' in impact_text.lower():
                        sentiment = 'negative'
                    impact = impact_text
                elif line.startswith('ОБОСНОВАНИЕ:'):
                    # Добавляем обоснование к влиянию
                    reasoning = line.replace('ОБОСНОВАНИЕ:', '').strip()
                    if impact:
                        impact += f" {reasoning}"
            
            # Если не удалось распарсить, используем весь текст
            if not summary and not impact:
                summary = analysis_text[:200] + "..." if len(analysis_text) > 200 else analysis_text
                impact = "Анализ выполнен, влияние требует дополнительной оценки"
            
            return {
                'summary': summary,
                'impact': impact,
                'sentiment': sentiment,
                'full_analysis': analysis_text
            }
        else:
            logger.error("Ошибка получения ответа от OpenAI API")
            await send_alert('CRITICAL', f"🤖 AI АНАЛИЗ НЕДОСТУПЕН\n\n❌ Ошибка получения ответа от OpenAI API\n⚠️ Новость о {token_symbol} не будет обработана")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка AI анализа новости: {e}")
        await send_alert('CRITICAL', f"🤖 AI АНАЛИЗ НЕДОСТУПЕН\n\n❌ Ошибка: {e}\n⚠️ Новость о {token_symbol} не будет обработана")
        return None



async def health_check() -> Dict[str, Any]:
    """
    Проверка состояния всех компонентов системы мониторинга
    Возвращает статус каждого компонента и общий статус системы
    """
    health_status = {
        'timestamp': datetime.now().isoformat(),
        'overall_status': 'healthy',
        'components': {},
        'errors': []
    }
    
    try:
        # Проверка базы данных
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM token_data')
                count = cursor.fetchone()[0]
                health_status['components']['database'] = {
                    'status': 'healthy',
                    'message': f'Connected, {count} records in token_data'
                }
        except Exception as e:
            health_status['components']['database'] = {
                'status': 'unhealthy',
                'message': f'Database error: {e}'
            }
            health_status['errors'].append(f'Database: {e}')
            health_status['overall_status'] = 'degraded'
        
        # Проверка конфигурации
        try:
            required_keys = [
                'etherscan.api_key',
                'telegram.bot_token',
                'telegram.chat_id'
            ]
            missing_keys = []
            for key_path in required_keys:
                keys = key_path.split('.')
                value = config.api_config
                for key in keys:
                    if key in value:
                        value = value[key]
                    else:
                        missing_keys.append(key_path)
                        break
            
            if missing_keys:
                health_status['components']['configuration'] = {
                    'status': 'warning',
                    'message': f'Missing keys: {missing_keys}'
                }
            else:
                health_status['components']['configuration'] = {
                    'status': 'healthy',
                    'message': 'All required keys configured'
                }
        except Exception as e:
            health_status['components']['configuration'] = {
                'status': 'unhealthy',
                'message': f'Configuration error: {e}'
            }
            health_status['errors'].append(f'Configuration: {e}')
            health_status['overall_status'] = 'degraded'
        
        # Проверка real-time данных
        try:
            fuel_data = realtime_data.get('FUEL', {})
            arc_data = realtime_data.get('ARC', {})
            
            fuel_fresh = (fuel_data.get('last_update') and 
                         (datetime.now() - fuel_data['last_update']).total_seconds() < 300)
            arc_fresh = (arc_data.get('last_update') and 
                        (datetime.now() - arc_data['last_update']).total_seconds() < 300)
            
            if fuel_fresh and arc_fresh:
                health_status['components']['realtime_data'] = {
                    'status': 'healthy',
                    'message': 'Real-time data is fresh'
                }
            else:
                health_status['components']['realtime_data'] = {
                    'status': 'warning',
                    'message': 'Real-time data may be stale'
                }
        except Exception as e:
            health_status['components']['realtime_data'] = {
                'status': 'unhealthy',
                'message': f'Real-time data error: {e}'
            }
            health_status['errors'].append(f'Real-time data: {e}')
            health_status['overall_status'] = 'degraded'
        
        # Проверка обработки ошибок
        try:
            if ERROR_HANDLING_AVAILABLE:
                from error_handler import error_handler
                stats = error_handler.get_stats()
                if stats['total_errors'] > 100:
                    health_status['components']['error_handling'] = {
                        'status': 'warning',
                        'message': f'High error count: {stats["total_errors"]}'
                    }
                else:
                    health_status['components']['error_handling'] = {
                        'status': 'healthy',
                        'message': f'Error handling active, {stats["total_errors"]} total errors'
                    }
            else:
                health_status['components']['error_handling'] = {
                    'status': 'warning',
                    'message': 'Using fallback error handling'
                }
        except Exception as e:
            health_status['components']['error_handling'] = {
                'status': 'unhealthy',
                'message': f'Error handling error: {e}'
            }
            health_status['errors'].append(f'Error handling: {e}')
            health_status['overall_status'] = 'degraded'
        
        # Проверка алертов
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM alerts 
                    WHERE timestamp >= datetime('now', '-1 hour')
                ''')
                recent_alerts = cursor.fetchone()[0]
                
                if recent_alerts > 50:
                    health_status['components']['alerts'] = {
                        'status': 'warning',
                        'message': f'High alert volume: {recent_alerts} in last hour'
                    }
                else:
                    health_status['components']['alerts'] = {
                        'status': 'healthy',
                        'message': f'Alert system normal, {recent_alerts} recent alerts'
                    }
        except Exception as e:
            health_status['components']['alerts'] = {
                'status': 'unhealthy',
                'message': f'Alert system error: {e}'
            }
            health_status['errors'].append(f'Alerts: {e}')
            health_status['overall_status'] = 'degraded'
        
        logger.info(f"Health check completed: {health_status['overall_status']}")
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'unhealthy',
            'components': {},
            'errors': [f'Health check error: {e}']
        }

@app.route('/webhook/tradingview', methods=['POST'])
async def tradingview_webhook():
    """Webhook для получения алертов от TradingView"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data received'}), 400
        
        # Парсим данные от TradingView
        symbol = data.get('symbol', 'UNKNOWN')
        strategy = data.get('strategy', 'TradingView Alert')
        action = data.get('action', 'INFO')
        price = data.get('price', 0)
        message = data.get('message', 'TradingView alert received')
        
        # Создаем алерт
        alert_level = 'CRITICAL' if action in ['BUY', 'SELL'] else 'WARNING'
        alert_message = f"[TradingView] {strategy}: {message} | Цена: ${price}"
        
        await send_alert(alert_level, alert_message, symbol)
        
        # Логируем webhook
        logger.info(f"TradingView webhook received: {symbol} - {action} - {message}")
        
        return jsonify({'success': True, 'message': 'Alert processed'})
        
    except Exception as e:
        logger.error(f"Error processing TradingView webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Функция для отправки push-уведомления через Pushover
def send_mobile_alert(level, message):
    """Отправка push-уведомления через Pushover"""
    try:
        user_key = os.getenv('PUSHOVER_USER_KEY')
        api_token = os.getenv('PUSHOVER_API_TOKEN')
        if not user_key or not api_token:
            logger.warning('Pushover не настроен, пропуск push-уведомления')
            return
        payload = {
            'token': api_token,
            'user': user_key,
            'message': message,
            'title': f'Crypto Alert: {level}',
            'priority': 1 if level == 'CRITICAL' else 0
        }
        resp = requests.post('https://api.pushover.net/1/messages.json', data=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(f'Ошибка отправки Pushover: {resp.text}')
    except Exception as e:
        logger.error(f'Ошибка отправки push-уведомления: {e}')

def was_news_alert_sent(news_hash: str, symbol: str, hours: int = 24) -> bool:
    """Проверяет, была ли уже отправлена новость с таким хешем"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM social_alerts 
                WHERE token = ? AND link = ? AND timestamp > datetime('now', '-{} hours')
            '''.format(hours), (symbol, news_hash))
            count = cursor.fetchone()[0]
            return count > 0
    except Exception as e:
        logger.error(f"Ошибка проверки отправленных новостей: {e}")
        return False

def save_news_alert_sent(news_hash: str, symbol: str, priority: str):
    """Сохраняет информацию об отправленной новости"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO social_alerts 
                (timestamp, source, level, original_text, translated_text, link, token, keywords, important_news)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                'news_analysis',
                priority,
                f"News alert for {symbol}",
                f"News alert for {symbol}",
                news_hash,
                symbol,
                json.dumps([symbol.lower()]),
                1 if priority in ['high', 'medium'] else 0
            ))
    except Exception as e:
        logger.error(f"Ошибка сохранения отправленной новости: {e}")

def is_news_relevant_for_token(news_data: Dict[str, Any], symbol: str) -> bool:
    """Проверяет, релевантна ли новость для данного токена"""
    try:
        # Ключевые слова для каждого токена (более строгие)
        token_keywords = {
            'FUEL': ['fuel network', 'fuel protocol', 'fuel token', 'fuel blockchain', 'fuel ecosystem'],
            'ARC': ['arc protocol', 'arc token', 'arc blockchain', 'arc ecosystem', 'ai rig complex', 'ai rig', 'rig complex'],
            'VIRTUAL': ['virtuals protocol', 'virtual token', 'virtual blockchain', 'virtual ecosystem']
        }
        
        # Запрещенные слова (новости с этими словами НЕ должны приходить)
        forbidden_words = ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'cardano', 'ada', 'polkadot', 'dot']
        
        # Получаем ключевые слова для токена
        keywords = token_keywords.get(symbol.upper(), [symbol.lower()])
        
        # Текст для поиска (заголовок + описание)
        search_text = f"{news_data.get('title', '')} {news_data.get('description', '')}".lower()
        
        # Проверяем запрещенные слова
        for forbidden in forbidden_words:
            if forbidden in search_text:
                logger.info(f"Новость содержит запрещенное слово '{forbidden}' для {symbol}: {news_data.get('title', '')[:50]}...")
                return False
        
        # Проверяем наличие ключевых слов (только точные совпадения)
        for keyword in keywords:
            if keyword.lower() in search_text:
                logger.info(f"Найдено ключевое слово '{keyword}' для {symbol} в новости: {news_data.get('title', '')[:50]}...")
                return True
        
        logger.info(f"Новость не содержит ключевых слов для {symbol}: {news_data.get('title', '')[:50]}...")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка проверки релевантности новости для {symbol}: {e}")
        return False

async def send_official_post_alert(post_data: Dict[str, Any], symbol: str, platform: str, account: str):
    """Отправляет алерт о посте из официального источника"""
    try:
        # Генерируем хеш поста для дедупликации
        post_hash = generate_news_hash(post_data)
        
        # Проверяем, не был ли уже отправлен этот пост
        if was_news_alert_sent(post_hash, symbol, hours=24):
            logger.info(f"Пост уже был отправлен для {symbol}: {post_data.get('title', '')[:50]}...")
            return
        
        # Формируем сообщение
        title = post_data.get('title', 'Без заголовка')
        description = post_data.get('description', '')
        link = post_data.get('link', '')
        pub_date = post_data.get('pub_date', '')
        
        # Определяем эмодзи для платформы
        platform_emoji = {
            'Twitter': '🐦',
            'Discord': '💬',
            'GitHub': '📚',
            'Telegram': '📱'
        }.get(platform, '📢')
        
        message = f"""[{platform_emoji} ОФИЦИАЛЬНЫЙ {platform.upper()}] {symbol}

👤 {account}

📝 {title}

📄 {description[:200]}{'...' if len(description) > 200 else ''}

📅 {pub_date}

🔗 {link}"""
        
        # Отправляем алерт
        await send_alert(
            'HIGH',
            message,
            symbol,
            {
                'source': f'official_{platform.lower()}',
                'url': link,
                'account': account,
                'platform': platform
            }
        )
        
        # Сохраняем информацию об отправленном посте
        save_news_alert_sent(post_hash, symbol, 'high')
        
        logger.info(f"Отправлен алерт о посте {symbol} из {platform}: {account}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки алерта о посте: {e}")

async def send_github_commit_alert(commit_data: Dict[str, Any], symbol: str, owner: str, repo: str):
    """Отправляет алерт о коммите в GitHub репозитории"""
    try:
        # Создаем уникальный идентификатор коммита
        commit_hash = commit_data.get('sha', '')[:8]
        commit_id = f"{owner}/{repo}/{commit_hash}"
        
        # Проверяем, не был ли уже отправлен этот коммит
        if was_news_alert_sent(commit_id, symbol, hours=24):
            logger.info(f"Коммит уже был отправлен для {symbol}: {commit_id}")
            return
        
        # Извлекаем данные коммита
        commit_info = commit_data.get('commit', {})
        author = commit_info.get('author', {})
        message = commit_info.get('message', '')
        
        # Ограничиваем длину сообщения
        short_message = message.split('\n')[0][:100] + ('...' if len(message.split('\n')[0]) > 100 else '')
        
        # Формируем сообщение
        message_text = f"""[📚 ОФИЦИАЛЬНЫЙ GITHUB] {symbol}

👤 Автор: {author.get('name', 'Unknown')}

📝 Коммит: {short_message}

🔗 Репозиторий: {owner}/{repo}

🔗 Коммит: https://github.com/{owner}/{repo}/commit/{commit_hash}

📅 Дата: {author.get('date', 'Unknown')}"""
        
        # Отправляем алерт
        await send_alert(
            'HIGH',
            message_text,
            symbol,
            {
                'source': 'official_github',
                'url': f"https://github.com/{owner}/{repo}/commit/{commit_hash}",
                'repo': f"{owner}/{repo}",
                'commit_hash': commit_hash
            }
        )
        
        # Сохраняем информацию об отправленном коммите
        save_news_alert_sent(commit_id, symbol, 'high')
        
        logger.info(f"Отправлен алерт о коммите {symbol} в {owner}/{repo}: {commit_hash}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки алерта о коммите: {e}")

async def send_discord_server_alert(server_data: Dict[str, Any], symbol: str, invite_code: str):
    """Отправляет алерт о Discord сервере"""
    try:
        # Создаем уникальный идентификатор сервера
        server_id = f"discord_{symbol}_{invite_code}"
        
        # Проверяем, не был ли уже отправлен этот сервер
        if was_news_alert_sent(server_id, symbol, hours=24):
            logger.info(f"Discord сервер уже был отправлен для {symbol}: {server_id}")
            return
        
        # Извлекаем данные сервера
        server_name = server_data.get('guild', {}).get('name', 'Unknown Server')
        member_count = server_data.get('approximate_member_count', 0)
        online_count = server_data.get('approximate_presence_count', 0)
        
        # Формируем сообщение
        message_text = f"""[💬 ОФИЦИАЛЬНЫЙ DISCORD] {symbol}

🏠 Сервер: {server_name}

👥 Участников: {member_count:,}

🟢 Онлайн: {online_count:,}

🔗 Присоединиться: https://discord.gg/{invite_code}"""
        
        # Отправляем алерт
        await send_alert(
            'MEDIUM',
            message_text,
            symbol,
            {
                'source': 'official_discord',
                'url': f"https://discord.gg/{invite_code}",
                'server_name': server_name,
                'member_count': member_count
            }
        )
        
        # Сохраняем информацию об отправленном сервере
        save_news_alert_sent(server_id, symbol, 'medium')
        
        logger.info(f"Отправлен алерт о Discord сервере {symbol}: {server_name}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки алерта о Discord сервере: {e}")

def generate_news_hash(news_data: Dict[str, Any]) -> str:
    """Генерирует уникальный хеш для новости"""
    import hashlib
    
    # Создаем строку из ключевых полей новости
    key_data = f"{news_data.get('title', '')}{news_data.get('link', '')}{news_data.get('source', '')}"
    
    # Генерируем MD5 хеш
    return hashlib.md5(key_data.encode('utf-8')).hexdigest()

async def check_aerodrome(session: aiohttp.ClientSession, token: Dict) -> Dict[str, Any]:
    """Получение данных с Aerodrome DEX (Base)"""
    try:
        symbol = token['symbol']
        logger.debug(f"Запрос Aerodrome для {symbol}")
        
        # Aerodrome API endpoint для Base
        url = f"https://api.aerodrome.finance/v1/pairs"
        
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                
                # Ищем пару с нашим токеном
                target_pair = None
                for pair in data.get('pairs', []):
                    if (symbol.lower() in pair.get('token0', {}).get('symbol', '').lower() or 
                        symbol.lower() in pair.get('token1', {}).get('symbol', '').lower()):
                        target_pair = pair
                        break
                
                if not target_pair:
                    logger.warning(f"Aerodrome: пара не найдена для {symbol}")
                    return {'error': 'Pair not found'}
                
                # Извлекаем данные
                price_usd = float(target_pair.get('priceUsd', 0))
                volume_24h = float(target_pair.get('volume24h', 0))
                liquidity_usd = float(target_pair.get('liquidityUsd', 0))
                
                # Расчет изменения цены (если доступно)
                price_change_24h = 0.0
                if 'priceChange24h' in target_pair:
                    price_change_24h = float(target_pair['priceChange24h'])
                
                return {
                    'price': price_usd,
                    'volume_24h': volume_24h,
                    'price_change_24h': price_change_24h,
                    'liquidity_usd': liquidity_usd,
                    'source': 'aerodrome_base'
                }
            else:
                logger.warning(f"Aerodrome HTTP ошибка: {response.status}")
                return {'error': f'HTTP {response.status}'}
                
    except Exception as e:
        logger.error(f"Ошибка Aerodrome для {token['symbol']}: {e}")
        return {'error': 'Failed to fetch data'}

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Мониторинг остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}") 