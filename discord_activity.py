"""
Discord Activity Scanner for New Funded Projects
Модуль для анализа активности Discord серверов новых проектов

Использование:
    from discord_activity import scan_discord
    
    scan_discord(
        invite_link="https://discord.gg/agoraxyz",
        project_name="Agora"
    )
"""

import os
import asyncio
import json
import csv
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

import discord
from discord.ext import commands
import aiohttp
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class DiscordMessage:
    """Структура для хранения сообщения Discord"""
    content: str
    author: str
    channel: str
    timestamp: datetime
    message_id: int

@dataclass
class ActivitySummary:
    """Структура для хранения результатов анализа"""
    project_name: str
    total_messages: int
    active_channels: List[str]
    summary: str
    actionable: bool
    key_events: List[str]
    confidence: float
    timestamp: datetime

class DiscordActivityScanner:
    """Сканер активности Discord серверов"""
    
    def __init__(self):
        self.bot_token = os.getenv('DISCORD_BOT_TOKEN')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Каналы для мониторинга (ключевые слова)
        self.target_channels = [
            'announcements', 'general', 'chat', 'community', 
            'info', 'launch', 'news', 'updates', 'alpha', 'beta',
            'testnet', 'mainnet', 'mint', 'airdrop', 'whitelist'
        ]
        
        # Ключевые слова для определения actionable событий
        self.actionable_keywords = [
            'early role', 'og role', 'whitelist', 'mint', 'airdrop',
            'testnet', 'mainnet', 'launch', 'presale', 'fairlaunch',
            'alpha access', 'beta access', 'early access', 'vip',
            'founder', 'partner', 'collaborator', 'ambassador'
        ]
        
        # Инициализация Discord бота
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        
    async def connect_to_discord_server(self, invite_link: str) -> Optional[discord.Guild]:
        """
        Подключение к Discord серверу через бот-токен
        
        Args:
            invite_link: Ссылка-приглашение на сервер
            
        Returns:
            discord.Guild или None в случае ошибки
        """
        try:
            if not self.bot_token:
                logger.error("DISCORD_BOT_TOKEN не настроен")
                return None
            
            # Извлекаем код приглашения из ссылки
            invite_code = invite_link.split('/')[-1]
            
            # Подключаемся к серверу
            invite = await self.bot.fetch_invite(invite_code)
            guild = invite.guild
            
            logger.info(f"Успешно подключились к серверу: {guild.name}")
            return guild
            
        except discord.NotFound:
            logger.error(f"Сервер не найден: {invite_link}")
            return None
        except discord.Forbidden:
            logger.error(f"Нет доступа к серверу: {invite_link}")
            return None
        except Exception as e:
            logger.error(f"Ошибка подключения к Discord серверу: {e}")
            return None
    
    def is_target_channel(self, channel_name: str) -> bool:
        """
        Проверка, является ли канал целевым для мониторинга
        
        Args:
            channel_name: Название канала
            
        Returns:
            True если канал подходит для мониторинга
        """
        channel_lower = channel_name.lower()
        
        # Проверяем точное совпадение
        if channel_lower in self.target_channels:
            return True
        
        # Проверяем частичное совпадение
        for target in self.target_channels:
            if target in channel_lower or channel_lower in target:
                return True
        
        return False
    
    async def get_activity_messages(self, guild: discord.Guild, limit: int = 200) -> List[DiscordMessage]:
        """
        Извлечение последних сообщений из целевых каналов
        
        Args:
            guild: Discord сервер
            limit: Максимальное количество сообщений на канал
            
        Returns:
            Список сообщений DiscordMessage
        """
        messages = []
        
        try:
            # Получаем текстовые каналы
            text_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]
            
            for channel in text_channels:
                if not self.is_target_channel(channel.name):
                    continue
                
                logger.info(f"Сканируем канал: {channel.name}")
                
                try:
                    # Получаем последние сообщения
                    async for message in channel.history(limit=limit):
                        # Фильтруем спам и стикеры
                        if self.is_valid_message(message):
                            discord_msg = DiscordMessage(
                                content=message.content,
                                author=str(message.author),
                                channel=channel.name,
                                timestamp=message.created_at,
                                message_id=message.id
                            )
                            messages.append(discord_msg)
                            
                except discord.Forbidden:
                    logger.warning(f"Нет доступа к каналу: {channel.name}")
                except Exception as e:
                    logger.error(f"Ошибка получения сообщений из канала {channel.name}: {e}")
            
            logger.info(f"Получено {len(messages)} сообщений из {guild.name}")
            return messages
            
        except Exception as e:
            logger.error(f"Ошибка получения сообщений: {e}")
            return []
    
    def is_valid_message(self, message: discord.Message) -> bool:
        """
        Проверка валидности сообщения (фильтрация спама)
        
        Args:
            message: Discord сообщение
            
        Returns:
            True если сообщение валидно
        """
        # Игнорируем стикеры и эмодзи
        if not message.content or len(message.content.strip()) < 3:
            return False
        
        # Игнорируем сообщения ботов (кроме важных)
        if message.author.bot and not self.is_important_bot(message.author.name):
            return False
        
        # Игнорируем ссылки без контекста
        if message.content.startswith('http') and len(message.content.split()) < 3:
            return False
        
        return True
    
    def is_important_bot(self, bot_name: str) -> bool:
        """
        Проверка, является ли бот важным для мониторинга
        
        Args:
            bot_name: Имя бота
            
        Returns:
            True если бот важен
        """
        important_bots = [
            'announcement', 'news', 'update', 'launch', 'mint',
            'airdrop', 'whitelist', 'role', 'admin', 'mod'
        ]
        
        bot_lower = bot_name.lower()
        return any(keyword in bot_lower for keyword in important_bots)
    
    async def summarize_activity(self, messages: List[DiscordMessage], project_name: str) -> ActivitySummary:
        """
        Анализ активности через AI
        
        Args:
            messages: Список сообщений
            project_name: Название проекта
            
        Returns:
            Результат анализа ActivitySummary
        """
        try:
            if not messages:
                return ActivitySummary(
                    project_name=project_name,
                    total_messages=0,
                    active_channels=[],
                    summary="Нет сообщений для анализа",
                    actionable=False,
                    key_events=[],
                    confidence=0.0,
                    timestamp=datetime.now()
                )
            
            # Подготавливаем данные для анализа
            messages_text = self.prepare_messages_for_analysis(messages)
            
            # Анализируем через AI
            if self.openai_api_key:
                summary_data = await self.analyze_with_ai(messages_text, project_name)
            else:
                summary_data = self.analyze_without_ai(messages_text, project_name)
            
            # Определяем actionable события
            actionable = self.detect_actionable_events(messages_text)
            key_events = self.extract_key_events(messages_text)
            
            return ActivitySummary(
                project_name=project_name,
                total_messages=len(messages),
                active_channels=list(set(msg.channel for msg in messages)),
                summary=summary_data['summary'],
                actionable=actionable,
                key_events=key_events,
                confidence=summary_data['confidence'],
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Ошибка анализа активности: {e}")
            return ActivitySummary(
                project_name=project_name,
                total_messages=len(messages),
                active_channels=[],
                summary=f"Ошибка анализа: {str(e)}",
                actionable=False,
                key_events=[],
                confidence=0.0,
                timestamp=datetime.now()
            )
    
    def prepare_messages_for_analysis(self, messages: List[DiscordMessage]) -> str:
        """
        Подготовка сообщений для AI анализа
        
        Args:
            messages: Список сообщений
            
        Returns:
            Текст для анализа
        """
        # Группируем по каналам и сортируем по времени
        messages_by_channel = {}
        for msg in messages:
            if msg.channel not in messages_by_channel:
                messages_by_channel[msg.channel] = []
            messages_by_channel[msg.channel].append(msg)
        
        # Сортируем сообщения по времени
        for channel in messages_by_channel:
            messages_by_channel[channel].sort(key=lambda x: x.timestamp)
        
        # Формируем текст для анализа
        analysis_text = ""
        for channel, msgs in messages_by_channel.items():
            analysis_text += f"\n=== КАНАЛ: {channel} ===\n"
            for msg in msgs[-50:]:  # Последние 50 сообщений из каждого канала
                analysis_text += f"[{msg.timestamp.strftime('%Y-%m-%d %H:%M')}] {msg.author}: {msg.content}\n"
        
        return analysis_text
    
    async def analyze_with_ai(self, messages_text: str, project_name: str) -> Dict[str, Any]:
        """
        Анализ через OpenAI GPT
        
        Args:
            messages_text: Текст сообщений
            project_name: Название проекта
            
        Returns:
            Результат анализа
        """
        try:
            import openai
            
            prompt = f"""
            Проанализируй активность Discord сервера проекта {project_name}:
            
            {messages_text[:4000]}  # Ограничиваем размер
            
            Оцени:
            1. Общий уровень активности
            2. Тип проекта (DeFi, NFT, GameFi, etc.)
            3. Стадия развития (идея, разработка, тестнет, запуск)
            4. Наличие важных событий (mint, airdrop, whitelist)
            5. Уровень энтузиазма сообщества
            
            Ответь в формате JSON:
            {{
                "summary": "краткое описание активности",
                "project_type": "тип проекта",
                "development_stage": "стадия развития",
                "community_enthusiasm": "высокий/средний/низкий",
                "confidence": 0.0-1.0
            }}
            """
            
            response = await asyncio.to_thread(
                openai.ChatCompletion.create,
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты эксперт по анализу криптопроектов и Discord сообществ."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            result = response.choices[0].message.content
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {
                    "summary": result,
                    "confidence": 0.7
                }
                
        except Exception as e:
            logger.error(f"Ошибка AI анализа: {e}")
            return {
                "summary": "AI анализ недоступен",
                "confidence": 0.0
            }
    
    def analyze_without_ai(self, messages_text: str, project_name: str) -> Dict[str, Any]:
        """
        Простой анализ без AI
        
        Args:
            messages_text: Текст сообщений
            project_name: Название проекта
            
        Returns:
            Результат анализа
        """
        # Простая эвристика
        lines = messages_text.split('\n')
        message_count = len([line for line in lines if ':' in line])
        
        # Определяем тип проекта по ключевым словам
        project_type = "Unknown"
        if any(word in messages_text.lower() for word in ['defi', 'swap', 'yield', 'farm']):
            project_type = "DeFi"
        elif any(word in messages_text.lower() for word in ['nft', 'mint', 'collection']):
            project_type = "NFT"
        elif any(word in messages_text.lower() for word in ['game', 'play', 'gaming']):
            project_type = "GameFi"
        
        # Определяем стадию развития
        development_stage = "Development"
        if any(word in messages_text.lower() for word in ['testnet', 'beta']):
            development_stage = "Testnet"
        elif any(word in messages_text.lower() for word in ['mainnet', 'launch']):
            development_stage = "Launch"
        
        return {
            "summary": f"Найдено {message_count} сообщений. Тип: {project_type}, Стадия: {development_stage}",
            "project_type": project_type,
            "development_stage": development_stage,
            "confidence": 0.5
        }
    
    def detect_actionable_events(self, messages_text: str) -> bool:
        """
        Определение actionable событий
        
        Args:
            messages_text: Текст сообщений
            
        Returns:
            True если есть actionable события
        """
        text_lower = messages_text.lower()
        return any(keyword in text_lower for keyword in self.actionable_keywords)
    
    def extract_key_events(self, messages_text: str) -> List[str]:
        """
        Извлечение ключевых событий
        
        Args:
            messages_text: Текст сообщений
            
        Returns:
            Список ключевых событий
        """
        events = []
        text_lower = messages_text.lower()
        
        for keyword in self.actionable_keywords:
            if keyword in text_lower:
                events.append(keyword)
        
        return list(set(events))  # Убираем дубликаты
    
    async def output_summary(self, summary: ActivitySummary) -> None:
        """
        Отправка результатов анализа
        
        Args:
            summary: Результат анализа
        """
        try:
            # Формируем сообщение
            message = self.format_summary_message(summary)
            
            # Отправляем в Telegram
            if self.telegram_bot_token and self.telegram_chat_id:
                await self.send_telegram_message(message)
            
            # Сохраняем в базу данных
            self.save_to_database(summary)
            
            # Сохраняем в CSV
            self.save_to_csv(summary)
            
            logger.info(f"Результаты анализа отправлены для проекта: {summary.project_name}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки результатов: {e}")
    
    def format_summary_message(self, summary: ActivitySummary) -> str:
        """
        Форматирование сообщения для Telegram
        
        Args:
            summary: Результат анализа
            
        Returns:
            Отформатированное сообщение
        """
        emoji = "✅" if summary.actionable else "📊"
        
        message = f"{emoji} <b>Discord Activity Report</b>\n\n"
        message += f"🧩 <b>Project:</b> {summary.project_name}\n"
        message += f"📝 <b>Messages:</b> {summary.total_messages}\n"
        message += f"📢 <b>Channels:</b> {', '.join(summary.active_channels[:5])}\n\n"
        message += f"📋 <b>Summary:</b>\n{summary.summary}\n\n"
        
        if summary.key_events:
            message += f"🎯 <b>Key Events:</b> {', '.join(summary.key_events)}\n\n"
        
        message += f"⚡ <b>Actionable:</b> {'YES' if summary.actionable else 'NO'}\n"
        message += f"🎯 <b>Confidence:</b> {summary.confidence:.1%}\n"
        message += f"🕐 <b>Analyzed:</b> {summary.timestamp.strftime('%Y-%m-%d %H:%M')}"
        
        return message
    
    async def send_telegram_message(self, message: str) -> None:
        """
        Отправка сообщения в Telegram
        
        Args:
            message: Текст сообщения
        """
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка отправки в Telegram: {response.status}")
                        
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
    
    def save_to_database(self, summary: ActivitySummary) -> None:
        """
        Сохранение в SQLite базу данных
        
        Args:
            summary: Результат анализа
        """
        try:
            conn = sqlite3.connect('discord_activity.sqlite')
            cursor = conn.cursor()
            
            # Создаем таблицу если не существует
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS discord_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT,
                    total_messages INTEGER,
                    active_channels TEXT,
                    summary TEXT,
                    actionable BOOLEAN,
                    key_events TEXT,
                    confidence REAL,
                    timestamp DATETIME
                )
            ''')
            
            # Вставляем данные
            cursor.execute('''
                INSERT INTO discord_activity 
                (project_name, total_messages, active_channels, summary, actionable, key_events, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                summary.project_name,
                summary.total_messages,
                json.dumps(summary.active_channels),
                summary.summary,
                summary.actionable,
                json.dumps(summary.key_events),
                summary.confidence,
                summary.timestamp.isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}")
    
    def save_to_csv(self, summary: ActivitySummary) -> None:
        """
        Сохранение в CSV файл
        
        Args:
            summary: Результат анализа
        """
        try:
            file_exists = os.path.exists('activity_log.csv')
            
            with open('activity_log.csv', 'a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                
                if not file_exists:
                    # Записываем заголовки
                    writer.writerow([
                        'timestamp', 'project_name', 'total_messages', 'active_channels',
                        'summary', 'actionable', 'key_events', 'confidence'
                    ])
                
                # Записываем данные
                writer.writerow([
                    summary.timestamp.isoformat(),
                    summary.project_name,
                    summary.total_messages,
                    ';'.join(summary.active_channels),
                    summary.summary.replace('\n', ' '),
                    summary.actionable,
                    ';'.join(summary.key_events),
                    summary.confidence
                ])
                
        except Exception as e:
            logger.error(f"Ошибка сохранения в CSV: {e}")

async def scan_discord(invite_link: str, project_name: str) -> Optional[ActivitySummary]:
    """
    Основная функция для сканирования Discord активности
    
    Args:
        invite_link: Ссылка-приглашение на Discord сервер
        project_name: Название проекта
        
    Returns:
        Результат анализа или None в случае ошибки
    """
    scanner = DiscordActivityScanner()
    
    try:
        # Подключаемся к серверу
        guild = await scanner.connect_to_discord_server(invite_link)
        if not guild:
            return None
        
        # Получаем сообщения
        messages = await scanner.get_activity_messages(guild)
        if not messages:
            logger.warning(f"Нет сообщений для анализа в проекте {project_name}")
            return None
        
        # Анализируем активность
        summary = await scanner.summarize_activity(messages, project_name)
        
        # Отправляем результаты
        await scanner.output_summary(summary)
        
        return summary
        
    except Exception as e:
        logger.error(f"Ошибка сканирования Discord для {project_name}: {e}")
        return None

# Пример использования (для будущего):
if __name__ == "__main__":
    # Этот код будет выполняться только при прямом запуске модуля
    print("Discord Activity Scanner готов к использованию!")
    print("Использование:")
    print("from discord_activity import scan_discord")
    print("await scan_discord('https://discord.gg/agoraxyz', 'Agora')") 