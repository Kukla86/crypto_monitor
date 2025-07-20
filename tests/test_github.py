#!/usr/bin/env python3
"""
Тестовый скрипт для проверки GitHub мониторинга
"""

import asyncio
import logging
from dotenv import load_dotenv
import os

# Загружаем переменные окружения
load_dotenv('config.env')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

# Импортируем функции из monitor.py
import sys
sys.path.append('.')

from monitor import check_github, analyze_github_changes_with_ai

async def test_github_monitoring():
    """Тестируем GitHub мониторинг"""
    logger.info("🧪 Запуск теста GitHub мониторинга...")
    
    try:
        # Тестируем GitHub мониторинг
        await check_github()
        logger.info("✅ GitHub мониторинг завершен успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в GitHub мониторинге: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_github_monitoring()) 