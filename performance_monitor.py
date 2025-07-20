#!/usr/bin/env python3
"""
Модуль мониторинга производительности системы
Отслеживает использование ресурсов, время выполнения операций и оптимизирует работу
"""

import time
import psutil
import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading
import gc

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """Метрики производительности"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_sent_mb: float
    network_recv_mb: float
    active_connections: int
    cache_hit_rate: float
    avg_response_time: float
    requests_per_second: float

@dataclass
class OperationMetrics:
    """Метрики операций"""
    operation_name: str
    execution_time: float
    success: bool
    timestamp: datetime = None
    error_message: Optional[str] = None
    memory_used: Optional[float] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class PerformanceMonitor:
    """Монитор производительности системы"""
    
    def __init__(self, history_size: int = 1000):
        """Инициализация монитора"""
        self.history_size = history_size
        self.metrics_history = deque(maxlen=history_size)
        self.operation_history = deque(maxlen=history_size)
        self.start_time = time.time()
        self.request_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Базовые метрики системы
        self.process = psutil.Process()
        self.last_io_counters = psutil.disk_io_counters()
        self.last_net_counters = psutil.net_io_counters()
        self.last_io_time = time.time()
        self.last_net_time = time.time()
        
        # Запускаем мониторинг
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Монитор производительности запущен")
    
    def _monitor_loop(self):
        """Основной цикл мониторинга"""
        while self.monitoring_active:
            try:
                metrics = self._collect_metrics()
                self.metrics_history.append(metrics)
                
                # Проверяем критические пороги
                self._check_thresholds(metrics)
                
                time.sleep(5)  # Сбор метрик каждые 5 секунд
                
            except Exception as e:
                logger.error(f"Ошибка сбора метрик: {e}")
                time.sleep(10)
    
    def _collect_metrics(self) -> PerformanceMetrics:
        """Сбор метрик системы"""
        # CPU и память
        cpu_percent = self.process.cpu_percent()
        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()
        memory_used_mb = memory_info.rss / 1024 / 1024
        
        # Дисковые операции
        current_io = psutil.disk_io_counters()
        current_time = time.time()
        io_time_diff = current_time - self.last_io_time
        
        if self.last_io_counters and io_time_diff > 0:
            disk_io_read_mb = (current_io.read_bytes - self.last_io_counters.read_bytes) / 1024 / 1024 / io_time_diff
            disk_io_write_mb = (current_io.write_bytes - self.last_io_counters.write_bytes) / 1024 / 1024 / io_time_diff
        else:
            disk_io_read_mb = 0
            disk_io_write_mb = 0
        
        self.last_io_counters = current_io
        self.last_io_time = current_time
        
        # Сетевые операции
        current_net = psutil.net_io_counters()
        net_time_diff = current_time - self.last_net_time
        
        if self.last_net_counters and net_time_diff > 0:
            network_sent_mb = (current_net.bytes_sent - self.last_net_counters.bytes_sent) / 1024 / 1024 / net_time_diff
            network_recv_mb = (current_net.bytes_recv - self.last_net_counters.bytes_recv) / 1024 / 1024 / net_time_diff
        else:
            network_sent_mb = 0
            network_recv_mb = 0
        
        self.last_net_counters = current_net
        self.last_net_time = current_time
        
        # Подключения
        active_connections = len(self.process.connections())
        
        # Кэш
        total_cache_requests = self.cache_hits + self.cache_misses
        cache_hit_rate = (self.cache_hits / total_cache_requests * 100) if total_cache_requests > 0 else 0
        
        # Время выполнения и RPS
        uptime = time.time() - self.start_time
        requests_per_second = self.request_count / uptime if uptime > 0 else 0
        
        # Среднее время ответа (из последних операций)
        recent_operations = list(self.operation_history)[-100:] if self.operation_history else []
        avg_response_time = sum(op.execution_time for op in recent_operations) / len(recent_operations) if recent_operations else 0
        
        return PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            disk_io_read_mb=disk_io_read_mb,
            disk_io_write_mb=disk_io_write_mb,
            network_sent_mb=network_sent_mb,
            network_recv_mb=network_recv_mb,
            active_connections=active_connections,
            cache_hit_rate=cache_hit_rate,
            avg_response_time=avg_response_time,
            requests_per_second=requests_per_second
        )
    
    def _check_thresholds(self, metrics: PerformanceMetrics):
        """Проверка критических порогов"""
        warnings = []
        
        if metrics.cpu_percent > 80:
            warnings.append(f"Высокое использование CPU: {metrics.cpu_percent:.1f}%")
        
        if metrics.memory_percent > 85:
            warnings.append(f"Высокое использование памяти: {metrics.memory_percent:.1f}%")
        
        if metrics.memory_used_mb > 1000:  # 1GB
            warnings.append(f"Большое потребление памяти: {metrics.memory_used_mb:.1f}MB")
        
        if metrics.avg_response_time > 5.0:  # 5 секунд
            warnings.append(f"Медленные ответы: {metrics.avg_response_time:.2f}с")
        
        if warnings:
            logger.warning(f"Проблемы производительности: {'; '.join(warnings)}")
    
    def record_operation(self, operation_name: str, execution_time: float, 
                        success: bool, error_message: Optional[str] = None):
        """Запись метрик операции"""
        self.operation_history.append(OperationMetrics(
            operation_name=operation_name,
            execution_time=execution_time,
            success=success,
            error_message=error_message
        ))
        
        if success:
            self.request_count += 1
    
    def record_cache_hit(self):
        """Запись попадания в кэш"""
        self.cache_hits += 1
    
    def record_cache_miss(self):
        """Запись промаха кэша"""
        self.cache_misses += 1
    
    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """Получение текущих метрик"""
        return self.metrics_history[-1] if self.metrics_history else None
    
    def get_metrics_history(self, minutes: int = 60) -> List[PerformanceMetrics]:
        """Получение истории метрик за указанное время"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [m for m in self.metrics_history if m.timestamp > cutoff_time]
    
    def get_operation_stats(self, operation_name: Optional[str] = None) -> Dict[str, Any]:
        """Получение статистики операций"""
        operations = list(self.operation_history)
        
        if operation_name:
            operations = [op for op in operations if op.operation_name == operation_name]
        
        if not operations:
            return {}
        
        execution_times = [op.execution_time for op in operations]
        success_count = sum(1 for op in operations if op.success)
        
        return {
            'total_operations': len(operations),
            'success_rate': success_count / len(operations) * 100,
            'avg_execution_time': sum(execution_times) / len(execution_times),
            'min_execution_time': min(execution_times),
            'max_execution_time': max(execution_times),
            'recent_operations': len([op for op in operations if op.timestamp > datetime.now() - timedelta(minutes=5)])
        }
    
    def get_system_summary(self) -> Dict[str, Any]:
        """Получение сводки системы"""
        current_metrics = self.get_current_metrics()
        if not current_metrics:
            return {}
        
        return {
            'uptime_seconds': time.time() - self.start_time,
            'current_metrics': asdict(current_metrics),
            'cache_stats': {
                'hits': self.cache_hits,
                'misses': self.cache_misses,
                'hit_rate': current_metrics.cache_hit_rate
            },
            'operation_stats': self.get_operation_stats()
        }
    
    def optimize_memory(self):
        """Оптимизация памяти"""
        logger.info("Запуск оптимизации памяти...")
        
        # Принудительная сборка мусора
        collected = gc.collect()
        logger.info(f"Собрано объектов: {collected}")
        
        # Получаем текущее использование памяти
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        logger.info(f"Использование памяти после оптимизации: {memory_mb:.1f}MB")
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.monitoring_active = False
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        logger.info("Мониторинг производительности остановлен")

# Глобальный экземпляр монитора
performance_monitor = None

def get_performance_monitor() -> PerformanceMonitor:
    """Получение глобального монитора производительности"""
    global performance_monitor
    if performance_monitor is None:
        performance_monitor = PerformanceMonitor()
    return performance_monitor

def performance_decorator(operation_name: str):
    """Декоратор для отслеживания производительности функций"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            error_message = None
            
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error_message = str(e)
                raise
            finally:
                execution_time = time.time() - start_time
                monitor = get_performance_monitor()
                monitor.record_operation(operation_name, execution_time, success, error_message)
        
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            error_message = None
            
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                error_message = str(e)
                raise
            finally:
                execution_time = time.time() - start_time
                monitor = get_performance_monitor()
                monitor.record_operation(operation_name, execution_time, success, error_message)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator 