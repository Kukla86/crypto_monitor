#!/usr/bin/env python3
"""
Тесты для модуля мониторинга производительности
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from performance_monitor import (
    PerformanceMonitor, PerformanceMetrics, OperationMetrics,
    get_performance_monitor, performance_decorator
)

class TestPerformanceMonitor:
    """Тесты для PerformanceMonitor"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.monitor = PerformanceMonitor(history_size=10)
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        self.monitor.stop_monitoring()
    
    def test_initialization(self):
        """Тест инициализации монитора"""
        assert self.monitor.history_size == 10
        assert len(self.monitor.metrics_history) == 0
        assert len(self.monitor.operation_history) == 0
        assert self.monitor.request_count == 0
        assert self.monitor.cache_hits == 0
        assert self.monitor.cache_misses == 0
    
    def test_record_operation(self):
        """Тест записи операции"""
        self.monitor.record_operation("test_op", 1.5, True)
        
        assert len(self.monitor.operation_history) == 1
        assert self.monitor.request_count == 1
        
        operation = self.monitor.operation_history[0]
        assert operation.operation_name == "test_op"
        assert operation.execution_time == 1.5
        assert operation.success is True
    
    def test_record_cache_hit_miss(self):
        """Тест записи попаданий/промахов кэша"""
        self.monitor.record_cache_hit()
        self.monitor.record_cache_hit()
        self.monitor.record_cache_miss()
        
        assert self.monitor.cache_hits == 2
        assert self.monitor.cache_misses == 1
    
    @patch('psutil.Process')
    @patch('psutil.disk_io_counters')
    @patch('psutil.net_io_counters')
    def test_collect_metrics(self, mock_net_io, mock_disk_io, mock_process):
        """Тест сбора метрик"""
        # Мокаем psutil
        mock_process_instance = Mock()
        mock_process_instance.cpu_percent.return_value = 25.5
        mock_process_instance.memory_info.return_value = Mock(rss=100 * 1024 * 1024)  # 100MB
        mock_process_instance.memory_percent.return_value = 15.2
        mock_process_instance.connections.return_value = [Mock(), Mock()]  # 2 connections
        mock_process.return_value = mock_process_instance
        
        mock_disk_io.return_value = Mock(read_bytes=1000, write_bytes=500)
        mock_net_io.return_value = Mock(bytes_sent=2000, bytes_recv=3000)
        
        metrics = self.monitor._collect_metrics()
        
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.cpu_percent == 25.5
        assert metrics.memory_percent == 15.2
        assert metrics.memory_used_mb == 100.0
        assert metrics.active_connections == 2
    
    def test_get_current_metrics(self):
        """Тест получения текущих метрик"""
        # Сначала метрик нет
        assert self.monitor.get_current_metrics() is None
        
        # Добавляем метрики
        with patch.object(self.monitor, '_collect_metrics') as mock_collect:
            mock_collect.return_value = PerformanceMetrics(
                timestamp=datetime.now(),
                cpu_percent=10.0,
                memory_percent=20.0,
                memory_used_mb=50.0,
                disk_io_read_mb=1.0,
                disk_io_write_mb=0.5,
                network_sent_mb=2.0,
                network_recv_mb=3.0,
                active_connections=1,
                cache_hit_rate=75.0,
                avg_response_time=0.5,
                requests_per_second=10.0
            )
            
            self.monitor._monitor_loop()
            time.sleep(0.1)  # Даем время на выполнение
            
            current_metrics = self.monitor.get_current_metrics()
            assert current_metrics is not None
            assert current_metrics.cpu_percent == 10.0
    
    def test_get_operation_stats(self):
        """Тест получения статистики операций"""
        # Добавляем несколько операций
        self.monitor.record_operation("op1", 1.0, True)
        self.monitor.record_operation("op2", 2.0, True)
        self.monitor.record_operation("op3", 3.0, False)
        
        stats = self.monitor.get_operation_stats()
        
        assert stats['total_operations'] == 3
        assert stats['success_rate'] == pytest.approx(66.67, rel=0.01)
        assert stats['avg_execution_time'] == 2.0
        assert stats['min_execution_time'] == 1.0
        assert stats['max_execution_time'] == 3.0
    
    def test_get_operation_stats_by_name(self):
        """Тест получения статистики операций по имени"""
        self.monitor.record_operation("op1", 1.0, True)
        self.monitor.record_operation("op1", 2.0, True)
        self.monitor.record_operation("op2", 3.0, False)
        
        stats = self.monitor.get_operation_stats("op1")
        
        assert stats['total_operations'] == 2
        assert stats['success_rate'] == 100.0
        assert stats['avg_execution_time'] == 1.5
    
    def test_get_system_summary(self):
        """Тест получения сводки системы"""
        # Добавляем данные
        self.monitor.record_operation("test_op", 1.0, True)
        self.monitor.record_cache_hit()
        self.monitor.record_cache_miss()
        
        summary = self.monitor.get_system_summary()
        
        assert 'uptime_seconds' in summary
        assert 'current_metrics' in summary
        assert 'cache_stats' in summary
        assert 'operation_stats' in summary
        
        cache_stats = summary['cache_stats']
        assert cache_stats['hits'] == 1
        assert cache_stats['misses'] == 1
        assert cache_stats['hit_rate'] == 50.0
    
    def test_optimize_memory(self):
        """Тест оптимизации памяти"""
        with patch('gc.collect') as mock_gc:
            mock_gc.return_value = 10
            
            with patch.object(self.monitor.process, 'memory_info') as mock_memory:
                mock_memory.return_value = Mock(rss=50 * 1024 * 1024)  # 50MB
                
                self.monitor.optimize_memory()
                
                mock_gc.assert_called_once()

class TestPerformanceDecorator:
    """Тесты для декоратора производительности"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.monitor = get_performance_monitor()
    
    def test_sync_function_decorator(self):
        """Тест декоратора для синхронной функции"""
        @performance_decorator("test_sync")
        def test_function():
            time.sleep(0.1)
            return "success"
        
        result = test_function()
        
        assert result == "success"
        assert len(self.monitor.operation_history) == 1
        
        operation = self.monitor.operation_history[0]
        assert operation.operation_name == "test_sync"
        assert operation.success is True
        assert operation.execution_time > 0.1
    
    @pytest.mark.asyncio
    async def test_async_function_decorator(self):
        """Тест декоратора для асинхронной функции"""
        @performance_decorator("test_async")
        async def test_async_function():
            await asyncio.sleep(0.1)
            return "async_success"
        
        result = await test_async_function()
        
        assert result == "async_success"
        assert len(self.monitor.operation_history) == 1
        
        operation = self.monitor.operation_history[0]
        assert operation.operation_name == "test_async"
        assert operation.success is True
        assert operation.execution_time > 0.1
    
    def test_decorator_with_exception(self):
        """Тест декоратора с исключением"""
        @performance_decorator("test_exception")
        def failing_function():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            failing_function()
        
        assert len(self.monitor.operation_history) == 1
        
        operation = self.monitor.operation_history[0]
        assert operation.operation_name == "test_exception"
        assert operation.success is False
        assert "Test error" in operation.error_message

class TestPerformanceMetrics:
    """Тесты для PerformanceMetrics"""
    
    def test_performance_metrics_creation(self):
        """Тест создания PerformanceMetrics"""
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_percent=25.0,
            memory_percent=30.0,
            memory_used_mb=100.0,
            disk_io_read_mb=1.0,
            disk_io_write_mb=0.5,
            network_sent_mb=2.0,
            network_recv_mb=3.0,
            active_connections=5,
            cache_hit_rate=80.0,
            avg_response_time=0.5,
            requests_per_second=100.0
        )
        
        assert metrics.cpu_percent == 25.0
        assert metrics.memory_percent == 30.0
        assert metrics.memory_used_mb == 100.0
        assert metrics.active_connections == 5
        assert metrics.cache_hit_rate == 80.0

class TestOperationMetrics:
    """Тесты для OperationMetrics"""
    
    def test_operation_metrics_creation(self):
        """Тест создания OperationMetrics"""
        operation = OperationMetrics(
            operation_name="test_op",
            execution_time=1.5,
            success=True,
            error_message=None
        )
        
        assert operation.operation_name == "test_op"
        assert operation.execution_time == 1.5
        assert operation.success is True
        assert operation.error_message is None
    
    def test_operation_metrics_with_error(self):
        """Тест создания OperationMetrics с ошибкой"""
        operation = OperationMetrics(
            operation_name="failing_op",
            execution_time=0.5,
            success=False,
            error_message="Test error"
        )
        
        assert operation.operation_name == "failing_op"
        assert operation.execution_time == 0.5
        assert operation.success is False
        assert operation.error_message == "Test error"

if __name__ == "__main__":
    pytest.main([__file__]) 