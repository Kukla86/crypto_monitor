#!/usr/bin/env python3
"""
Интеграционные тесты для новых модулей
Проверяет взаимодействие между performance_monitor, alert_manager и recovery_manager
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from performance_monitor import get_performance_monitor, performance_decorator
from alert_manager import get_alert_manager, AlertLevel, AlertChannel
from recovery_manager import get_recovery_manager, RecoveryConfig, RecoveryStrategy

class TestIntegrationNewModules:
    """Интеграционные тесты для новых модулей"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        # Получаем экземпляры менеджеров
        self.performance_monitor = get_performance_monitor()
        self.alert_manager = get_alert_manager()
        self.recovery_manager = get_recovery_manager()
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        # Очищаем историю
        self.performance_monitor.operation_history.clear()
        self.alert_manager.alerts_history.clear()
        self.recovery_manager.failure_history.clear()
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_with_alerts(self):
        """Тест мониторинга производительности с алертами"""
        # Создаем функцию с декоратором производительности
        @performance_decorator("test_integration")
        async def slow_function():
            await asyncio.sleep(0.1)  # Имитируем медленную операцию
            return "success"
        
        # Выполняем функцию
        result = await slow_function()
        
        assert result == "success"
        
        # Проверяем, что операция записана
        assert len(self.performance_monitor.operation_history) == 1
        
        operation = self.performance_monitor.operation_history[0]
        assert operation.operation_name == "test_integration"
        assert operation.success is True
        assert operation.execution_time > 0.1
        
        # Проверяем статистику
        stats = self.performance_monitor.get_operation_stats("test_integration")
        assert stats['total_operations'] == 1
        assert stats['success_rate'] == 100.0
    
    @pytest.mark.asyncio
    async def test_alert_manager_with_templates(self):
        """Тест менеджера алертов с шаблонами"""
        # Отправляем алерт с шаблоном
        success = await self.alert_manager.send_alert(
            self.alert_manager.create_alert(
                level=AlertLevel.WARNING,
                title="Test Alert",
                message="Test message",
                token_symbol="FUEL",
                source="test",
                template="price_spike",
                data={"token": "FUEL", "change": "15", "period": "1 час"}
            )
        )
        
        assert success is True
        
        # Проверяем, что алерт записан
        assert len(self.alert_manager.alerts_history) == 1
        
        alert = self.alert_manager.alerts_history[0]
        assert alert.token_symbol == "FUEL"
        assert alert.source == "test"
        assert alert.template == "price_spike"
    
    @pytest.mark.asyncio
    async def test_recovery_manager_with_retry(self):
        """Тест менеджера восстановления с повторными попытками"""
        # Регистрируем компонент
        config = RecoveryConfig(
            max_retries=2,
            retry_delay=0.1,
            strategy=RecoveryStrategy.RETRY
        )
        self.recovery_manager.register_component("test_component", config)
        
        # Создаем функцию, которая падает первые 2 раза
        call_count = 0
        
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Test error {call_count}")
            return "success"
        
        # Выполняем с восстановлением
        result = await self.recovery_manager.execute_with_recovery(
            "test_component", failing_function
        )
        
        assert result == "success"
        assert call_count == 3
        
        # Проверяем, что сбои записаны
        assert len(self.recovery_manager.failure_history) == 2
        
        # Проверяем, что проблема разрешена
        stats = self.recovery_manager.get_failure_stats(hours=1)
        assert stats['total_failures'] == 2
        assert stats['resolved_failures'] == 1
    
    @pytest.mark.asyncio
    async def test_integration_performance_alert_recovery(self):
        """Интеграционный тест: производительность -> алерт -> восстановление"""
        
        # 1. Мониторинг производительности
        @performance_decorator("critical_operation")
        async def critical_operation():
            # Имитируем критическую операцию
            await asyncio.sleep(0.05)
            return "critical_success"
        
        result = await critical_operation()
        assert result == "critical_success"
        
        # 2. Проверяем метрики производительности
        current_metrics = self.performance_monitor.get_current_metrics()
        if current_metrics:
            # Если CPU или память превышают пороги, отправляем алерт
            if current_metrics.cpu_percent > 80 or current_metrics.memory_percent > 85:
                alert = self.alert_manager.create_alert(
                    level=AlertLevel.WARNING,
                    title="Performance Warning",
                    message=f"High resource usage: CPU {current_metrics.cpu_percent}%, Memory {current_metrics.memory_percent}%",
                    source="performance_monitor",
                    template="performance_warning",
                    data={
                        "metric": "resource_usage",
                        "value": f"CPU: {current_metrics.cpu_percent}%, Memory: {current_metrics.memory_percent}%",
                        "threshold": "80%"
                    }
                )
                
                success = await self.alert_manager.send_alert(alert)
                assert success is True
        
        # 3. Проверяем статистику
        perf_stats = self.performance_monitor.get_operation_stats("critical_operation")
        assert perf_stats['total_operations'] == 1
        assert perf_stats['success_rate'] == 100.0
        
        alert_stats = self.alert_manager.get_alert_stats(hours=1)
        assert 'total_alerts' in alert_stats
    
    @pytest.mark.asyncio
    async def test_rate_limiting_integration(self):
        """Тест интеграции rate limiting"""
        
        # Отправляем несколько алертов быстро
        for i in range(5):
            alert = self.alert_manager.create_alert(
                level=AlertLevel.INFO,
                title=f"Test Alert {i}",
                message=f"Test message {i}",
                token_symbol="FUEL"
            )
            success = await self.alert_manager.send_alert(alert)
            assert success is True
        
        # Проверяем, что алерты записаны
        assert len(self.alert_manager.alerts_history) == 5
        
        # Проверяем rate limiting
        # Попробуем отправить еще много алертов
        for i in range(100):
            alert = self.alert_manager.create_alert(
                level=AlertLevel.INFO,
                title=f"Rate Test {i}",
                message=f"Rate test message {i}",
                token_symbol="FUEL"
            )
            success = await self.alert_manager.send_alert(alert)
            if not success:
                break  # Rate limit сработал
        
        # Должно быть ограничение на количество алертов
        assert len(self.alert_manager.alerts_history) <= 65  # 60 + 5 из предыдущего теста
    
    @pytest.mark.asyncio
    async def test_health_check_integration(self):
        """Тест интеграции проверки здоровья"""
        
        # Добавляем проверку здоровья для компонента
        async def health_check():
            # Простая проверка здоровья
            return True
        
        self.recovery_manager.add_health_check("test_component", health_check)
        
        # Проверяем состояние здоровья
        health = self.recovery_manager.get_component_health("test_component")
        assert health['component'] == "test_component"
        assert 'is_healthy' in health
        assert 'recent_failures' in health
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self):
        """Тест интеграции обработки ошибок"""
        
        # Создаем функцию, которая всегда падает
        async def always_failing_function():
            raise RuntimeError("Always failing")
        
        # Регистрируем с конфигурацией fallback
        fallback_called = False
        
        async def fallback_function():
            nonlocal fallback_called
            fallback_called = True
        
        config = RecoveryConfig(
            max_retries=1,
            strategy=RecoveryStrategy.FALLBACK,
            fallback_function=fallback_function
        )
        
        self.recovery_manager.register_component("failing_component", config)
        
        # Выполняем функцию
        with pytest.raises(RuntimeError):
            await self.recovery_manager.execute_with_recovery(
                "failing_component", always_failing_function
            )
        
        # Проверяем, что fallback был вызван
        assert fallback_called is True
        
        # Проверяем, что сбой записан
        stats = self.recovery_manager.get_failure_stats(hours=1)
        assert stats['total_failures'] >= 1
    
    def test_system_summary_integration(self):
        """Тест интеграции сводки системы"""
        
        # Получаем сводки от всех менеджеров
        perf_summary = self.performance_monitor.get_system_summary()
        alert_stats = self.alert_manager.get_alert_stats(hours=1)
        recovery_stats = self.recovery_manager.get_failure_stats(hours=1)
        
        # Проверяем структуру данных
        assert 'uptime_seconds' in perf_summary
        assert 'current_metrics' in perf_summary
        assert 'cache_stats' in perf_summary
        assert 'operation_stats' in perf_summary
        
        assert 'total_alerts' in alert_stats
        assert 'by_level' in alert_stats
        assert 'by_token' in alert_stats
        
        assert 'total_failures' in recovery_stats
        assert 'resolved_failures' in recovery_stats
        assert 'by_component' in recovery_stats
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Тест конкурентных операций"""
        
        # Создаем несколько конкурентных операций
        async def concurrent_operation(operation_id):
            @performance_decorator(f"concurrent_op_{operation_id}")
            async def op():
                await asyncio.sleep(0.01)
                return f"result_{operation_id}"
            
            return await op()
        
        # Запускаем конкурентно
        tasks = [concurrent_operation(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # Проверяем результаты
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result == f"result_{i}"
        
        # Проверяем, что все операции записаны
        assert len(self.performance_monitor.operation_history) == 5
        
        # Проверяем статистику
        stats = self.performance_monitor.get_operation_stats()
        assert stats['total_operations'] == 5
        assert stats['success_rate'] == 100.0

if __name__ == "__main__":
    pytest.main([__file__]) 