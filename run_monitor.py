#!/usr/bin/env python3
"""
Скрипт запуска системы мониторинга криптовалют
Включает проверку зависимостей и инициализацию компонентов
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(module)s:%(lineno)d] %(message)s',
        handlers=[
            logging.FileHandler('monitoring.log', mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def check_dependencies():
    """Проверка зависимостей"""
    logger = logging.getLogger(__name__)
    
    required_modules = [
        'yaml', 'aiohttp', 'requests', 'asyncio', 'websockets',
        'telethon', 'discord', 'openai', 'flask', 'dotenv',
        'cachetools', 'pandas', 'numpy', 'sklearn'
    ]
    
    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        logger.error(f"Отсутствуют модули: {', '.join(missing_modules)}")
        logger.error("Установите зависимости: pip install -r requirements.txt")
        return False
    
    logger.info("Все зависимости установлены")
    return True

def check_config_files():
    """Проверка конфигурационных файлов"""
    logger = logging.getLogger(__name__)
    
    required_files = [
        'config.env',
        'tokens.json',
        'config/sources.yaml'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        logger.warning(f"Отсутствуют файлы: {', '.join(missing_files)}")
        logger.warning("Создайте недостающие файлы конфигурации")
        return False
    
    logger.info("Все конфигурационные файлы найдены")
    return True

async def main():
    """Основная функция"""
    logger = setup_logging()
    
    print("🚀 Запуск системы мониторинга криптовалют...")
    
    # Проверяем зависимости
    if not check_dependencies():
        print("❌ Ошибка: отсутствуют зависимости")
        return 1
    
    # Проверяем конфигурационные файлы
    if not check_config_files():
        print("⚠️  Предупреждение: отсутствуют некоторые конфигурационные файлы")
    
    try:
        # Импортируем основные модули
        from config_manager import get_config_manager
        from cache_manager import CacheManager
        
        # Инициализируем менеджеры
        config_manager = get_config_manager()
        cache_manager = CacheManager()
        
        logger.info("Менеджеры инициализированы")
        
        # Проверяем конфигурацию
        config_summary = config_manager.get_config_summary()
        logger.info(f"Конфигурация загружена: {config_summary['sources_count']} источников, {config_summary['tokens_count']} токенов")
        
        print("✅ Система готова к запуску")
        print("📊 Для запуска полного мониторинга используйте: python monitor.py")
        print("🌐 Для запуска веб-интерфейса используйте: python web_dashboard.py")
        
        return 0
        
    except Exception as e:
        logger.error(f"Ошибка инициализации: {e}")
        print(f"❌ Ошибка: {e}")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Завершение работы...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1) 