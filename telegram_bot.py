#!/usr/bin/env python3
"""
Интерактивный Telegram бот для мониторинга криптовалют
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, ConversationHandler, filters
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import os
from dotenv import load_dotenv
import aiohttp
import asyncio
from dataclasses import dataclass
import threading
import time
import requests



# Загружаем переменные окружения
load_dotenv('config.env')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
DB_PATH = 'crypto_monitor.db'

# Список токенов для мониторинга
TOKENS = ['FUEL', 'ARC', 'URO', 'XION', 'AI16Z', 'SAHARA', 'VIRTUAL', 'BID', 'MANTA', 'ANON']

# Состояния для ConversationHandler (мониторинг токенов)
WAITING_TOKEN_ADDRESS = 1
WAITING_VOLUME_THRESHOLD = 2
WAITING_CHECK_INTERVAL = 3

# Хранилище временных данных пользователей
user_states: Dict[int, Dict[str, Any]] = {}

# Data classes для мониторинга токенов
@dataclass
class TokenConfig:
    user_id: int
    token_address: str
    volume_threshold: float
    check_interval: int
    added_at: datetime

@dataclass
class VolumeData:
    token_address: str
    volume_24h: float
    volume_change_24h: float
    price: float
    price_change_24h: float
    timestamp: datetime



class DexScreenerMonitor:
    """Класс для работы с DexScreener API"""
    
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest"
        self.db_path = "token_monitor.db"
        self.json_path = "user_tokens.json"
        self.init_database()
        self.load_user_tokens()
    
    def init_database(self):
        """Инициализация базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token_address TEXT NOT NULL,
                        volume_threshold REAL NOT NULL,
                        price_threshold REAL DEFAULT 0,
                        check_interval INTEGER NOT NULL,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, token_address)
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS volume_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token_address TEXT NOT NULL,
                        volume_24h REAL NOT NULL,
                        volume_change_24h REAL NOT NULL,
                        price REAL NOT NULL,
                        price_change_24h REAL NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS peak_values (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token_address TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        peak_price REAL NOT NULL,
                        peak_volume REAL NOT NULL,
                        last_alert_price REAL NOT NULL,
                        last_alert_volume REAL NOT NULL,
                        last_alert_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(token_address, user_id)
                    )
                ''')
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")
    
    def load_user_tokens(self):
        """Загрузка токенов пользователей из JSON"""
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    self.user_tokens = json.load(f)
            else:
                self.user_tokens = {}
        except Exception as e:
            logger.error(f"Ошибка загрузки токенов: {e}")
            self.user_tokens = {}
    
    def save_user_tokens(self):
        """Сохранение токенов пользователей в JSON"""
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(self.user_tokens, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Ошибка сохранения токенов: {e}")
    
    def get_token_info(self, token_address: str) -> Optional[Dict]:
        """Получение информации о токене через DexScreener API"""
        try:
            url = f"{self.base_url}/dex/tokens/{token_address}"
            logger.info(f"Запрос к DexScreener API: {url}")
            
            response = requests.get(url, timeout=10)
            logger.info(f"Статус ответа DexScreener: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Получены данные от DexScreener: {data}")
                
                if data.get('pairs') and len(data['pairs']) > 0:
                    pair = data['pairs'][0]  # Берем первую пару
                    return {
                        'address': pair.get('tokenAddress'),
                        'name': pair.get('baseToken', {}).get('name'),
                        'symbol': pair.get('baseToken', {}).get('symbol'),
                        'price': float(pair.get('priceUsd', 0)),
                        'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
                        'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0)),
                        'liquidity': float(pair.get('liquidity', {}).get('usd', 0))
                    }
                else:
                    logger.warning(f"Токен {token_address} не найден в DexScreener или нет торговых пар")
            else:
                logger.warning(f"DexScreener вернул статус {response.status_code}")
                    
            return None
        except Exception as e:
            logger.error(f"Ошибка получения информации о токене {token_address}: {e}")
            return None
    
    def add_token(self, user_id: int, token_address: str, volume_threshold: float, price_threshold: float, check_interval: int) -> bool:
        """Добавление токена для мониторинга"""
        try:
            # Проверяем существование токена
            token_info = self.get_token_info(token_address)
            if not token_info:
                return False
            
            # Сохраняем в БД
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO user_tokens 
                    (user_id, token_address, volume_threshold, price_threshold, check_interval)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, token_address, volume_threshold, price_threshold, check_interval))
                conn.commit()
            
            # Сохраняем в JSON
            if str(user_id) not in self.user_tokens:
                self.user_tokens[str(user_id)] = []
            
            token_config = {
                'token_address': token_address,
                'volume_threshold': volume_threshold,
                'price_threshold': price_threshold,
                'check_interval': check_interval,
                'monitor_price': True,
                'added_at': datetime.now().isoformat(),
                'token_info': token_info
            }
            
            # Удаляем если уже существует
            self.user_tokens[str(user_id)] = [
                t for t in self.user_tokens[str(user_id)] 
                if t['token_address'] != token_address
            ]
            
            self.user_tokens[str(user_id)].append(token_config)
            self.save_user_tokens()
            
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления токена: {e}")
            return False
    
    def remove_token(self, user_id: int, token_address: str) -> bool:
        """Удаление токена из мониторинга"""
        try:
            # Удаляем из БД
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM user_tokens 
                    WHERE user_id = ? AND token_address = ?
                ''', (user_id, token_address))
                conn.commit()
            
            # Удаляем из JSON
            if str(user_id) in self.user_tokens:
                self.user_tokens[str(user_id)] = [
                    t for t in self.user_tokens[str(user_id)] 
                    if t['token_address'] != token_address
                ]
                self.save_user_tokens()
            
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления токена: {e}")
            return False
    
    def get_user_tokens(self, user_id: int) -> List[Dict]:
        """Получение токенов пользователя"""
        return self.user_tokens.get(str(user_id), [])
    
    def check_volume_changes(self, user_id: int) -> List[Dict]:
        """Проверка изменений объема и цены для токенов пользователя"""
        alerts = []
        user_tokens = self.get_user_tokens(user_id)
        
        for token_config in user_tokens:
            try:
                token_info = self.get_token_info(token_config['token_address'])
                if token_info:
                    volume_threshold = token_config.get('volume_threshold', 0)
                    price_threshold = token_config.get('price_threshold', 0)
                    monitor_price = token_config.get('monitor_price', True)
                    
                    current_price = token_info['price']
                    current_volume = token_info['volume_24h']
                    token_address = token_config['token_address']
                    
                    # Обновляем пиковые значения
                    self.update_peak_values(token_address, user_id, current_price, current_volume)
                    
                    # Проверяем изменение объема
                    if volume_threshold > 0:
                        if self.should_send_volume_alert(token_address, user_id, current_volume, volume_threshold):
                            # Вычисляем изменение от последнего алерта
                            peak_data = self.get_peak_values(token_address, user_id)
                            if peak_data['last_alert_volume'] > 0:
                                volume_change = ((current_volume - peak_data['last_alert_volume']) / peak_data['last_alert_volume']) * 100
                            else:
                                # Для первого алерта показываем изменение за 24 часа
                                volume_change = token_info.get('volume_change_24h', 0)
                            
                            alerts.append({
                                'token_address': token_address,
                                'token_name': token_info.get('name', 'Unknown'),
                                'type': 'volume',
                                'change': volume_change,
                                'threshold': volume_threshold,
                                'current_price': current_price,
                                'current_volume': current_volume
                            })
                            
                            # Обновляем время последнего алерта объема
                            self.update_peak_values(token_address, user_id, current_price, current_volume, 
                                                  alert_volume=current_volume)
                    
                    # Проверяем изменение цены
                    if monitor_price and price_threshold > 0:
                        if self.should_send_price_alert(token_address, user_id, current_price, price_threshold):
                            # Вычисляем изменение от последнего алерта
                            peak_data = self.get_peak_values(token_address, user_id)
                            if peak_data['last_alert_price'] > 0:
                                price_change = ((current_price - peak_data['last_alert_price']) / peak_data['last_alert_price']) * 100
                            else:
                                # Для первого алерта показываем изменение за 24 часа
                                price_change = token_info.get('price_change_24h', 0)
                            
                            alerts.append({
                                'token_address': token_address,
                                'token_name': token_info.get('name', 'Unknown'),
                                'type': 'price',
                                'change': price_change,
                                'threshold': price_threshold,
                                'current_price': current_price,
                                'current_volume': current_volume
                            })
                            
                            # Обновляем время последнего алерта цены
                            self.update_peak_values(token_address, user_id, current_price, current_volume, 
                                                  alert_price=current_price)
            except Exception as e:
                logger.error(f"Ошибка проверки токена {token_config['token_address']}: {e}")
        
        return alerts
    
    async def save_volume_data(self, token_address: str, volume_data: VolumeData):
        """Сохранение данных объема в БД"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO volume_history 
                    (token_address, volume_24h, volume_change_24h, price, price_change_24h)
                    VALUES (?, ?, ?, ?, ?)
                ''', (token_address, volume_data.volume_24h, volume_data.volume_change_24h,
                     volume_data.price, volume_data.price_change_24h))
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения данных объема: {e}")
    
    def get_peak_values(self, token_address: str, user_id: int) -> Dict:
        """Получить пиковые значения для токена и пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT peak_price, peak_volume, last_alert_price, last_alert_volume, last_alert_time
                    FROM peak_values 
                    WHERE token_address = ? AND user_id = ?
                ''', (token_address, user_id))
                row = cursor.fetchone()
                
                if row:
                    return {
                        'peak_price': row[0],
                        'peak_volume': row[1],
                        'last_alert_price': row[2],
                        'last_alert_volume': row[3],
                        'last_alert_time': row[4]
                    }
                else:
                    return {
                        'peak_price': 0.0,
                        'peak_volume': 0.0,
                        'last_alert_price': 0.0,
                        'last_alert_volume': 0.0,
                        'last_alert_time': None
                    }
        except Exception as e:
            logger.error(f"Ошибка получения пиковых значений: {e}")
            return {
                'peak_price': 0.0,
                'peak_volume': 0.0,
                'last_alert_price': 0.0,
                'last_alert_volume': 0.0,
                'last_alert_time': None
            }
    
    def update_peak_values(self, token_address: str, user_id: int, current_price: float, current_volume: float, alert_price: float = None, alert_volume: float = None):
        """Обновить пиковые значения"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем текущие пиковые значения
                peak_data = self.get_peak_values(token_address, user_id)
                
                # Обновляем пиковые значения если текущие больше
                new_peak_price = max(peak_data['peak_price'], current_price)
                new_peak_volume = max(peak_data['peak_volume'], current_volume)
                
                # Если переданы значения алерта, обновляем их
                if alert_price is not None:
                    new_alert_price = alert_price
                else:
                    new_alert_price = peak_data['last_alert_price']
                
                if alert_volume is not None:
                    new_alert_volume = alert_volume
                else:
                    new_alert_volume = peak_data['last_alert_volume']
                
                cursor.execute('''
                    INSERT OR REPLACE INTO peak_values 
                    (token_address, user_id, peak_price, peak_volume, last_alert_price, last_alert_volume, last_alert_time)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (token_address, user_id, new_peak_price, new_peak_volume, new_alert_price, new_alert_volume))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Ошибка обновления пиковых значений: {e}")
    
    def should_send_price_alert(self, token_address: str, user_id: int, current_price: float, price_threshold: float) -> bool:
        """Проверить, нужно ли отправить алерт цены"""
        try:
            peak_data = self.get_peak_values(token_address, user_id)
            
            # Если это первый алерт или цена достигла нового пика
            if peak_data['last_alert_price'] == 0.0:
                return True
            
            # Вычисляем изменение от последнего алерта
            price_change = ((current_price - peak_data['last_alert_price']) / peak_data['last_alert_price']) * 100
            
            # Отправляем алерт только если изменение превышает порог
            return abs(price_change) >= price_threshold
            
        except Exception as e:
            logger.error(f"Ошибка проверки алерта цены: {e}")
            return True
    
    def should_send_volume_alert(self, token_address: str, user_id: int, current_volume: float, volume_threshold: float) -> bool:
        """Проверить, нужно ли отправить алерт объема"""
        try:
            peak_data = self.get_peak_values(token_address, user_id)
            
            # Если это первый алерт или объем достиг нового пика
            if peak_data['last_alert_volume'] == 0.0:
                return True
            
            # Вычисляем изменение от последнего алерта
            volume_change = ((current_volume - peak_data['last_alert_volume']) / peak_data['last_alert_volume']) * 100
            
            # Отправляем алерт только если изменение превышает порог
            return abs(volume_change) >= volume_threshold
            
        except Exception as e:
            logger.error(f"Ошибка проверки алерта объема: {e}")
            return True


class CryptoMonitorBot:
    def __init__(self):
        self.updater = None
        self.dex_monitor = DexScreenerMonitor()
        self.loop = asyncio.new_event_loop()
        self.bg_thread = threading.Thread(target=self._start_async_loop, daemon=True)
        self.bg_thread.start()
    
    def safe_edit_message(self, query, text, reply_markup=None, parse_mode=None):
        """Безопасное редактирование сообщения с обработкой ошибок"""
        try:
            query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                # Игнорируем эту ошибку - сообщение не изменилось
                logger.debug("Сообщение не изменилось, пропускаем")
                pass
            else:
                logger.error(f"Ошибка редактирования сообщения: {e}")
                # Пытаемся отправить новое сообщение
                try:
                    if self.updater and self.updater.bot:
                        self.updater.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode
                        )
                except Exception as send_error:
                    logger.error(f"Ошибка отправки нового сообщения: {send_error}")

    def _start_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.background_volume_checker()

    def background_volume_checker(self):
        while True:
            try:
                # Получаем всех пользователей
                user_ids = list(self.dex_monitor.user_tokens.keys())
                for user_id in user_ids:
                    alerts = self.dex_monitor.check_volume_changes(int(user_id))
                    for alert in alerts:
                        self.send_alert(int(user_id), alert)
            except Exception as e:
                logger.error(f"Ошибка фоновой проверки токенов: {e}")
            time.sleep(300)  # 5 минут

    def send_alert(self, user_id, alert):
        try:
            chat_id = user_id  # Можно заменить на отдельный chat_id, если нужно
            
            alert_type = alert.get('type', 'volume')
            if alert_type == 'volume':
                text = (
                    f"📊 <b>Алерт объема!</b>\n"
                    f"Токен: <code>{alert['token_address']}</code> | {alert['token_name']}\n"
                    f"Изменение объема: {alert['change']:+.2f}% (порог {alert['threshold']}%)\n"
                    f"Текущий объем: ${alert['current_volume']:,.0f}\n"
                    f"Цена: ${alert['current_price']:.6f}"
                )
            else:  # price
                text = (
                    f"💰 <b>Алерт цены!</b>\n"
                    f"Токен: <code>{alert['token_address']}</code> | {alert['token_name']}\n"
                    f"Изменение цены: {alert['change']:+.2f}% (порог {alert['threshold']}%)\n"
                    f"Текущая цена: ${alert['current_price']:.6f}\n"
                    f"Объем 24ч: ${alert['current_volume']:,.0f}"
                )
            
            if self.updater:
                self.updater.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")
    
    def start(self, update: Update, context: CallbackContext):
        """Обработчик команды /start"""
        keyboard = [
            [InlineKeyboardButton("📊 Токены и цены", callback_data="tokens")],
            [InlineKeyboardButton("📈 Объемы торгов", callback_data="volumes")],
            [InlineKeyboardButton("⚡ Быстрые алерты", callback_data="alerts")],
            [InlineKeyboardButton("🔍 Детальная аналитика", callback_data="analytics")],
            [InlineKeyboardButton("📊 Рыночная сводка", callback_data="summary")],
            [InlineKeyboardButton("🔗 Мониторинг токенов", callback_data="token_monitor")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "🤖 **Crypto Monitor Bot**\n\n"
            "Добро пожаловать в систему мониторинга криптовалют!\n\n"
            "**Основные возможности:**\n"
            "• 📊 Мониторинг токенов (объем + цена)\n"
            "• 🔔 Уведомления о важных изменениях\n"
            "• 🌐 Поддержка всех популярных сетей\n\n"
            "Выберите нужную опцию:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def button_handler(self, update: Update, context: CallbackContext):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        
        # Быстрый ответ для улучшения UX
        try:
            query.answer()
        except Exception as e:
            logger.warning(f"Ошибка ответа на callback query: {e}")
            # Продолжаем выполнение даже если ответ не удался
        
        # Обработка в отдельном потоке для улучшения производительности
        import threading
        thread = threading.Thread(target=self._process_button, args=(query, context))
        thread.daemon = True
        thread.start()
    
    def _process_button(self, query, context):
        """Обработка кнопки в отдельном потоке"""
        try:
            if query.data == "tokens":
                self.show_tokens(query, context)
            elif query.data == "volumes":
                self.show_volumes(query, context)
            elif query.data == "alerts":
                self.show_alerts(query, context)
            elif query.data == "analytics":
                self.show_analytics(query, context)
            elif query.data == "summary":
                self.show_summary(query, context)
            elif query.data == "token_monitor":
                self.show_token_monitor_menu(query, context)
            elif query.data == "settings":
                self.show_settings(query, context)
            elif query.data == "back_to_main":
                self.show_main_menu(query, context)
            elif query.data.startswith("token_"):
                token = query.data.split("_")[1]
                self.show_token_details(query, context, token)
            elif query.data == "refresh":
                self.refresh_data(query, context)
            # Обработка кнопок мониторинга токенов
            elif query.data == "add_token":
                self.add_token_command(query, context)
            elif query.data == "list_tokens":
                self.list_tokens_command(query, context)
            elif query.data == "remove_token":
                self.remove_token_command(query, context)
            elif query.data == "check_volumes":
                self.check_volume_command(query, context)
            elif query.data == "refresh_tokens":
                self.list_tokens_command(query, context)
            elif query.data == "check_all_volumes":
                self.check_volume_command(query, context)
            elif query.data == "cancel_remove":
                self.safe_edit_message(query, "❌ Удаление отменено")
            elif query.data.startswith("remove_"):
                self.handle_remove_token(query, context)
            elif query.data.startswith("interval_"):
                self.handle_interval_selection(query, context)
            elif query.data == "notifications":
                self.show_notification_settings(query, context)
            elif query.data == "thresholds":
                self.show_threshold_settings(query, context)
            elif query.data == "auto_refresh":
                self.show_auto_refresh_settings(query, context)
            elif query.data == "notification_settings":
                self.show_notification_settings(query, context)
            elif query.data in ["disable_all", "enable_all"]:
                self.toggle_notifications(query, context)
            elif query.data in ["edit_thresholds", "reset_thresholds"]:
                self.handle_threshold_action(query, context)
            elif query.data in ["fast_mode", "eco_mode"]:
                self.handle_performance_mode(query, context)
            else:
                logger.warning(f"Неизвестный callback_data: {query.data}")
                
        except Exception as e:
            logger.error(f"Ошибка обработки кнопки {query.data}: {e}")
            try:
                self.safe_edit_message(
                    query,
                    "❌ Произошла ошибка при обработке запроса",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
                    ]])
                )
            except:
                pass
    
    def show_main_menu(self, query, context):
        """Показать главное меню"""
        keyboard = [
            [InlineKeyboardButton("📊 Токены и цены", callback_data="tokens")],
            [InlineKeyboardButton("📈 Объемы торгов", callback_data="volumes")],
            [InlineKeyboardButton("⚡ Быстрые алерты", callback_data="alerts")],
            [InlineKeyboardButton("🔍 Детальная аналитика", callback_data="analytics")],
            [InlineKeyboardButton("📊 Рыночная сводка", callback_data="summary")],
            [InlineKeyboardButton("🔗 Мониторинг токенов", callback_data="token_monitor")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        self.safe_edit_message(
            query,
            "🤖 **Crypto Monitor Bot**\n\n"
            "Выберите нужную опцию:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def show_tokens(self, query, context):
        """Показать все токены с ценами"""
        try:
            # Получаем последние данные из БД
            token_data = self.get_latest_token_data()
            
            message = "💰 **ТОКЕНЫ И ЦЕНЫ**\n\n"
            
            for token in TOKENS:
                if token in token_data:
                    data = token_data[token]
                    price = data.get('price', 0)
                    volume = data.get('volume_24h', 0)
                    change = data.get('price_change_24h', 0)
                    
                    # Эмодзи для изменения цены
                    emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
                    
                    message += f"{emoji} **{token}**: ${price:.6f}\n"
                    message += f"   📊 ${volume:,.0f} | {change:+.2f}%\n\n"
                else:
                    message += f"⚪ **{token}**: Нет данных\n\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")],
                [InlineKeyboardButton("📊 Рыночная сводка", callback_data="summary")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            self.safe_edit_message(
                query,
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка показа токенов: {e}")
            self.safe_edit_message(
                query,
                "❌ Ошибка получения данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
                ]])
            )
    
    def show_volumes(self, query, context):
        """Показать объемы торгов"""
        try:
            token_data = self.get_latest_token_data()
            
            # Сортируем по объему
            sorted_tokens = sorted(
                [(token, data) for token, data in token_data.items() if 'volume_24h' in data],
                key=lambda x: x[1]['volume_24h'],
                reverse=True
            )
            
            message = "📈 **ОБЪЕМЫ ТОРГОВ**\n\n"
            
            for i, (token, data) in enumerate(sorted_tokens[:10], 1):
                volume = data['volume_24h']
                price = data.get('price', 0)
                
                # Эмодзи для топ-3
                rank_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                
                message += f"{rank_emoji} **{token}**: ${volume:,.0f}\n"
                message += f"   💰 ${price:.6f}\n\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")],
                [InlineKeyboardButton("📊 Токены и цены", callback_data="tokens")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            self.safe_edit_message(
                query,
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка показа объемов: {e}")
            self.safe_edit_message(
                query,
                "❌ Ошибка получения данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
                ]])
            )
    
    def show_summary(self, query, context):
        """Показать рыночную сводку"""
        try:
            token_data = self.get_latest_token_data()
            
            # Топ по объему
            top_volume = sorted(
                [(token, data) for token, data in token_data.items() if 'volume_24h' in data],
                key=lambda x: x[1]['volume_24h'],
                reverse=True
            )[:5]
            
            # Топ по росту
            top_gainers = sorted(
                [(token, data) for token, data in token_data.items() if 'price_change_24h' in data],
                key=lambda x: x[1]['price_change_24h'],
                reverse=True
            )[:5]
            
            # Топ по падению
            top_losers = sorted(
                [(token, data) for token, data in token_data.items() if 'price_change_24h' in data],
                key=lambda x: x[1]['price_change_24h']
            )[:5]
            
            message = "📊 **РЫНОЧНАЯ СВОДКА**\n\n"
            
            message += "🔥 **Топ по объему:**\n"
            for i, (token, data) in enumerate(top_volume, 1):
                volume = data['volume_24h']
                change = data.get('price_change_24h', 0)
                emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
                message += f"{i}. {token}: ${volume:,.0f} ({emoji}{change:+.2f}%)\n"
            
            message += "\n📈 **Топ по росту:**\n"
            for i, (token, data) in enumerate(top_gainers, 1):
                change = data['price_change_24h']
                message += f"{i}. {token}: 🟢+{change:.2f}%\n"
            
            message += "\n📉 **Топ по падению:**\n"
            for i, (token, data) in enumerate(top_losers, 1):
                change = data['price_change_24h']
                message += f"{i}. {token}: 🔴{change:.2f}%\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")],
                [InlineKeyboardButton("📊 Токены и цены", callback_data="tokens")],
                [InlineKeyboardButton("📈 Объемы", callback_data="volumes")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            self.safe_edit_message(
                query,
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка показа сводки: {e}")
            self.safe_edit_message(
                query,
                "❌ Ошибка получения данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
                ]])
            )
    
    def show_alerts(self, query, context):
        """Показать активные алерты"""
        try:
            # Получаем последние алерты из БД
            alerts = self.get_recent_alerts()
            
            if not alerts:
                message = "✅ **АКТИВНЫЕ АЛЕРТЫ**\n\n"
                message += "Нет активных алертов"
            else:
                message = "⚡ **ПОСЛЕДНИЕ АЛЕРТЫ**\n\n"
                
                for alert in alerts[:10]:  # Показываем последние 10
                    level = alert['level']
                    symbol = alert.get('token_symbol', 'N/A')
                    message_text = alert['message'][:100] + "..." if len(alert['message']) > 100 else alert['message']
                    timestamp = alert['timestamp']
                    
                    # Эмодзи для уровня
                    level_emoji = "🚨" if level == "CRITICAL" else "⚠️" if level == "WARNING" else "📊"
                    
                    message += f"{level_emoji} **{symbol}** ({level})\n"
                    message += f"   {message_text}\n"
                    message += f"   📅 {timestamp}\n\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")],
                [InlineKeyboardButton("📊 Рыночная сводка", callback_data="summary")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            self.safe_edit_message(
                query,
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка показа алертов: {e}")
            self.safe_edit_message(
                query,
                "❌ Ошибка получения данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
                ]])
            )
    
    def show_analytics(self, query, context):
        """Показать детальную аналитику"""
        try:
            # Создаем кнопки для каждого токена
            keyboard = []
            for i in range(0, len(TOKENS), 2):
                row = []
                row.append(InlineKeyboardButton(TOKENS[i], callback_data=f"token_{TOKENS[i]}"))
                if i + 1 < len(TOKENS):
                    row.append(InlineKeyboardButton(TOKENS[i + 1], callback_data=f"token_{TOKENS[i + 1]}"))
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            self.safe_edit_message(
                query,
                "🔍 **ДЕТАЛЬНАЯ АНАЛИТИКА**\n\n"
                "Выберите токен для подробного анализа:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка показа аналитики: {e}")
            query.edit_message_text(
                "❌ Ошибка получения данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
                ]])
            )
    
    def show_token_details(self, query, context, token):
        """Показать детали токена"""
        try:
            token_data = self.get_latest_token_data()
            
            if token not in token_data:
                self.safe_edit_message(
                    query,
                    f"❌ Нет данных для токена {token}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("⬅️ Назад", callback_data="analytics")
                    ]])
                )
                return
            
            data = token_data[token]
            price = data.get('price', 0)
            volume = data.get('volume_24h', 0)
            change = data.get('price_change_24h', 0)
            
            # Получаем корректные данные из основной БД
            price_history = self.get_correct_price_history(token, hours=24)
            
            message = f"🔍 **АНАЛИЗ {token}**\n\n"
            message += f"💰 **Цена**: ${price:.6f}\n"
            message += f"📊 **Объем**: ${volume:,.0f}\n"
            message += f"📈 **Изменение**: {change:+.2f}%\n"
            
            if price_history and len(price_history) > 1:
                prices = [p[0] for p in price_history if p[0] > 0]
                if prices:
                    min_price = min(prices)
                    max_price = max(prices)
                    # Проверяем разумность данных
                    if max_price < price * 10 and min_price > price * 0.1:  # Разумные пределы
                        message += f"📉 **Мин**: ${min_price:.6f}\n"
                        message += f"📈 **Макс**: ${max_price:.6f}\n"
                    else:
                        message += f"📉 **Мин**: ${price:.6f}\n"
                        message += f"📈 **Макс**: ${price:.6f}\n"
                else:
                    message += f"📉 **Мин**: ${price:.6f}\n"
                    message += f"📈 **Макс**: ${price:.6f}\n"
            else:
                message += f"📉 **Мин**: ${price:.6f}\n"
                message += f"📈 **Макс**: ${price:.6f}\n"
            
            # Получаем последние алерты для токена
            token_alerts = self.get_token_alerts(token)
            if token_alerts:
                message += f"\n⚠️ **Последние алерты**: {len(token_alerts)}\n"
            
            keyboard = [
                [InlineKeyboardButton("📊 История цен", callback_data=f"history_{token}")],
                [InlineKeyboardButton("📈 Тех. индикаторы", callback_data=f"indicators_{token}")],
                [InlineKeyboardButton("⬅️ Назад к аналитике", callback_data="analytics")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            self.safe_edit_message(
                query,
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка показа деталей токена: {e}")
            self.safe_edit_message(
                query,
                "❌ Ошибка получения данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Назад", callback_data="analytics")
                ]])
            )
    
    def show_settings(self, query, context):
        """Показать настройки"""
        message = "⚙️ **НАСТРОЙКИ**\n\n"
        message += "🔔 **Уведомления**: Включены\n"
        message += "📊 **Интервал обновления**: 30 сек\n"
        message += "🚨 **Пороги алертов**:\n"
        message += "   • Критический: 25%\n"
        message += "   • Предупреждение: 15%\n"
        message += "   • Информация: 8%\n\n"
        message += "📈 **Пороги объема**:\n"
        message += "   • Критический: 150%\n"
        message += "   • Информация: 80%\n\n"
        message += "🎯 **Дополнительные настройки**:\n"
        message += "   • Автообновление: Включено\n"
        message += "   • Уведомления о новых токенах: Включено\n"
        message += "   • Детальные алерты: Включено"
        
        keyboard = [
            [InlineKeyboardButton("🔔 Настройки уведомлений", callback_data="notifications")],
            [InlineKeyboardButton("📊 Настройки порогов", callback_data="thresholds")],
            [InlineKeyboardButton("🔄 Автообновление", callback_data="auto_refresh")],
            [InlineKeyboardButton("📱 Уведомления", callback_data="notification_settings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        self.safe_edit_message(
            query,
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def show_notification_settings(self, query, context):
        """Показать настройки уведомлений"""
        message = "🔔 **НАСТРОЙКИ УВЕДОМЛЕНИЙ**\n\n"
        message += "📱 **Типы уведомлений**:\n"
        message += "   ✅ Критические алерты (25%+)\n"
        message += "   ✅ Предупреждения (15%+)\n"
        message += "   ✅ Информационные (8%+)\n"
        message += "   ✅ Новые токены\n"
        message += "   ✅ Изменения объема\n\n"
        message += "⏰ **Частота уведомлений**:\n"
        message += "   • Мгновенно для критических\n"
        message += "   • Каждые 5 минут для обычных\n"
        message += "   • Сводка каждый час"
        
        keyboard = [
            [InlineKeyboardButton("🔕 Отключить все", callback_data="disable_all")],
            [InlineKeyboardButton("🔔 Включить все", callback_data="enable_all")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        self.safe_edit_message(
            query,
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def show_threshold_settings(self, query, context):
        """Показать настройки порогов"""
        message = "📊 **НАСТРОЙКИ ПОРОГОВ**\n\n"
        message += "🚨 **Пороги алертов**:\n"
        message += "   • Критический: 25% (🔴)\n"
        message += "   • Предупреждение: 15% (🟡)\n"
        message += "   • Информация: 8% (🟢)\n\n"
        message += "📈 **Пороги объема**:\n"
        message += "   • Критический: 150% от среднего\n"
        message += "   • Информация: 80% от среднего\n\n"
        message += "💰 **Пороги цены**:\n"
        message += "   • Минимальная: $0.000001\n"
        message += "   • Максимальная: $1000"
        
        keyboard = [
            [InlineKeyboardButton("📈 Изменить пороги", callback_data="edit_thresholds")],
            [InlineKeyboardButton("🔄 Сбросить", callback_data="reset_thresholds")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        self.safe_edit_message(
            query,
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def show_auto_refresh_settings(self, query, context):
        """Показать настройки автообновления"""
        message = "🔄 **АВТООБНОВЛЕНИЕ**\n\n"
        message += "⏱️ **Текущие интервалы**:\n"
        message += "   • Данные токенов: 30 сек\n"
        message += "   • Объемы торгов: 60 сек\n"
        message += "   • On-chain данные: 5 мин\n"
        message += "   • Аналитика: 10 мин\n\n"
        message += "📊 **Статус**:\n"
        message += "   ✅ Автообновление включено\n"
        message += "   ✅ Кэширование активно\n"
        message += "   ✅ Оптимизация памяти\n\n"
        message += "⚡ **Производительность**:\n"
        message += "   • Быстрые ответы: < 1 сек\n"
        message += "   • Использование CPU: ~5%\n"
        message += "   • Память: ~50 MB"
        
        keyboard = [
            [InlineKeyboardButton("⚡ Быстрый режим", callback_data="fast_mode")],
            [InlineKeyboardButton("🐌 Экономичный", callback_data="eco_mode")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        self.safe_edit_message(
            query,
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def refresh_data(self, query, context):
        """Обновить данные"""
        try:
            query.answer("🔄 Обновление данных...")
            
            # Показываем обновленную сводку
            self.show_summary(query, context)
            
        except Exception as e:
            logger.error(f"Ошибка обновления данных: {e}")
            self.safe_edit_message(
                query,
                "❌ Ошибка обновления данных",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
                ]])
            )
    
    def toggle_notifications(self, query, context):
        """Включить/выключить уведомления"""
        action = query.data
        if action == "disable_all":
            message = "🔕 **УВЕДОМЛЕНИЯ ОТКЛЮЧЕНЫ**\n\n"
            message += "Все уведомления временно отключены.\n"
            message += "Для включения нажмите 'Включить все'."
        else:
            message = "🔔 **УВЕДОМЛЕНИЯ ВКЛЮЧЕНЫ**\n\n"
            message += "Все уведомления активированы:\n"
            message += "✅ Критические алерты\n"
            message += "✅ Предупреждения\n"
            message += "✅ Информационные\n"
            message += "✅ Новые токены"
        
        keyboard = [
            [InlineKeyboardButton("🔔 Настройки уведомлений", callback_data="notifications")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        self.safe_edit_message(
            query,
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def handle_threshold_action(self, query, context):
        """Обработать действия с порогами"""
        action = query.data
        if action == "reset_thresholds":
            message = "🔄 **ПОРОГИ СБРОШЕНЫ**\n\n"
            message += "Восстановлены стандартные значения:\n"
            message += "• Критический: 25%\n"
            message += "• Предупреждение: 15%\n"
            message += "• Информация: 8%"
        else:
            message = "📈 **ИЗМЕНЕНИЕ ПОРОГОВ**\n\n"
            message += "Для изменения порогов используйте команды:\n"
            message += "/set_critical <значение>\n"
            message += "/set_warning <значение>\n"
            message += "/set_info <значение>"
        
        keyboard = [
            [InlineKeyboardButton("📊 Настройки порогов", callback_data="thresholds")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        self.safe_edit_message(
            query,
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def handle_performance_mode(self, query, context):
        """Обработать режимы производительности"""
        action = query.data
        if action == "fast_mode":
            message = "⚡ **БЫСТРЫЙ РЕЖИМ АКТИВИРОВАН**\n\n"
            message += "Оптимизация для скорости:\n"
            message += "• Обновление: каждые 15 сек\n"
            message += "• Кэширование: агрессивное\n"
            message += "• Уведомления: мгновенные\n"
            message += "• Использование CPU: ~10%"
        else:
            message = "🐌 **ЭКОНОМИЧНЫЙ РЕЖИМ АКТИВИРОВАН**\n\n"
            message += "Оптимизация для экономии ресурсов:\n"
            message += "• Обновление: каждые 60 сек\n"
            message += "• Кэширование: умеренное\n"
            message += "• Уведомления: каждые 10 мин\n"
            message += "• Использование CPU: ~2%"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Автообновление", callback_data="auto_refresh")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        self.safe_edit_message(
            query,
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def get_latest_token_data(self) -> Dict[str, Any]:
        """Получить последние данные токенов из БД"""
        try:
            # Получаем данные из основной БД мониторинга
            with sqlite3.connect('crypto_monitor.db') as conn:
                cursor = conn.cursor()
                
                # Получаем последние данные для всех токенов из token_data
                cursor.execute('''
                    SELECT 
                        symbol,
                        price,
                        volume_24h,
                        timestamp
                    FROM token_data 
                    WHERE timestamp = (
                        SELECT MAX(timestamp) 
                        FROM token_data t2 
                        WHERE t2.symbol = token_data.symbol
                    )
                    ORDER BY symbol
                ''')
                
                rows = cursor.fetchall()
                result = {}
                
                for row in rows:
                    symbol, price, volume_24h, timestamp = row
                    result[symbol] = {
                        'price': price or 0,
                        'volume_24h': volume_24h or 0,
                        'price_change_24h': 0,  # Пока не вычисляем изменение
                        'timestamp': timestamp
                    }
                
                return result
                
        except Exception as e:
            logger.error(f"Ошибка получения данных токенов: {e}")
            return {}
    
    def get_recent_alerts(self) -> List[Dict[str, Any]]:
        """Получить последние алерты"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT level, message, token_symbol, timestamp
                    FROM alerts
                    ORDER BY timestamp DESC
                    LIMIT 10
                ''')
                
                rows = cursor.fetchall()
                result = []
                
                for row in rows:
                    level, message, token_symbol, timestamp = row
                    result.append({
                        'level': level,
                        'message': message,
                        'token_symbol': token_symbol,
                        'timestamp': timestamp
                    })
                
                return result
        except Exception as e:
            logger.error(f"Ошибка получения алертов: {e}")
            return []
    
    def get_token_alerts(self, token: str) -> List[Dict[str, Any]]:
        """Получить алерты для конкретного токена"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT level, message, timestamp
                    FROM alerts
                    WHERE token_symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT 5
                ''', (token,))
                
                rows = cursor.fetchall()
                result = []
                
                for row in rows:
                    level, message, timestamp = row
                    result.append({
                        'level': level,
                        'message': message,
                        'timestamp': timestamp
                    })
                
                return result
        except Exception as e:
            logger.error(f"Ошибка получения алертов токена: {e}")
            return []
    
    def get_correct_price_history(self, token: str, hours: int = 24) -> List[tuple]:
        """Получить корректную историю цен токена из основной БД"""
        try:
            with sqlite3.connect('crypto_monitor.db') as conn:
                cursor = conn.cursor()
                
                # Получаем данные за последние N часов
                cursor.execute('''
                    SELECT price, timestamp
                    FROM token_data
                    WHERE symbol = ?
                    AND timestamp >= datetime('now', '-{} hours')
                    ORDER BY timestamp DESC
                    LIMIT 100
                '''.format(hours), (token,))
                
                rows = cursor.fetchall()
                return [(float(row[0]), row[1]) for row in rows if row[0] is not None]
                
        except Exception as e:
            logger.error(f"Ошибка получения истории цен для {token}: {e}")
            return []
    
    def get_price_history(self, token: str, hours: int = 24) -> List[tuple]:
        """Получить историю цен токена"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT price, timestamp
                    FROM token_data
                    WHERE symbol = ?
                    AND timestamp >= datetime('now', '-{} hours')
                    ORDER BY timestamp DESC
                '''.format(hours), (token,))
                
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения истории цен: {e}")
            return []
    
    # ===== МЕТОДЫ МОНИТОРИНГА ТОКЕНОВ =====
    
    def show_token_monitor_menu(self, query, context):
        """Показать меню мониторинга токенов"""
        welcome_text = """
🔗 **МОНИТОРИНГ ТОКЕНОВ**

Добавляйте любые токены для отслеживания через DexScreener API.

**Возможности:**
• 📊 Отслеживание объема торгов (24ч)
• 💰 Отслеживание изменений цены (24ч)
• 🔔 Уведомления при превышении порогов
• 🌐 Поддержка всех сетей (Ethereum, BSC, Polygon, Solana)
• ⚙️ Гибкие настройки порогов и интервалов
• 🎯 Настраиваемые алерты (объем и/или цена)

**Поддерживаемые сети:**
• Ethereum, BSC, Polygon (EVM)
• Solana (SPL токены)

**Что отслеживается:**
• Изменения объема торгов за 24 часа
• Изменения цены токена за 24 часа
• Можно настроить отдельные пороги для каждого параметра

Выберите действие:
        """
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить токен", callback_data="add_token")],
            [InlineKeyboardButton("📋 Мои токены", callback_data="list_tokens")],
            [InlineKeyboardButton("🔍 Проверить объемы", callback_data="check_volumes")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    def add_token_command(self, query, context):
        """Начать процесс добавления токена"""
        user_id = query.from_user.id
        
        logger.info(f"Начало добавления токена для пользователя {user_id}")
        
        # Инициализируем состояние пользователя
        user_states[user_id] = {
            'step': 'waiting_address',
            'token_address': None,
            'volume_threshold': None,
            'price_threshold': None,
            'check_interval': 5,
            'monitor_volume': True,
            'monitor_price': True
        }
        
        query.edit_message_text(
            "🔗 **Добавление нового токена**\n\n"
            "Отправьте адрес контракта токена:\n\n"
            "**Поддерживаемые сети:**\n"
            "• Ethereum, BSC, Polygon: `0x1234567890123456789012345678901234567890`\n"
            "• Solana: `4YWy8JNjB4CLjG71hxGwzFXWd4DtpdvsAY2GqQ1Fbonk`\n\n"
            "**Что отслеживается:**\n"
            "• Изменения цены (24ч)\n"
            "• Изменения объема торгов (24ч)\n\n"
            "Используйте /cancel для отмены",
            parse_mode='Markdown'
        )
        
        # Переводим в состояние ожидания адреса
        context.user_data['waiting_token_address'] = True
    
    def handle_token_address(self, update, context):
        """Обработчик ввода адреса токена"""
        user_id = update.effective_user.id
        token_address = update.message.text.strip()
        
        logger.info(f"Получен адрес токена от пользователя {user_id}: {token_address}")
        
        # Проверяем, что пользователь в правильном состоянии
        if user_id not in user_states or user_states[user_id].get('step') != 'waiting_address':
            logger.warning(f"Пользователь {user_id} не в состоянии ожидания адреса")
            update.message.reply_text("❌ Ошибка состояния. Начните заново с /start")
            return
        
        # Проверяем формат адреса (поддерживаем EVM и Solana)
        is_valid_address = False
        
        # EVM адреса (Ethereum, BSC, Polygon и др.)
        if token_address.startswith('0x') and len(token_address) == 42:
            is_valid_address = True
        # Solana адреса (база58, обычно 32-44 символа)
        elif len(token_address) >= 32 and len(token_address) <= 44:
            # Проверяем, что это base58 строка
            try:
                import base58
                base58.b58decode(token_address)
                is_valid_address = True
            except:
                pass
        
        if not is_valid_address:
            update.message.reply_text(
                "❌ **Неверный формат адреса!**\n\n"
                "Поддерживаемые форматы:\n"
                "• **EVM адреса:** `0x1234567890123456789012345678901234567890`\n"
                "• **Solana адреса:** `4YWy8JNjB4CLjG71hxGwzFXWd4DtpdvsAY2GqQ1Fbonk`\n\n"
                "Попробуйте еще раз:",
                parse_mode='Markdown'
            )
            return
        
        # Сохраняем адрес
        user_states[user_id]['token_address'] = token_address
        user_states[user_id]['step'] = 'waiting_threshold'
        
        # Проверяем существование токена
        update.message.reply_text("🔍 Проверяю токен в DexScreener...")
        
        # Проверяем токен через DexScreener API
        try:
            # Используем синхронный запрос вместо asyncio
            import requests
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            logger.info(f"Запрос к DexScreener API: {url}")
            
            response = requests.get(url, timeout=10)
            logger.info(f"Статус ответа DexScreener: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Получены данные от DexScreener: {data}")
                
                if data.get('pairs') and len(data['pairs']) > 0:
                    pair = data['pairs'][0]  # Берем первую пару
                    token_info = {
                        'address': pair.get('tokenAddress'),
                        'name': pair.get('baseToken', {}).get('name'),
                        'symbol': pair.get('baseToken', {}).get('symbol'),
                        'price': float(pair.get('priceUsd', 0)),
                        'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
                        'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0)),
                        'liquidity': float(pair.get('liquidity', {}).get('usd', 0))
                    }
                    
                    update.message.reply_text(
                        f"✅ **Токен найден!**\n\n"
                        f"**Название:** {token_info.get('name', 'Unknown')}\n"
                        f"**Символ:** {token_info.get('symbol', 'Unknown')}\n"
                        f"**Цена:** ${token_info.get('price', 0):.6f}\n"
                        f"**Объем 24ч:** ${token_info.get('volume_24h', 0):,.0f}\n\n"
                        f"Теперь укажите % прироста объема для уведомления:\n"
                        f"Пример: `10` (уведомление при росте на 10%)",
                        parse_mode='Markdown'
                    )
                    logger.info(f"Токен {token_address} найден, переходим к вводу порога")
                else:
                    update.message.reply_text(
                        "❌ **Токен не найден!**\n\n"
                        "Проверьте правильность адреса и попробуйте еще раз.\n"
                        "Убедитесь, что токен торгуется на DEX.",
                        parse_mode='Markdown'
                    )
                    return
            else:
                update.message.reply_text(
                    f"❌ **Ошибка API DexScreener!**\n\n"
                    f"Статус: {response.status_code}\n"
                    "Попробуйте еще раз позже.",
                    parse_mode='Markdown'
                )
                return
        except Exception as e:
            logger.error(f"Ошибка проверки токена {token_address}: {e}")
            update.message.reply_text(
                f"❌ **Ошибка проверки токена:** {str(e)}\n\n"
                "Попробуйте еще раз.",
                parse_mode='Markdown'
            )
            return
    
    def handle_volume_threshold(self, update, context):
        """Обработчик ввода порогов объема и цены"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        logger.info(f"Получен порог от пользователя {user_id}: {text}")
        
        # Проверяем состояние пользователя
        current_step = user_states[user_id].get('step')
        
        if current_step == 'waiting_threshold':
            # Ввод порога объема
            try:
                volume_threshold = float(text)
                if volume_threshold <= 0 or volume_threshold > 1000:
                    raise ValueError("Недопустимое значение")
            except ValueError:
                update.message.reply_text(
                    "❌ **Неверное значение!**\n\n"
                    "Введите число от 0.1 до 1000.\n"
                    "Пример: `10` (уведомление при росте объема на 10%)",
                    parse_mode='Markdown'
                )
                return
            
            # Сохраняем порог объема
            user_states[user_id]['volume_threshold'] = volume_threshold
            user_states[user_id]['step'] = 'waiting_price_threshold'
            
            update.message.reply_text(
                f"📊 **Порог объема установлен: {volume_threshold}%**\n\n"
                f"Теперь укажите % изменения цены для уведомления:\n"
                f"Пример: `20` (уведомление при изменении цены на 20%)\n"
                f"Или отправьте `0` если не хотите отслеживать цену",
                parse_mode='Markdown'
            )
            
        elif current_step == 'waiting_price_threshold':
            # Ввод порога цены
            try:
                price_threshold = float(text)
                if price_threshold < 0 or price_threshold > 1000:
                    raise ValueError("Недопустимое значение")
            except ValueError:
                update.message.reply_text(
                    "❌ **Неверное значение!**\n\n"
                    "Введите число от 0 до 1000.\n"
                    "Пример: `20` (уведомление при изменении цены на 20%)\n"
                    f"Или отправьте `0` если не хотите отслеживать цену",
                    parse_mode='Markdown'
                )
                return
            
            # Сохраняем порог цены
            user_states[user_id]['price_threshold'] = price_threshold
            user_states[user_id]['monitor_price'] = price_threshold > 0
            user_states[user_id]['step'] = 'waiting_interval'
            
            # Показываем выбор интервала
            keyboard = [
                [InlineKeyboardButton("5 минут", callback_data="interval_5")],
                [InlineKeyboardButton("15 минут", callback_data="interval_15")],
                [InlineKeyboardButton("30 минут", callback_data="interval_30")],
                [InlineKeyboardButton("60 минут", callback_data="interval_60")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            volume_threshold = user_states[user_id]['volume_threshold']
            monitor_text = f"📊 **Пороги установлены:**\n• Объем: {volume_threshold}%\n• Цена: {price_threshold}%"
            
            update.message.reply_text(
                f"{monitor_text}\n\n"
                f"Выберите интервал проверки:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            update.message.reply_text("❌ Ошибка состояния. Начните заново с /start")
            return
    
    def handle_interval_selection(self, query, context):
        """Обработчик выбора интервала"""
        user_id = query.from_user.id
        interval = int(query.data.split('_')[1])
        
        # Сохраняем интервал
        user_states[user_id]['check_interval'] = interval
        
        # Получаем данные пользователя
        user_data = user_states[user_id]
        token_address = user_data['token_address']
        volume_threshold = user_data['volume_threshold']
        price_threshold = user_data.get('price_threshold', 0)
        monitor_price = user_data.get('monitor_price', True)
        
        # Добавляем токен в мониторинг
        try:
            success = self.dex_monitor.add_token(user_id, token_address, volume_threshold, price_threshold, interval)
            if success:
                logger.info(f"Токен {token_address} успешно добавлен для пользователя {user_id}")
            else:
                logger.error(f"Не удалось добавить токен {token_address} для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка добавления токена: {e}")
            success = False
        
        if success:
            monitor_text = f"• Объем: {volume_threshold}%"
            if monitor_price and price_threshold > 0:
                monitor_text += f"\n• Цена: {price_threshold}%"
            
            query.edit_message_text(
                f"✅ **Токен успешно добавлен!**\n\n"
                f"**Адрес:** `{token_address}`\n"
                f"**Пороги:**\n{monitor_text}\n"
                f"**Интервал:** {interval} минут\n\n"
                f"Теперь вы будете получать уведомления при превышении порогов!",
                parse_mode='Markdown'
            )
        else:
            query.edit_message_text(
                "❌ **Ошибка добавления токена!**\n\n"
                "Попробуйте еще раз или обратитесь к администратору.",
                parse_mode='Markdown'
            )
        
        # Очищаем состояние пользователя
        if user_id in user_states:
            del user_states[user_id]
        
        # Очищаем данные контекста
        context.user_data.clear()
    
    def handle_price_threshold(self, update, context):
        """Обработчик ввода порога цены"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        logger.info(f"Получен порог цены от пользователя {user_id}: {text}")
        
        try:
            price_threshold = float(text)
            if price_threshold <= 0:
                update.message.reply_text("❌ Порог цены должен быть больше 0. Попробуйте еще раз:")
                return
            
            # Сохраняем порог цены
            if user_id in user_states:
                user_states[user_id]['price_threshold'] = price_threshold
                user_states[user_id]['step'] = 'waiting_interval'
            
            # Показываем выбор интервала
            keyboard = [
                [InlineKeyboardButton("5 минут", callback_data="interval_5")],
                [InlineKeyboardButton("10 минут", callback_data="interval_10")],
                [InlineKeyboardButton("15 минут", callback_data="interval_15")],
                [InlineKeyboardButton("30 минут", callback_data="interval_30")],
                [InlineKeyboardButton("60 минут", callback_data="interval_60")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(
                f"✅ **Порог цены установлен: {price_threshold}%**\n\n"
                "Теперь выберите интервал проверки:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except ValueError:
            update.message.reply_text("❌ Введите корректное число для порога цены:")
    
    def list_tokens_command(self, query, context):
        """Показать список токенов пользователя"""
        user_id = query.from_user.id
        
        # Здесь должна быть интеграция с DexScreener монитором
        tokens = self.dex_monitor.get_user_tokens(user_id)
        if not tokens:
            tokens_text = "📋 **Ваши токены:**\n\nНет добавленных токенов.\n\nДобавьте новый токен для отслеживания!"
        else:
            tokens_text = "📋 **Ваши токены:**\n\n"
            for t in tokens:
                tokens_text += f"• `{t['token_address']}` | Порог: {t['volume_threshold']}% | Интервал: {t['check_interval']} мин\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_tokens")],
            [InlineKeyboardButton("➕ Добавить токен", callback_data="add_token")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="token_monitor")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            query.edit_message_text(
                tokens_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                # Игнорируем ошибку если сообщение не изменилось
                pass
            else:
                # Отправляем новое сообщение если не можем отредактировать
                query.message.reply_text(
                    tokens_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
    
    def remove_token_command(self, query, context):
        """Показать меню удаления токенов"""
        user_id = query.from_user.id
        tokens = self.dex_monitor.get_user_tokens(user_id)
        if not tokens:
            query.edit_message_text(
                "🗑 **Удаление токенов**\n\nНет токенов для удаления.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="token_monitor")]]),
                parse_mode='Markdown'
            )
            return
        keyboard = [[InlineKeyboardButton(f"Удалить {t['token_address'][:8]}...", callback_data=f"remove_{t['token_address']}")]
                    for t in tokens]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="token_monitor")])
        query.edit_message_text(
            "🗑 **Выберите токен для удаления:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    def handle_remove_token(self, query, context):
        token_address = query.data.split('_', 1)[1]
        user_id = query.from_user.id
        try:
            success = self.dex_monitor.remove_token(user_id, token_address)
        except Exception as e:
            logger.error(f"Ошибка удаления токена: {e}")
            success = False
        
        if success:
            query.edit_message_text(
                f"✅ **Токен удален!**\n\nАдрес: `{token_address[:10]}...{token_address[-8:]}`",
                parse_mode='Markdown'
            )
        else:
            query.edit_message_text(
                "❌ **Ошибка удаления токена!**",
                parse_mode='Markdown'
            )

    def check_volume_command(self, query, context):
        user_id = query.from_user.id
        try:
            alerts = self.dex_monitor.check_volume_changes(user_id)
        except Exception as e:
            logger.error(f"Ошибка проверки объемов: {e}")
            alerts = []
        
        if not alerts:
            text = "🔍 **Проверка объемов**\n\nНет токенов с превышением порога."
        else:
            text = "🔍 **Токены с превышением порога:**\n\n"
            for alert in alerts:
                text += (f"• `{alert['token_address']}` | {alert['token_name']}\n"
                        f"  Объем: {alert['current_volume']}, Изменение: {alert['volume_change']}% (порог {alert['threshold']}%)\n"
                        f"  Цена: ${alert['current_price']:.6f}\n\n")
        query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="token_monitor")]]),
            parse_mode='Markdown'
        )
    
    def my_alerts(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        tokens = self.dex_monitor.get_user_tokens(user_id)
        if not tokens:
            update.message.reply_text("У вас нет активных алертов.")
            return
        text = "\U0001F514 <b>Ваши алерты:</b>\n\n"
        keyboard = []
        for t in tokens:
            text += (f"• <code>{t['token_address']}</code> | Порог: {t['volume_threshold']}% | Интервал: {t['check_interval']} мин\n")
            keyboard.append([InlineKeyboardButton(f"Удалить {t['token_address'][:8]}...", callback_data=f"remove_alert_{t['token_address']}")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

    def remove_alert(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        tokens = self.dex_monitor.get_user_tokens(user_id)
        if not tokens:
            update.message.reply_text("Нет алертов для удаления.")
            return
        keyboard = [[InlineKeyboardButton(f"Удалить {t['token_address'][:8]}...", callback_data=f"remove_alert_{t['token_address']}")]
                    for t in tokens]
        update.message.reply_text(
            "Выберите алерт для удаления:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def clear_alerts(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        tokens = self.dex_monitor.get_user_tokens(user_id)
        if not tokens:
            update.message.reply_text("Нет алертов для удаления.")
            return
        try:
            for t in tokens:
                self.dex_monitor.remove_token(user_id, t['token_address'])
        except Exception as e:
            logger.error(f"Ошибка удаления алертов: {e}")
        update.message.reply_text("Все алерты удалены.")

    def handle_remove_alert(self, update: Update, context: CallbackContext):
        query = update.callback_query
        user_id = query.from_user.id
        token_address = query.data.split('_', 2)[2]
        try:
            success = self.dex_monitor.remove_token(user_id, token_address)
        except Exception as e:
            logger.error(f"Ошибка удаления алерта: {e}")
            success = False
        if success:
            query.edit_message_text(f"✅ Алерт по токену {token_address[:10]}... удалён.")
        else:
            query.edit_message_text("❌ Ошибка удаления алерта.")

    def handle_text_message(self, update: Update, context: CallbackContext):
        """Обработчик всех текстовых сообщений"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        logger.info(f"Получено текстовое сообщение от пользователя {user_id}: {text}")
        
        # Проверяем состояние пользователя
        if user_id not in user_states:
            update.message.reply_text("❌ Начните с команды /start")
            return
        
        user_state = user_states[user_id]
        current_step = user_state.get('step')
        
        logger.info(f"Пользователь {user_id} в состоянии: {current_step}")
        
        if current_step == 'waiting_address':
            # Обрабатываем ввод адреса токена
            self.handle_token_address(update, context)
        elif current_step == 'waiting_threshold':
            # Обрабатываем ввод порога объема
            self.handle_volume_threshold(update, context)
        elif current_step == 'waiting_price_threshold':
            # Обрабатываем ввод порога цены
            self.handle_price_threshold(update, context)
        else:
            update.message.reply_text("❌ Неизвестное состояние. Начните заново с /start")
            if user_id in user_states:
                del user_states[user_id]

    def run(self):
        """Запустить бота"""
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN не найден в переменных окружения")
            return
        
        try:
            self.updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
            dispatcher = self.updater.dispatcher
            
            # Добавляем обработчики
            dispatcher.add_handler(CommandHandler("start", self.start))
            dispatcher.add_handler(CommandHandler("my_alerts", self.my_alerts))
            dispatcher.add_handler(CommandHandler("remove_alert", self.remove_alert))
            dispatcher.add_handler(CommandHandler("clear_alerts", self.clear_alerts))
            dispatcher.add_handler(CallbackQueryHandler(self.handle_remove_alert, pattern='^remove_alert_'))
            dispatcher.add_handler(CallbackQueryHandler(self.button_handler))
            
            # Добавляем обработчики для добавления токенов
            dispatcher.add_handler(CallbackQueryHandler(self.add_token_command, pattern='^add_token$'))
            dispatcher.add_handler(CallbackQueryHandler(self.handle_interval_selection, pattern='^interval_'))
            
            # Добавляем обработчик для всех текстовых сообщений
            dispatcher.add_handler(MessageHandler(None, self.handle_text_message))
            
            # Добавляем обработчик ошибок
            def error_handler(update, context):
                logger.error(f"Ошибка в updater: {context.error}")
            
            dispatcher.add_error_handler(error_handler)
            
            # Запускаем бота с drop_pending_updates=True для избежания конфликтов
            logger.info("Telegram бот запущен")
            self.updater.start_polling(drop_pending_updates=True, timeout=30)
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            if "Conflict" in str(e):
                logger.info("Обнаружен конфликт, ожидаем 60 секунд...")
                time.sleep(60)
                logger.info("Перезапуск бота...")
                self.run()
            else:
                logger.error(f"Критическая ошибка: {e}")
                # Не перезапускаем при других ошибках
                return
    
    async def cancel(self, update, context):
        """Отмена операции"""
        user_id = update.effective_user.id
        
        if user_id in user_states:
            del user_states[user_id]
        
        update.message.reply_text(
            "❌ **Операция отменена**\n\n"
            "Используйте /start для возврата в главное меню.",
            parse_mode='Markdown'
        )
        
        return ConversationHandler.END

def main():
    """Главная функция"""
    bot = CryptoMonitorBot()
    bot.run()

if __name__ == "__main__":
    main() 