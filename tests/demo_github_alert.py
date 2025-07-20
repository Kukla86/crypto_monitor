#!/usr/bin/env python3
"""
Демонстрация нового формата GitHub алерта
"""

import asyncio
import aiohttp
from dotenv import load_dotenv
import os

# Загружаем переменные окружения
load_dotenv('config.env')

async def demo_github_alert():
    """Демонстрация нового формата GitHub алерта"""
    
    # Тестовые данные AI анализа
    ai_analysis = {
        'importance': 'high',
        'impact': 'positive',
        'summary': 'Добавлена новая функция оптимизации транзакций, которая значительно улучшает производительность сети. Внесены критические изменения в механизм консенсуса.',
        'reason': 'Критическое обновление производительности',
        'technical_details': 'Оптимизация RPC endpoints, улучшение memory management',
        'should_alert': True
    }
    
    # Тестовые данные коммита
    repo_info = {'owner': 'FuelLabs', 'repo': 'fuel-core'}
    commit_link = 'https://github.com/FuelLabs/fuel-core/commit/abc123'
    
    # Формируем новый короткий формат
    impact_emoji = {
        'positive': '🚀',
        'negative': '⚠️',
        'neutral': '📝'
    }.get(ai_analysis['impact'], '📝')
    
    # Короткое резюме на русском
    short_summary = ai_analysis['summary'][:200] + "..." if len(ai_analysis['summary']) > 200 else ai_analysis['summary']
    
    alert_message = f"{impact_emoji} <b>GitHub: {repo_info['owner']}/{repo_info['repo']}</b>\n\n"
    alert_message += f"{short_summary}\n\n"
    alert_message += f"🔗 {commit_link}"
    
    print("=== НОВЫЙ ФОРМАТ GITHUB АЛЕРТА ===")
    print(alert_message)
    print("\n=== СТАРЫЙ ФОРМАТ (для сравнения) ===")
    
    # Старый формат для сравнения
    old_format = f"{impact_emoji} <b>HIGH - GITHUB UPDATE</b>\n\n"
    old_format += f"<b>Репозиторий:</b> {repo_info['owner']}/{repo_info['repo']}\n"
    old_format += f"<b>Важность:</b> {ai_analysis['importance'].upper()}\n"
    old_format += f"<b>Влияние:</b> {ai_analysis['impact'].upper()}\n\n"
    old_format += f"<b>AI Анализ:</b>\n{ai_analysis['summary']}\n\n"
    old_format += f"<b>Технические детали:</b>\n{ai_analysis['technical_details']}\n\n"
    old_format += f"<b>Обоснование:</b>\n{ai_analysis['reason']}\n\n"
    old_format += f"<b>Ссылка:</b> {commit_link}"
    
    print(old_format)
    print(f"\nДлина нового формата: {len(alert_message)} символов")
    print(f"Длина старого формата: {len(old_format)} символов")
    print(f"Сокращение: {len(old_format) - len(alert_message)} символов")

if __name__ == "__main__":
    asyncio.run(demo_github_alert()) 