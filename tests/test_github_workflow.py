#!/usr/bin/env python3
"""
Тест полного workflow GitHub мониторинга
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from config import get_config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_github_workflow():
    """Тест полного workflow GitHub мониторинга"""
    try:
        from monitor import analyze_github_changes_with_ai, send_github_alert
        
        # Симулируем новый коммит
        commit_data = {
            'sha': 'test123abc456',
            'commit': {
                'message': 'fix: resolve critical security vulnerability in token transfer',
                'author': {
                    'name': 'Security Team',
                    'email': 'security@fuellabs.com',
                    'date': datetime.now().isoformat()
                }
            },
            'author': {
                'login': 'security-team'
            },
            'stats': {
                'additions': 50,
                'deletions': 30,
                'total': 80
            },
            'files': [
                {
                    'filename': 'src/security/TokenTransfer.sol',
                    'additions': 30,
                    'deletions': 20
                },
                {
                    'filename': 'tests/security/TokenTransfer.test.js',
                    'additions': 20,
                    'deletions': 10
                }
            ]
        }
        
        repo_info = {
            'owner': 'FuelLabs',
            'repo': 'fuel-core'
        }
        
        logger.info("🔄 Тестируем полный workflow GitHub мониторинга...")
        logger.info(f"Коммит: {commit_data['sha'][:8]}")
        logger.info(f"Сообщение: {commit_data['commit']['message']}")
        
        # Шаг 1: AI-анализ
        logger.info("\n--- ШАГ 1: AI-анализ ---")
        ai_analysis = await analyze_github_changes_with_ai(commit_data, repo_info)
        
        logger.info(f"AI результат: важность={ai_analysis.get('importance')}, влияние={ai_analysis.get('impact')}")
        logger.info(f"Отправлять алерт: {ai_analysis.get('should_alert')}")
        
        # Шаг 2: Формирование сообщения
        logger.info("\n--- ШАГ 2: Формирование сообщения ---")
        
        if ai_analysis.get('should_alert', False):
            importance = ai_analysis.get('importance', 'medium')
            level_map = {
                'critical': 'CRITICAL',
                'high': 'HIGH', 
                'medium': 'MEDIUM',
                'low': 'INFO'
            }
            level = level_map.get(importance, 'MEDIUM')
            
            # Используем AI-результат для сообщения
            summary = ai_analysis.get('summary', 'Обновление в репозитории')
            reason = ai_analysis.get('reason', '')
            
            message = f"🔧 <b>GITHUB UPDATE - {level}</b>\n\n"
            message += f"<b>Репозиторий:</b> {repo_info['owner']}/{repo_info['repo']}\n"
            message += f"<b>Коммит:</b> {commit_data['sha'][:8]}\n"
            message += f"<b>Автор:</b> {commit_data['author']['login']}\n"
            message += f"<b>AI-анализ:</b> {summary}\n"
            if reason:
                message += f"<b>Обоснование:</b> {reason[:100]}...\n"
            message += f"\n<b>Ссылка:</b> https://github.com/{repo_info['owner']}/{repo_info['repo']}/commit/{commit_data['sha']}"
            
            logger.info(f"Сформировано сообщение: {message[:200]}...")
            
            # Шаг 3: Отправка алерта
            logger.info("\n--- ШАГ 3: Отправка алерта ---")
            commit_link = f"https://github.com/{repo_info['owner']}/{repo_info['repo']}/commit/{commit_data['sha']}"
            
            await send_github_alert(message, level, commit_link, repo_info)
            logger.info("✅ Алерт отправлен!")
            
            return True
        else:
            logger.info("⚠️ AI рекомендует не отправлять алерт")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка workflow: {e}")
        return False

async def test_with_real_commit():
    """Тест с реальным коммитом из GitHub"""
    try:
        import aiohttp
        
        # Получаем реальный коммит
        owner = "torvalds"
        repo = "linux"
        
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {
            'per_page': 1,
            'since': (datetime.now() - timedelta(days=30)).isoformat()
        }
        
        logger.info(f"🔍 Получаем реальный коммит из {owner}/{repo}...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    commits = await response.json()
                    if commits:
                        commit = commits[0]
                        logger.info(f"Найден коммит: {commit['sha'][:8]} - {commit['commit']['message'][:50]}...")
                        
                        # Получаем детальную информацию
                        commit_detail_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit['sha']}"
                        async with session.get(commit_detail_url) as detail_response:
                            if detail_response.status == 200:
                                detailed_commit = await detail_response.json()
                                
                                repo_info = {'owner': owner, 'repo': repo}
                                
                                # AI-анализ реального коммита
                                from monitor import analyze_github_changes_with_ai
                                ai_analysis = await analyze_github_changes_with_ai(detailed_commit, repo_info)
                                
                                logger.info(f"AI-анализ реального коммита:")
                                logger.info(f"  Важность: {ai_analysis.get('importance')}")
                                logger.info(f"  Влияние: {ai_analysis.get('impact')}")
                                logger.info(f"  Описание: {ai_analysis.get('summary')}")
                                
                                return True
                    
                    logger.warning("Не найдено коммитов")
                    return False
                else:
                    logger.error(f"Ошибка GitHub API: {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Ошибка теста с реальным коммитом: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    logger.info("🚀 Начинаем тестирование GitHub workflow...")
    
    # Тест 1: Симулированный workflow
    logger.info("\n--- ТЕСТ 1: Симулированный workflow ---")
    workflow_ok = await test_github_workflow()
    
    await asyncio.sleep(3)
    
    # Тест 2: Реальный коммит
    logger.info("\n--- ТЕСТ 2: Реальный коммит ---")
    real_commit_ok = await test_with_real_commit()
    
    # Результаты
    logger.info("\n--- РЕЗУЛЬТАТЫ ---")
    logger.info(f"Симулированный workflow: {'✅ УСПЕХ' if workflow_ok else '❌ ОШИБКА'}")
    logger.info(f"Реальный коммит: {'✅ УСПЕХ' if real_commit_ok else '❌ ОШИБКА'}")
    
    if workflow_ok:
        logger.info("🎉 GitHub workflow работает корректно!")
    else:
        logger.error("💥 Есть проблемы в workflow")

if __name__ == "__main__":
    asyncio.run(main()) 