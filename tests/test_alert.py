#!/usr/bin/env python3
"""
Тест отправки алертов в Telegram
"""

import asyncio
import aiohttp
import logging
from config import get_config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_telegram_alert():
    """Тест отправки простого алерта в Telegram"""
    try:
        config = get_config()
        
        # Проверяем конфигурацию
        bot_token = config.api_config['telegram']['bot_token']
        chat_id = config.api_config['telegram']['chat_id']
        
        logger.info(f"Bot token: {bot_token[:10]}...")
        logger.info(f"Chat ID: {chat_id}")
        
        # Простое тестовое сообщение
        message = "🧪 <b>ТЕСТ АЛЕРТА</b>\n\nЭто тестовое сообщение для проверки работы системы мониторинга."
        
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        logger.info("Отправляем тестовое сообщение...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(telegram_url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ Сообщение отправлено успешно!")
                    logger.info(f"Ответ Telegram: {result}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка отправки: {response.status}")
                    logger.error(f"Ответ: {error_text}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Ошибка теста: {e}")
        return False

async def test_github_alert():
    """Тест отправки GitHub алерта"""
    try:
        config = get_config()
        
        bot_token = config.api_config['telegram']['bot_token']
        chat_id = config.api_config['telegram']['chat_id']
        
        # Тестовый GitHub алерт
        message = "🔧 <b>GITHUB UPDATE</b>\n\nТестовый коммит в репозитории\n\n<b>Репозиторий:</b> FuelLabs/fuel-core\n<b>Коммит:</b> abc123\n<b>Сообщение:</b> Test commit"
        
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        logger.info("Отправляем GitHub алерт...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(telegram_url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ GitHub алерт отправлен успешно!")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка GitHub алерта: {response.status}")
                    logger.error(f"Ответ: {error_text}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Ошибка GitHub теста: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    logger.info("🚀 Начинаем тестирование алертов...")
    
    # Тест 1: Простой алерт
    logger.info("\n--- ТЕСТ 1: Простой алерт ---")
    success1 = await test_telegram_alert()
    
    await asyncio.sleep(2)
    
    # Тест 2: GitHub алерт
    logger.info("\n--- ТЕСТ 2: GitHub алерт ---")
    success2 = await test_github_alert()
    
    # Результаты
    logger.info("\n--- РЕЗУЛЬТАТЫ ---")
    logger.info(f"Простой алерт: {'✅ УСПЕХ' if success1 else '❌ ОШИБКА'}")
    logger.info(f"GitHub алерт: {'✅ УСПЕХ' if success2 else '❌ ОШИБКА'}")
    
    if success1 and success2:
        logger.info("🎉 Все тесты прошли успешно!")
    else:
        logger.error("💥 Некоторые тесты не прошли")

if __name__ == "__main__":
    asyncio.run(main()) 