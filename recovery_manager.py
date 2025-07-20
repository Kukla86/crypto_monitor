#!/usr/bin/env python3
"""
Система автоматического восстановления
Обрабатывает сбои и автоматически восстанавливает работу системы
"""

import asyncio
import logging
import time
import traceback
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import threading
from functools import wraps

logger = logging.getLogger(__name__)

class RecoveryStrategy(Enum):
    """Стратегии восстановления"""
    RETRY = "retry"
    RESTART = "restart"
    FALLBACK = "fallback"
    IGNORE = "ignore"
    ESCALATE = "escalate"

@dataclass
class RecoveryConfig:
    """Конфигурация восстановления"""
    max_retries: int = 3
    retry_delay: float = 1.0
    backoff_factor: float = 2.0
    timeout: float = 30.0
    strategy: RecoveryStrategy = RecoveryStrategy.RETRY
    fallback_function: Optional[Callable] = None
    alert_on_failure: bool = True

@dataclass
class FailureRecord:
    """Запись о сбое"""
    component: str
    error: str
    timestamp: datetime
    retry_count: int = 0
    resolved: bool = False
    resolution_time: Optional[datetime] = None

class RecoveryManager:
    """Менеджер восстановления"""
    
    def __init__(self):
        """Инициализация менеджера"""
        self.failure_history = []
        self.recovery_configs = {}
        self.active_recoveries = {}
        self.health_checks = {}
        self.recovery_hooks = []
        
        # Запускаем мониторинг здоровья
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._health_monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Менеджер восстановления инициализирован")
    
    def register_component(self, component_name: str, config: RecoveryConfig):
        """Регистрация компонента для мониторинга"""
        self.recovery_configs[component_name] = config
        logger.info(f"Зарегистрирован компонент: {component_name}")
    
    def add_health_check(self, component_name: str, health_check_func: Callable):
        """Добавление проверки здоровья компонента"""
        self.health_checks[component_name] = health_check_func
        logger.info(f"Добавлена проверка здоровья для: {component_name}")
    
    def add_recovery_hook(self, hook_func: Callable):
        """Добавление хука восстановления"""
        self.recovery_hooks.append(hook_func)
    
    async def execute_with_recovery(self, component_name: str, func: Callable, *args, **kwargs):
        """Выполнение функции с автоматическим восстановлением"""
        config = self.recovery_configs.get(component_name, RecoveryConfig())
        
        for attempt in range(config.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=config.timeout)
                else:
                    result = func(*args, **kwargs)
                
                # Успешное выполнение
                if attempt > 0:
                    await self._record_resolution(component_name)
                
                return result
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Сбой в {component_name} (попытка {attempt + 1}/{config.max_retries + 1}): {error_msg}")
                
                # Записываем сбой
                await self._record_failure(component_name, error_msg, attempt)
                
                if attempt == config.max_retries:
                    # Исчерпаны все попытки
                    await self._handle_final_failure(component_name, config, e)
                    raise
                else:
                    # Ждем перед следующей попыткой
                    delay = config.retry_delay * (config.backoff_factor ** attempt)
                    await asyncio.sleep(delay)
    
    async def _record_failure(self, component_name: str, error: str, attempt: int):
        """Запись сбоя"""
        failure = FailureRecord(
            component=component_name,
            error=error,
            timestamp=datetime.now(),
            retry_count=attempt
        )
        
        self.failure_history.append(failure)
        
        # Ограничиваем историю
        if len(self.failure_history) > 1000:
            self.failure_history = self.failure_history[-1000:]
        
        # Вызываем хуки
        for hook in self.recovery_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(failure)
                else:
                    hook(failure)
            except Exception as e:
                logger.error(f"Ошибка в хуке восстановления: {e}")
    
    async def _record_resolution(self, component_name: str):
        """Запись разрешения проблемы"""
        # Находим последний неразрешенный сбой для этого компонента
        for failure in reversed(self.failure_history):
            if failure.component == component_name and not failure.resolved:
                failure.resolved = True
                failure.resolution_time = datetime.now()
                logger.info(f"Проблема в {component_name} разрешена")
                break
    
    async def _handle_final_failure(self, component_name: str, config: RecoveryConfig, error: Exception):
        """Обработка финального сбоя"""
        logger.error(f"Критический сбой в {component_name}: {error}")
        
        if config.strategy == RecoveryStrategy.FALLBACK and config.fallback_function:
            logger.info(f"Запуск fallback функции для {component_name}")
            try:
                if asyncio.iscoroutinefunction(config.fallback_function):
                    await config.fallback_function()
                else:
                    config.fallback_function()
            except Exception as e:
                logger.error(f"Ошибка в fallback функции: {e}")
        
        elif config.strategy == RecoveryStrategy.RESTART:
            logger.info(f"Перезапуск компонента {component_name}")
            await self._restart_component(component_name)
        
        elif config.strategy == RecoveryStrategy.ESCALATE:
            logger.critical(f"Эскалация сбоя в {component_name}")
            await self._escalate_failure(component_name, error)
        
        if config.alert_on_failure:
            await self._send_failure_alert(component_name, error)
    
    async def _restart_component(self, component_name: str):
        """Перезапуск компонента"""
        try:
            # Здесь будет логика перезапуска компонентов
            logger.info(f"Компонент {component_name} перезапущен")
        except Exception as e:
            logger.error(f"Ошибка перезапуска {component_name}: {e}")
    
    async def _escalate_failure(self, component_name: str, error: Exception):
        """Эскалация сбоя"""
        try:
            from alert_manager import AlertLevel, send_alert
            
            await send_alert(
                level=AlertLevel.CRITICAL,
                title="🚨 Критический сбой системы",
                message=f"Компонент {component_name} не удалось восстановить: {str(error)}",
                source="recovery_manager",
                template="system_error"
            )
        except Exception as e:
            logger.error(f"Ошибка эскалации: {e}")
    
    async def _send_failure_alert(self, component_name: str, error: Exception):
        """Отправка алерта о сбое"""
        try:
            from alert_manager import AlertLevel, send_alert
            
            await send_alert(
                level=AlertLevel.ERROR,
                title="⚠️ Сбой компонента",
                message=f"Компонент {component_name}: {str(error)}",
                source="recovery_manager",
                template="system_error"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")
    
    def _health_monitor_loop(self):
        """Цикл мониторинга здоровья"""
        while self.monitoring_active:
            try:
                for component_name, health_check in self.health_checks.items():
                    try:
                        if asyncio.iscoroutinefunction(health_check):
                            # Для асинхронных функций создаем новый event loop
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                result = loop.run_until_complete(health_check())
                                if not result:
                                    logger.warning(f"Проверка здоровья {component_name} не прошла")
                            finally:
                                loop.close()
                        else:
                            result = health_check()
                            if not result:
                                logger.warning(f"Проверка здоровья {component_name} не прошла")
                    except Exception as e:
                        logger.error(f"Ошибка проверки здоровья {component_name}: {e}")
                
                time.sleep(30)  # Проверяем каждые 30 секунд
                
            except Exception as e:
                logger.error(f"Ошибка мониторинга здоровья: {e}")
                time.sleep(60)
    
    def get_failure_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Получение статистики сбоев"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_failures = [f for f in self.failure_history if f.timestamp > cutoff_time]
        
        stats = {
            'total_failures': len(recent_failures),
            'resolved_failures': len([f for f in recent_failures if f.resolved]),
            'by_component': {},
            'avg_resolution_time': 0
        }
        
        # Группируем по компонентам
        for failure in recent_failures:
            component = failure.component
            if component not in stats['by_component']:
                stats['by_component'][component] = {
                    'total': 0,
                    'resolved': 0,
                    'avg_retries': 0
                }
            
            stats['by_component'][component]['total'] += 1
            if failure.resolved:
                stats['by_component'][component]['resolved'] += 1
        
        # Вычисляем средние значения
        for component_stats in stats['by_component'].values():
            if component_stats['total'] > 0:
                component_stats['avg_retries'] = sum(
                    f.retry_count for f in recent_failures 
                    if f.component in stats['by_component']
                ) / component_stats['total']
        
        # Среднее время разрешения
        resolved_failures = [f for f in recent_failures if f.resolved and f.resolution_time]
        if resolved_failures:
            total_resolution_time = sum(
                (f.resolution_time - f.timestamp).total_seconds() 
                for f in resolved_failures
            )
            stats['avg_resolution_time'] = total_resolution_time / len(resolved_failures)
        
        return stats
    
    def get_component_health(self, component_name: str) -> Dict[str, Any]:
        """Получение состояния здоровья компонента"""
        recent_failures = [f for f in self.failure_history if f.component == component_name]
        recent_failures = [f for f in recent_failures if f.timestamp > datetime.now() - timedelta(hours=1)]
        
        return {
            'component': component_name,
            'is_healthy': len(recent_failures) == 0,
            'recent_failures': len(recent_failures),
            'last_failure': recent_failures[-1].timestamp if recent_failures else None,
            'config': asdict(self.recovery_configs.get(component_name, RecoveryConfig()))
        }
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.monitoring_active = False
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        logger.info("Мониторинг здоровья остановлен")

# Глобальный экземпляр менеджера восстановления
recovery_manager = None

def get_recovery_manager() -> RecoveryManager:
    """Получение глобального менеджера восстановления"""
    global recovery_manager
    if recovery_manager is None:
        recovery_manager = RecoveryManager()
    return recovery_manager

def recovery_decorator(component_name: str, config: Optional[RecoveryConfig] = None):
    """Декоратор для автоматического восстановления"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            manager = get_recovery_manager()
            
            # Регистрируем компонент если нужно
            if component_name not in manager.recovery_configs:
                manager.register_component(component_name, config or RecoveryConfig())
            
            return await manager.execute_with_recovery(component_name, func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            manager = get_recovery_manager()
            
            # Регистрируем компонент если нужно
            if component_name not in manager.recovery_configs:
                manager.register_component(component_name, config or RecoveryConfig())
            
            # Для синхронных функций создаем асинхронную обертку
            async def async_func():
                return func(*args, **kwargs)
            
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                manager.execute_with_recovery(component_name, async_func)
            )
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator 