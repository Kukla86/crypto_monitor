#!/usr/bin/env python3
"""
Простой тест для проверки новых модулей
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import time

def test_performance_monitor():
    """Тест модуля мониторинга производительности"""
    print("🔍 Тестирование performance_monitor...")
    
    try:
        from performance_monitor import get_performance_monitor, performance_decorator
        
        # Получаем монитор
        monitor = get_performance_monitor()
        print("✅ PerformanceMonitor создан")
        
        # Тестируем запись операций
        monitor.record_operation("test_op", 1.5, True)
        print("✅ Операция записана")
        
        # Тестируем кэш
        monitor.record_cache_hit()
        monitor.record_cache_miss()
        print("✅ Кэш записан")
        
        # Тестируем статистику
        stats = monitor.get_operation_stats()
        print(f"✅ Статистика получена: {stats}")
        
        # Тестируем декоратор
        @performance_decorator("test_decorator")
        def test_function():
            time.sleep(0.1)
            return "success"
        
        result = test_function()
        assert result == "success"
        print("✅ Декоратор работает")
        
        print("🎉 performance_monitor работает корректно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в performance_monitor: {e}")
        return False

def test_alert_manager():
    """Тест модуля менеджера алертов"""
    print("🔍 Тестирование alert_manager...")
    
    try:
        from alert_manager import get_alert_manager, AlertLevel, AlertChannel
        
        # Получаем менеджер
        manager = get_alert_manager()
        print("✅ AlertManager создан")
        
        # Тестируем создание алерта
        alert = manager.create_alert(
            level=AlertLevel.INFO,
            title="Test Alert",
            message="Test message",
            token_symbol="FUEL"
        )
        print("✅ Алерт создан")
        
        # Тестируем шаблоны
        templates = manager.alert_templates
        assert "price_spike" in templates
        assert "volume_surge" in templates
        print("✅ Шаблоны загружены")
        
        print("🎉 alert_manager работает корректно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в alert_manager: {e}")
        return False

def test_recovery_manager():
    """Тест модуля менеджера восстановления"""
    print("🔍 Тестирование recovery_manager...")
    
    try:
        from recovery_manager import get_recovery_manager, RecoveryConfig, RecoveryStrategy
        
        # Получаем менеджер
        manager = get_recovery_manager()
        print("✅ RecoveryManager создан")
        
        # Тестируем регистрацию компонента
        config = RecoveryConfig(max_retries=3)
        manager.register_component("test_component", config)
        print("✅ Компонент зарегистрирован")
        
        # Тестируем статистику
        stats = manager.get_failure_stats(hours=1)
        print(f"✅ Статистика получена: {stats}")
        
        print("🎉 recovery_manager работает корректно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в recovery_manager: {e}")
        return False

async def test_integration():
    """Интеграционный тест"""
    print("🔍 Интеграционное тестирование...")
    
    try:
        from performance_monitor import get_performance_monitor, performance_decorator
        from alert_manager import get_alert_manager, AlertLevel
        from recovery_manager import get_recovery_manager, RecoveryConfig, RecoveryStrategy
        
        # Получаем все менеджеры
        perf_monitor = get_performance_monitor()
        alert_manager = get_alert_manager()
        recovery_manager = get_recovery_manager()
        
        print("✅ Все менеджеры созданы")
        
        # Тестируем интеграцию
        @performance_decorator("integration_test")
        async def test_function():
            await asyncio.sleep(0.1)
            return "integration_success"
        
        result = await test_function()
        assert result == "integration_success"
        print("✅ Интеграционная функция выполнена")
        
        # Проверяем, что операция записана
        stats = perf_monitor.get_operation_stats("integration_test")
        assert stats['total_operations'] == 1
        print("✅ Операция записана в монитор")
        
        print("🎉 Интеграция работает корректно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в интеграции: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестов новых модулей...\n")
    
    results = []
    
    # Тестируем каждый модуль
    results.append(test_performance_monitor())
    print()
    
    results.append(test_alert_manager())
    print()
    
    results.append(test_recovery_manager())
    print()
    
    # Интеграционный тест
    results.append(asyncio.run(test_integration()))
    print()
    
    # Итоговый результат
    success_count = sum(results)
    total_count = len(results)
    
    print("=" * 50)
    print(f"📊 Результаты тестирования: {success_count}/{total_count} успешно")
    
    if success_count == total_count:
        print("🎉 Все тесты прошли успешно!")
        return 0
    else:
        print("⚠️ Некоторые тесты не прошли")
        return 1

if __name__ == "__main__":
    exit(main()) 