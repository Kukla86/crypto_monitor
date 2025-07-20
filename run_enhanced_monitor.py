#!/usr/bin/env python3
"""
Запуск обновленной системы мониторинга криптовалют
Включает новые модули: производительность, алерты, восстановление
"""

import asyncio
import sys
import os
import logging
from datetime import datetime

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup_enhanced_logging():
    """Настройка расширенного логирования"""
    # Создаем директорию для логов если её нет
    os.makedirs('logs', exist_ok=True)
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(module)s:%(lineno)d] %(message)s',
        handlers=[
            logging.FileHandler('logs/enhanced_monitor.log', mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Отдельный логгер для ошибок
    error_logger = logging.getLogger('error_logger')
    error_logger.setLevel(logging.ERROR)
    error_handler = logging.FileHandler('logs/errors.log')
    error_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(module)s:%(lineno)d] %(message)s'))
    error_logger.addHandler(error_handler)
    
    return logging.getLogger(__name__)

async def check_system_health():
    """Проверка здоровья системы"""
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем доступность новых модулей
        from performance_monitor import get_performance_monitor
        from alert_manager import get_alert_manager
        from recovery_manager import get_recovery_manager
        
        # Инициализируем менеджеры
        perf_monitor = get_performance_monitor()
        alert_mgr = get_alert_manager()
        recovery_mgr = get_recovery_manager()
        
        logger.info("✅ Все новые модули доступны")
        
        # Получаем статистику
        perf_summary = perf_monitor.get_system_summary()
        alert_stats = alert_mgr.get_alert_stats(hours=1)
        recovery_stats = recovery_mgr.get_failure_stats(hours=1)
        
        logger.info(f"📊 Статистика производительности: {perf_summary.get('uptime_seconds', 0):.1f}с работы")
        logger.info(f"📊 Статистика алертов: {alert_stats.get('total_alerts', 0)} алертов за час")
        logger.info(f"📊 Статистика восстановления: {recovery_stats.get('total_failures', 0)} сбоев за час")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта модулей: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка проверки здоровья: {e}")
        return False

async def send_startup_alert():
    """Отправка алерта о запуске системы"""
    try:
        from alert_manager import AlertLevel, send_alert
        
        await send_alert(
            level=AlertLevel.INFO,
            title="🚀 Система мониторинга запущена",
            message=f"Обновленная система мониторинга криптовалют запущена в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            source="enhanced_monitor",
            template="system_info"
        )
        
        logging.getLogger(__name__).info("✅ Алерт о запуске отправлен")
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"⚠️ Не удалось отправить алерт о запуске: {e}")

async def main():
    """Главная функция запуска"""
    logger = setup_enhanced_logging()
    
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК ОБНОВЛЕННОЙ СИСТЕМЫ МОНИТОРИНГА")
    logger.info("=" * 60)
    
    # Проверяем здоровье системы
    logger.info("🔍 Проверка здоровья системы...")
    health_ok = await check_system_health()
    
    if not health_ok:
        logger.error("❌ Система не готова к запуску")
        return 1
    
    # Отправляем алерт о запуске
    await send_startup_alert()
    
    # Запускаем основной монитор
    logger.info("🔄 Запуск основного монитора...")
    
    try:
        # Импортируем и запускаем основной монитор
        from monitor import main as monitor_main
        
        await monitor_main()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в мониторе: {e}")
        return 1
    finally:
        logger.info("=" * 60)
        logger.info("🛑 СИСТЕМА МОНИТОРИНГА ОСТАНОВЛЕНА")
        logger.info("=" * 60)
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Программа остановлена пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1) 