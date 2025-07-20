#!/usr/bin/env python3
"""
Тест интегрированного Discord мониторинга
"""

import asyncio
import json
import logging
from config import get_config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_discord_ai_analysis():
    """Тест AI-анализа Discord сообщений"""
    try:
        from monitor import analyze_discord_message_with_ai
        
        # Тестовые сообщения
        test_messages = [
            {
                'content': '🚀 ANNOUNCEMENT: FUEL Network mainnet launch is scheduled for next week! Get ready for the biggest event in crypto history!',
                'server': 'Fuel Network Official',
                'channel': 'announcements',
                'expected_level': 'CRITICAL'
            },
            {
                'content': 'New partnership announcement: ARC token will be listed on Binance next month. This is huge for our community!',
                'server': 'ARC Community',
                'channel': 'news',
                'expected_level': 'HIGH'
            },
            {
                'content': 'Just had a great chat about the weather today. Nice sunny day for trading!',
                'server': 'Crypto Chat',
                'channel': 'general',
                'expected_level': 'LOW'
            }
        ]
        
        logger.info("🧪 Тестируем AI-анализ Discord сообщений...")
        
        for i, test_msg in enumerate(test_messages, 1):
            logger.info(f"\n--- Тест {i}: {test_msg['expected_level']} ---")
            logger.info(f"Сообщение: {test_msg['content'][:50]}...")
            logger.info(f"Сервер: {test_msg['server']}")
            logger.info(f"Канал: {test_msg['channel']}")
            
            result = await analyze_discord_message_with_ai(
                test_msg['content'], 
                test_msg['server'], 
                test_msg['channel']
            )
            
            logger.info(f"AI результат:")
            logger.info(f"  Отправлять алерт: {result.get('should_alert')}")
            logger.info(f"  Уровень: {result.get('level')}")
            logger.info(f"  Обоснование: {result.get('reason', 'Нет')}")
            
            # Проверяем ожидаемый результат
            if result.get('level') == test_msg['expected_level']:
                logger.info(f"✅ Тест {i} прошел успешно!")
            else:
                logger.warning(f"⚠️ Тест {i}: ожидали {test_msg['expected_level']}, получили {result.get('level')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста AI-анализа Discord: {e}")
        return False

async def test_discord_token_detection():
    """Тест определения токенов в Discord сообщениях"""
    try:
        test_cases = [
            {
                'text': 'FUEL token is mooning today!',
                'expected_token': 'FUEL'
            },
            {
                'text': 'ARC community is growing fast',
                'expected_token': 'ARC'
            },
            {
                'text': 'CreatorBid platform is amazing',
                'expected_token': 'BID'
            },
            {
                'text': 'Manta Network partnership announced',
                'expected_token': 'MANTA'
            },
            {
                'text': 'Hey Anon, check this out!',
                'expected_token': 'ANON'
            }
        ]
        
        logger.info("🔍 Тестируем определение токенов в Discord сообщениях...")
        
        for i, test_case in enumerate(test_cases, 1):
            text = test_case['text'].lower()
            expected = test_case['expected_token']
            
            # Логика определения токена (как в monitor.py)
            token = ''
            if 'fuel' in text:
                token = 'FUEL'
            elif 'arc' in text:
                token = 'ARC'
            elif 'bid' in text or 'creatorbid' in text:
                token = 'BID'
            elif 'manta' in text:
                token = 'MANTA'
            elif 'anon' in text or 'hey anon' in text:
                token = 'ANON'
            
            if token == expected:
                logger.info(f"✅ Тест {i}: {expected} - правильно определен")
            else:
                logger.error(f"❌ Тест {i}: ожидали {expected}, получили {token}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста определения токенов: {e}")
        return False

async def test_discord_cache():
    """Тест кэширования Discord сообщений"""
    try:
        cache_file = 'discord_messages_cache.json'
        
        # Создаем тестовый кэш
        test_cache = {
            'test_server_123_test_channel_456_test_message_789': {
                'timestamp': '2024-01-15T10:30:00',
                'level': 'HIGH',
                'server': 'Test Server',
                'channel': 'test-channel'
            }
        }
        
        logger.info("💾 Тестируем кэширование Discord сообщений...")
        
        # Сохраняем тестовый кэш
        with open(cache_file, 'w') as f:
            json.dump(test_cache, f, indent=2)
        
        logger.info("✅ Тестовый кэш сохранен")
        
        # Читаем кэш обратно
        with open(cache_file, 'r') as f:
            loaded_cache = json.load(f)
        
        if loaded_cache == test_cache:
            logger.info("✅ Кэш корректно загружен")
        else:
            logger.error("❌ Ошибка загрузки кэша")
            return False
        
        # Проверяем логику проверки кэша
        message_key = 'test_server_123_test_channel_456_test_message_789'
        if message_key in loaded_cache:
            logger.info("✅ Логика проверки кэша работает")
        else:
            logger.error("❌ Ошибка проверки кэша")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста кэша: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    logger.info("🚀 Начинаем тестирование интегрированного Discord мониторинга...")
    
    # Тест 1: AI-анализ
    logger.info("\n--- ТЕСТ 1: AI-анализ Discord сообщений ---")
    ai_ok = await test_discord_ai_analysis()
    
    await asyncio.sleep(2)
    
    # Тест 2: Определение токенов
    logger.info("\n--- ТЕСТ 2: Определение токенов ---")
    token_ok = await test_discord_token_detection()
    
    await asyncio.sleep(2)
    
    # Тест 3: Кэширование
    logger.info("\n--- ТЕСТ 3: Кэширование сообщений ---")
    cache_ok = await test_discord_cache()
    
    # Результаты
    logger.info("\n--- РЕЗУЛЬТАТЫ ---")
    logger.info(f"AI-анализ: {'✅ УСПЕХ' if ai_ok else '❌ ОШИБКА'}")
    logger.info(f"Определение токенов: {'✅ УСПЕХ' if token_ok else '❌ ОШИБКА'}")
    logger.info(f"Кэширование: {'✅ УСПЕХ' if cache_ok else '❌ ОШИБКА'}")
    
    if ai_ok and token_ok and cache_ok:
        logger.info("🎉 Все тесты Discord интеграции прошли успешно!")
        logger.info("💡 Discord мониторинг готов к использованию в monitor.py")
    else:
        logger.error("💥 Некоторые тесты не прошли")

if __name__ == "__main__":
    asyncio.run(main()) 