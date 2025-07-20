#!/usr/bin/env python3
"""
Тест GitHub мониторинга
"""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from config import get_config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_github_api():
    """Тест API GitHub"""
    try:
        # Тестовый репозиторий
        owner = "FuelLabs"
        repo = "fuel-core"
        
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {
            'per_page': 5,
            'since': (datetime.now() - timedelta(days=7)).isoformat()
        }
        
        logger.info(f"Запрашиваем коммиты: {owner}/{repo}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                response_text = await response.text()
                if response.status == 200:
                    commits = json.loads(response_text)
                    logger.info(f"✅ Получено {len(commits)} коммитов")
                    if not commits:
                        logger.warning(f"Пустой список коммитов. Ответ GitHub: {response_text}")
                    for i, commit in enumerate(commits[:3]):
                        logger.info(f"Коммит {i+1}: {commit['sha'][:8]} - {commit['commit']['message'][:50]}...")
                    return commits
                else:
                    logger.error(f"❌ Ошибка GitHub API: {response.status}")
                    logger.error(f"Ответ GitHub: {response_text}")
                    return []
                    
    except Exception as e:
        logger.error(f"❌ Ошибка теста GitHub API: {e}")
        return []

async def test_github_alert_send():
    """Тест отправки GitHub алерта"""
    try:
        config = get_config()
        
        # Тестовые данные коммита
        commit_data = {
            'sha': 'abc123def456',
            'commit': {
                'message': 'Test commit message for monitoring system',
                'author': {
                    'name': 'Test Author',
                    'email': 'test@example.com'
                }
            },
            'author': {
                'login': 'testuser'
            },
            'html_url': 'https://github.com/FuelLabs/fuel-core/commit/abc123def456'
        }
        
        repo_info = {
            'owner': 'FuelLabs',
            'repo': 'fuel-core'
        }
        
        # Формируем сообщение
        message = f"🔧 <b>GITHUB UPDATE</b>\n\n"
        message += f"<b>Репозиторий:</b> {repo_info['owner']}/{repo_info['repo']}\n"
        message += f"<b>Коммит:</b> {commit_data['sha'][:8]}\n"
        message += f"<b>Автор:</b> {commit_data['author']['login']}\n"
        message += f"<b>Сообщение:</b> {commit_data['commit']['message'][:100]}...\n\n"
        message += f"<b>Ссылка:</b> {commit_data['html_url']}"
        
        # Отправляем в Telegram
        bot_token = config.api_config['telegram']['bot_token']
        chat_id = config.api_config['telegram']['chat_id']
        
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        logger.info("Отправляем тестовый GitHub алерт...")
        
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
        logger.error(f"❌ Ошибка теста GitHub алерта: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    logger.info("🚀 Начинаем тестирование GitHub мониторинга...")
    
    # Тест 1: GitHub API
    logger.info("\n--- ТЕСТ 1: GitHub API ---")
    commits = await test_github_api()
    
    await asyncio.sleep(2)
    
    # Тест 2: Отправка алерта
    logger.info("\n--- ТЕСТ 2: Отправка GitHub алерта ---")
    success = await test_github_alert_send()
    
    # Результаты
    logger.info("\n--- РЕЗУЛЬТАТЫ ---")
    logger.info(f"GitHub API: {'✅ УСПЕХ' if commits else '❌ ОШИБКА'}")
    logger.info(f"Отправка алерта: {'✅ УСПЕХ' if success else '❌ ОШИБКА'}")
    
    if commits and success:
        logger.info("🎉 Все тесты GitHub мониторинга прошли успешно!")
    else:
        logger.error("💥 Некоторые тесты не прошли")

if __name__ == "__main__":
    asyncio.run(main()) 