#!/usr/bin/env python3
"""
Тест AI-анализа GitHub коммитов
"""

import asyncio
import json
import logging
from config import get_config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ai_analysis():
    """Тест AI-анализа коммита"""
    try:
        # Импортируем функцию из monitor.py
        import sys
        sys.path.append('.')
        
        # Тестовые данные коммита
        commit_data = {
            'sha': 'abc123def456789',
            'commit': {
                'message': 'feat: add new smart contract functionality for token swaps',
                'author': {
                    'name': 'John Doe',
                    'email': 'john@example.com',
                    'date': '2024-01-15T10:30:00Z'
                }
            },
            'author': {
                'login': 'johndoe'
            },
            'stats': {
                'additions': 150,
                'deletions': 25,
                'total': 175
            },
            'files': [
                {
                    'filename': 'contracts/TokenSwap.sol',
                    'additions': 100,
                    'deletions': 10
                },
                {
                    'filename': 'tests/TokenSwap.test.js',
                    'additions': 50,
                    'deletions': 15
                }
            ]
        }
        
        repo_info = {
            'owner': 'FuelLabs',
            'repo': 'fuel-core'
        }
        
        logger.info("🧪 Тестируем AI-анализ коммита...")
        logger.info(f"Коммит: {commit_data['sha'][:8]}")
        logger.info(f"Сообщение: {commit_data['commit']['message']}")
        logger.info(f"Репозиторий: {repo_info['owner']}/{repo_info['repo']}")
        
        # Импортируем функцию анализа
        from monitor import analyze_github_changes_with_ai
        
        # Выполняем AI-анализ
        result = await analyze_github_changes_with_ai(commit_data, repo_info)
        
        logger.info("📊 Результат AI-анализа:")
        logger.info(f"  Важность: {result.get('importance')}")
        logger.info(f"  Влияние: {result.get('impact')}")
        logger.info(f"  Отправлять алерт: {result.get('should_alert')}")
        logger.info(f"  Краткое описание: {result.get('summary')}")
        logger.info(f"  Обоснование: {result.get('reason')}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста AI-анализа: {e}")
        return None

async def test_openai_connection():
    """Тест подключения к OpenAI"""
    try:
        from monitor import analyze_with_chatgpt
        
        logger.info("🔗 Тестируем подключение к OpenAI...")
        
        test_prompt = "Привет! Это тестовое сообщение. Ответь одним словом: 'OK'"
        
        response = await analyze_with_chatgpt(test_prompt, "test")
        
        if response and 'choices' in response:
            content = response['choices'][0]['message']['content']
            logger.info(f"✅ OpenAI отвечает: {content}")
            return True
        else:
            logger.error("❌ OpenAI не отвечает")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к OpenAI: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    logger.info("🚀 Начинаем тестирование AI-анализа GitHub...")
    
    # Тест 1: Подключение к OpenAI
    logger.info("\n--- ТЕСТ 1: Подключение к OpenAI ---")
    openai_ok = await test_openai_connection()
    
    await asyncio.sleep(2)
    
    # Тест 2: AI-анализ коммита
    logger.info("\n--- ТЕСТ 2: AI-анализ коммита ---")
    analysis_result = await test_ai_analysis()
    
    # Результаты
    logger.info("\n--- РЕЗУЛЬТАТЫ ---")
    logger.info(f"OpenAI подключение: {'✅ УСПЕХ' if openai_ok else '❌ ОШИБКА'}")
    logger.info(f"AI-анализ: {'✅ УСПЕХ' if analysis_result else '❌ ОШИБКА'}")
    
    if openai_ok and analysis_result:
        logger.info("🎉 Все тесты AI-анализа прошли успешно!")
        logger.info(f"📝 Рекомендация: {analysis_result.get('summary', 'Нет рекомендации')}")
    else:
        logger.error("💥 Некоторые тесты не прошли")

if __name__ == "__main__":
    asyncio.run(main()) 