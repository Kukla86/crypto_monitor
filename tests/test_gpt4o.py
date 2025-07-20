#!/usr/bin/env python3
"""
Тест работы GPT-4o (GPT-4 Omni)
"""

import asyncio
import logging
from config import get_config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_gpt4_analysis():
    """Тест анализа с GPT-4"""
    try:
        from monitor import analyze_with_chatgpt
        
        # Тестовый промпт
        test_prompt = """
        Проанализируй это сообщение из Discord сервера криптовалютного проекта:

        Сервер: Fuel Network Official
        Канал: announcements
        Сообщение: 🚀 ANNOUNCEMENT: FUEL Network mainnet launch is scheduled for next week! Get ready for the biggest event in crypto history!

        Оцени важность этого сообщения для криптовалют FUEL и ARC:

        КРИТЕРИИ ВАЖНОСТИ:
        - CRITICAL: анонсы релизов, критические обновления, проблемы безопасности
        - HIGH: новые функции, партнерства, листинги, важные обновления
        - MEDIUM: общие новости, обсуждения, технические детали
        - LOW: обычные чаты, мемы, спам

        Ответь в формате JSON:
        {
            "should_alert": true/false,
            "level": "CRITICAL/HIGH/MEDIUM/LOW",
            "reason": "обоснование на русском"
        }
        """
        
        logger.info("🧪 Тестируем GPT-4o анализ...")
        
        response = await analyze_with_chatgpt(test_prompt, "gpt4_test")
        
        if response and 'choices' in response:
            content = response['choices'][0]['message']['content']
            logger.info(f"✅ GPT-4o ответ получен:")
            logger.info(f"📝 Содержание: {content[:200]}...")
            
            # Проверяем, что это JSON (обрабатываем markdown формат)
            import json
            import re
            
            try:
                # Убираем markdown обрамление если есть
                cleaned_content = content.strip()
                if cleaned_content.startswith('```json'):
                    cleaned_content = cleaned_content[7:]  # Убираем ```json
                if cleaned_content.startswith('```'):
                    cleaned_content = cleaned_content[3:]  # Убираем ```
                if cleaned_content.endswith('```'):
                    cleaned_content = cleaned_content[:-3]  # Убираем ```
                
                cleaned_content = cleaned_content.strip()
                
                analysis = json.loads(cleaned_content)
                logger.info(f"✅ JSON успешно распарсен:")
                logger.info(f"  should_alert: {analysis.get('should_alert')}")
                logger.info(f"  level: {analysis.get('level')}")
                logger.info(f"  reason: {analysis.get('reason', 'Нет')}")
                return True
            except json.JSONDecodeError:
                logger.error(f"❌ Ошибка парсинга JSON: {content}")
                return False
        else:
            logger.error("❌ GPT-4 не вернул ответ")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка теста GPT-4o: {e}")
        return False

async def test_gpt4_github_analysis():
    """Тест GitHub анализа с GPT-4o"""
    try:
        from monitor import analyze_github_changes_with_ai
        
        # Тестовые данные коммита
        commit_data = {
            'sha': 'test123abc456',
            'commit': {
                'message': 'feat: implement critical security fix for token transfers',
                'author': {
                    'name': 'Security Team',
                    'email': 'security@fuellabs.com',
                    'date': '2024-01-15T10:30:00Z'
                }
            },
            'author': {
                'login': 'security-team'
            },
            'stats': {
                'additions': 100,
                'deletions': 50,
                'total': 150
            },
            'files': [
                {
                    'filename': 'src/security/TokenTransfer.sol',
                    'additions': 80,
                    'deletions': 30
                }
            ]
        }
        
        repo_info = {
            'owner': 'FuelLabs',
            'repo': 'fuel-core'
        }
        
        logger.info("🧪 Тестируем GPT-4o GitHub анализ...")
        
        result = await analyze_github_changes_with_ai(commit_data, repo_info)
        
        logger.info(f"✅ GPT-4o GitHub анализ результат:")
        logger.info(f"  importance: {result.get('importance')}")
        logger.info(f"  impact: {result.get('impact')}")
        logger.info(f"  should_alert: {result.get('should_alert')}")
        logger.info(f"  summary: {result.get('summary', 'Нет')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста GPT-4o GitHub анализа: {e}")
        return False

async def test_gpt4_discord_analysis():
    """Тест Discord анализа с GPT-4o"""
    try:
        from monitor import analyze_discord_message_with_ai
        
        test_message = "🚀 ANNOUNCEMENT: ARC token will be listed on Binance next month! This is huge for our community!"
        
        logger.info("🧪 Тестируем GPT-4o Discord анализ...")
        
        result = await analyze_discord_message_with_ai(
            test_message, 
            "ARC Community", 
            "announcements"
        )
        
        logger.info(f"✅ GPT-4o Discord анализ результат:")
        logger.info(f"  should_alert: {result.get('should_alert')}")
        logger.info(f"  level: {result.get('level')}")
        logger.info(f"  reason: {result.get('reason', 'Нет')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста GPT-4o Discord анализа: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    logger.info("🚀 Начинаем тестирование GPT-4o...")
    
    # Тест 1: Общий анализ
    logger.info("\n--- ТЕСТ 1: Общий GPT-4o анализ ---")
    general_ok = await test_gpt4_analysis()
    
    await asyncio.sleep(2)
    
    # Тест 2: GitHub анализ
    logger.info("\n--- ТЕСТ 2: GitHub анализ с GPT-4o ---")
    github_ok = await test_gpt4_github_analysis()
    
    await asyncio.sleep(2)
    
    # Тест 3: Discord анализ
    logger.info("\n--- ТЕСТ 3: Discord анализ с GPT-4o ---")
    discord_ok = await test_gpt4_discord_analysis()
    
    # Результаты
    logger.info("\n--- РЕЗУЛЬТАТЫ ---")
    logger.info(f"Общий анализ: {'✅ УСПЕХ' if general_ok else '❌ ОШИБКА'}")
    logger.info(f"GitHub анализ: {'✅ УСПЕХ' if github_ok else '❌ ОШИБКА'}")
    logger.info(f"Discord анализ: {'✅ УСПЕХ' if discord_ok else '❌ ОШИБКА'}")
    
    if general_ok and github_ok and discord_ok:
        logger.info("🎉 Все тесты GPT-4o прошли успешно!")
        logger.info("💡 GPT-4o работает корректно во всех модулях")
    else:
        logger.error("💥 Некоторые тесты GPT-4o не прошли")

if __name__ == "__main__":
    asyncio.run(main()) 