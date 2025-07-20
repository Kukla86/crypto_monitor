#!/usr/bin/env python3
"""
Расширенный менеджер алертов
Поддерживает множественные каналы уведомлений, шаблоны и приоритизацию
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import hashlib
from pathlib import Path

logger = logging.getLogger(__name__)

class AlertLevel(Enum):
    """Уровни важности алертов"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AlertChannel(Enum):
    """Каналы отправки алертов"""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    EMAIL = "email"
    WEBHOOK = "webhook"
    CONSOLE = "console"
    LOG = "log"

@dataclass
class AlertTemplate:
    """Шаблон алерта"""
    name: str
    title: str
    message: str
    emoji: str = ""
    color: str = "#000000"
    priority: AlertLevel = AlertLevel.INFO

@dataclass
class Alert:
    """Алерт"""
    id: str
    level: AlertLevel
    title: str
    message: str
    token_symbol: Optional[str] = None
    source: Optional[str] = None
    timestamp: datetime = None
    data: Optional[Dict[str, Any]] = None
    channels: List[AlertChannel] = None
    template: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.channels is None:
            self.channels = [AlertChannel.TELEGRAM, AlertChannel.CONSOLE]

class AlertManager:
    """Менеджер алертов"""
    
    def __init__(self):
        """Инициализация менеджера"""
        self.alerts_history = []
        self.sent_alerts = set()
        self.alert_templates = self._load_templates()
        self.channel_handlers = self._setup_channel_handlers()
        self.rate_limits = {}
        self.alert_filters = []
        
        logger.info("Менеджер алертов инициализирован")
    
    def _load_templates(self) -> Dict[str, AlertTemplate]:
        """Загрузка шаблонов алертов"""
        templates = {
            'price_spike': AlertTemplate(
                name='price_spike',
                title='🚀 Резкий рост цены',
                message='Токен {token} показал рост на {change}% за {period}',
                emoji='🚀',
                color='#00ff00',
                priority=AlertLevel.WARNING
            ),
            'volume_surge': AlertTemplate(
                name='volume_surge',
                title='📈 Всплеск объема',
                message='Объем торгов {token} вырос на {change}%',
                emoji='📈',
                color='#ffaa00',
                priority=AlertLevel.WARNING
            ),
            'whale_movement': AlertTemplate(
                name='whale_movement',
                title='🐋 Движение китов',
                message='Крупная транзакция {amount} {token} на сумму ${value}',
                emoji='🐋',
                color='#ff0000',
                priority=AlertLevel.ERROR
            ),
            'social_buzz': AlertTemplate(
                name='social_buzz',
                title='📱 Социальная активность',
                message='Повышенная активность в соцсетях для {token}',
                emoji='📱',
                color='#0088ff',
                priority=AlertLevel.INFO
            ),
            'system_error': AlertTemplate(
                name='system_error',
                title='❌ Ошибка системы',
                message='Ошибка в {component}: {error}',
                emoji='❌',
                color='#ff0000',
                priority=AlertLevel.CRITICAL
            ),
            'performance_warning': AlertTemplate(
                name='performance_warning',
                title='⚡ Предупреждение производительности',
                message='{metric}: {value} (порог: {threshold})',
                emoji='⚡',
                color='#ff8800',
                priority=AlertLevel.WARNING
            )
        }
        
        return templates
    
    def _setup_channel_handlers(self) -> Dict[AlertChannel, callable]:
        """Настройка обработчиков каналов"""
        return {
            AlertChannel.TELEGRAM: self._send_telegram_alert,
            AlertChannel.DISCORD: self._send_discord_alert,
            AlertChannel.EMAIL: self._send_email_alert,
            AlertChannel.WEBHOOK: self._send_webhook_alert,
            AlertChannel.CONSOLE: self._send_console_alert,
            AlertChannel.LOG: self._send_log_alert
        }
    
    def create_alert(self, level: AlertLevel, title: str, message: str, 
                    token_symbol: Optional[str] = None, source: Optional[str] = None,
                    data: Optional[Dict[str, Any]] = None, 
                    channels: Optional[List[AlertChannel]] = None,
                    template: Optional[str] = None) -> Alert:
        """Создание нового алерта"""
        
        # Применяем шаблон если указан
        if template and template in self.alert_templates:
            template_obj = self.alert_templates[template]
            title = template_obj.title
            message = template_obj.message.format(**data) if data else template_obj.message
            level = template_obj.priority
        
        # Генерируем уникальный ID
        alert_id = self._generate_alert_id(title, message, token_symbol)
        
        # Проверяем, не был ли уже отправлен этот алерт
        if alert_id in self.sent_alerts:
            logger.debug(f"Алерт уже был отправлен: {alert_id}")
            return None
        
        alert = Alert(
            id=alert_id,
            level=level,
            title=title,
            message=message,
            token_symbol=token_symbol,
            source=source,
            data=data,
            channels=channels or [AlertChannel.TELEGRAM, AlertChannel.CONSOLE],
            template=template
        )
        
        return alert
    
    def _generate_alert_id(self, title: str, message: str, token_symbol: Optional[str]) -> str:
        """Генерация уникального ID алерта"""
        content = f"{title}:{message}:{token_symbol or ''}"
        return hashlib.md5(content.encode()).hexdigest()[:8]
    
    async def send_alert(self, alert: Alert) -> bool:
        """Отправка алерта"""
        if not alert:
            return False
        
        try:
            # Проверяем rate limits
            if not self._check_rate_limit(alert):
                logger.warning(f"Rate limit для алерта {alert.id}")
                return False
            
            # Применяем фильтры
            if not self._apply_filters(alert):
                logger.debug(f"Алерт {alert.id} отфильтрован")
                return False
            
            # Отправляем по всем каналам
            success = True
            for channel in alert.channels:
                if channel in self.channel_handlers:
                    try:
                        await self.channel_handlers[channel](alert)
                    except Exception as e:
                        logger.error(f"Ошибка отправки в {channel.value}: {e}")
                        success = False
            
            if success:
                # Помечаем как отправленный
                self.sent_alerts.add(alert.id)
                self.alerts_history.append(alert)
                
                # Ограничиваем историю
                if len(self.alerts_history) > 1000:
                    self.alerts_history = self.alerts_history[-1000:]
                
                logger.info(f"Алерт отправлен: {alert.title}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")
            return False
    
    def _check_rate_limit(self, alert: Alert) -> bool:
        """Проверка rate limit"""
        key = f"{alert.level.value}:{alert.token_symbol or 'global'}"
        current_time = time.time()
        
        if key not in self.rate_limits:
            self.rate_limits[key] = []
        
        # Удаляем старые записи (старше 1 часа)
        self.rate_limits[key] = [t for t in self.rate_limits[key] if current_time - t < 3600]
        
        # Проверяем лимиты
        limits = {
            AlertLevel.INFO: 60,      # 60 алертов в час
            AlertLevel.WARNING: 30,   # 30 алертов в час
            AlertLevel.ERROR: 10,     # 10 алертов в час
            AlertLevel.CRITICAL: 5    # 5 алертов в час
        }
        
        if len(self.rate_limits[key]) >= limits.get(alert.level, 60):
            return False
        
        self.rate_limits[key].append(current_time)
        return True
    
    def _apply_filters(self, alert: Alert) -> bool:
        """Применение фильтров"""
        for filter_func in self.alert_filters:
            if not filter_func(alert):
                return False
        return True
    
    def add_filter(self, filter_func: callable):
        """Добавление фильтра алертов"""
        self.alert_filters.append(filter_func)
    
    async def _send_telegram_alert(self, alert: Alert):
        """Отправка в Telegram"""
        try:
            from telegram_bot import CryptoMonitorBot
            
            message = self._format_alert_message(alert, 'telegram')
            await CryptoMonitorBot.send_message(message)
            
        except ImportError:
            logger.warning("Telegram бот недоступен")
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
    
    async def _send_discord_alert(self, alert: Alert):
        """Отправка в Discord"""
        try:
            # Здесь будет интеграция с Discord
            logger.info(f"Discord алерт: {alert.title}")
        except Exception as e:
            logger.error(f"Ошибка отправки в Discord: {e}")
    
    async def _send_email_alert(self, alert: Alert):
        """Отправка по email"""
        try:
            # Здесь будет интеграция с email
            logger.info(f"Email алерт: {alert.title}")
        except Exception as e:
            logger.error(f"Ошибка отправки email: {e}")
    
    async def _send_webhook_alert(self, alert: Alert):
        """Отправка webhook"""
        try:
            # Здесь будет интеграция с webhook
            logger.info(f"Webhook алерт: {alert.title}")
        except Exception as e:
            logger.error(f"Ошибка отправки webhook: {e}")
    
    async def _send_console_alert(self, alert: Alert):
        """Отправка в консоль"""
        emoji = self.alert_templates.get(alert.template, AlertTemplate("", "", "")).emoji if alert.template else ""
        print(f"{emoji} [{alert.level.value.upper()}] {alert.title}: {alert.message}")
    
    def _send_log_alert(self, alert: Alert):
        """Отправка в лог"""
        log_level = getattr(logging, alert.level.value.upper(), logging.INFO)
        logger.log(log_level, f"{alert.title}: {alert.message}")
    
    def _format_alert_message(self, alert: Alert, channel: str) -> str:
        """Форматирование сообщения алерта"""
        template = self.alert_templates.get(alert.template)
        emoji = template.emoji if template else ""
        
        if channel == 'telegram':
            return f"{emoji} <b>{alert.title}</b>\n{alert.message}"
        else:
            return f"{emoji} {alert.title}\n{alert.message}"
    
    def get_alerts_history(self, hours: int = 24, level: Optional[AlertLevel] = None) -> List[Alert]:
        """Получение истории алертов"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        alerts = [a for a in self.alerts_history if a.timestamp > cutoff_time]
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        return alerts
    
    def get_alert_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Получение статистики алертов"""
        alerts = self.get_alerts_history(hours)
        
        stats = {
            'total_alerts': len(alerts),
            'by_level': {},
            'by_token': {},
            'by_source': {}
        }
        
        for alert in alerts:
            # По уровню
            level = alert.level.value
            stats['by_level'][level] = stats['by_level'].get(level, 0) + 1
            
            # По токену
            if alert.token_symbol:
                stats['by_token'][alert.token_symbol] = stats['by_token'].get(alert.token_symbol, 0) + 1
            
            # По источнику
            if alert.source:
                stats['by_source'][alert.source] = stats['by_source'].get(alert.source, 0) + 1
        
        return stats
    
    def clear_history(self):
        """Очистка истории алертов"""
        self.alerts_history.clear()
        self.sent_alerts.clear()
        logger.info("История алертов очищена")

# Глобальный экземпляр менеджера алертов
alert_manager = None

def get_alert_manager() -> AlertManager:
    """Получение глобального менеджера алертов"""
    global alert_manager
    if alert_manager is None:
        alert_manager = AlertManager()
    return alert_manager

async def send_alert(level: AlertLevel, title: str, message: str, 
                    token_symbol: Optional[str] = None, source: Optional[str] = None,
                    data: Optional[Dict[str, Any]] = None, 
                    channels: Optional[List[AlertChannel]] = None,
                    template: Optional[str] = None) -> bool:
    """Удобная функция для отправки алертов"""
    manager = get_alert_manager()
    alert = manager.create_alert(level, title, message, token_symbol, source, data, channels, template)
    return await manager.send_alert(alert) 