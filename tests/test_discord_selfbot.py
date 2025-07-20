#!/usr/bin/env python3
"""
Тестовый скрипт для Discord Selfbot Monitor
Проверяет подключение и настройки без запуска полного мониторинга
"""

import asyncio
import os
from discord_selfbot_monitor import DiscordSelfbotMonitor
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv('config.env')

async def test_discord_selfbot():
    """Тестирование Discord selfbot"""
    print("🧪 Тестирование Discord Selfbot Monitor...")
    
    # Создаем экземпляр монитора
    monitor = DiscordSelfbotMonitor()
    
    # Проверяем настройки
    print(f"📋 Проверка настроек:")
    print(f"   Discord Token: {'✅' if monitor.discord_token else '❌'}")
    print(f"   OpenAI API Key: {'✅' if monitor.openai_api_key else '❌'}")
    print(f"   Telegram Bot Token: {'✅' if monitor.telegram_bot_token else '❌'}")
    print(f"   Telegram Chat ID: {'✅' if monitor.telegram_chat_id else '❌'}")
    print(f"   Target Channels: {len(monitor.target_channels)} каналов")
    
    if not monitor.discord_token:
        print("\n❌ DISCORD_USER_TOKEN не настроен!")
        print("Добавьте его в config.env:")
        print("DISCORD_USER_TOKEN=ваш_токен_здесь")
        return
    
    if not monitor.openai_api_key:
        print("\n❌ OPENAI_API_KEY не настроен!")
        print("Добавьте его в config.env:")
        print("OPENAI_API_KEY=ваш_ключ_здесь")
        return
    
    # Создаем HTTP сессию
    import aiohttp
    monitor.session = aiohttp.ClientSession(headers=monitor.headers)
    
    try:
        print(f"\n🔍 Тестирование подключения к каналам:")
        
        for channel_id in monitor.target_channels:
            try:
                # Получаем информацию о канале
                channel_name = await monitor.get_channel_name(channel_id)
                print(f"   Канал {channel_id}: {channel_name}")
                
                # Пробуем получить сообщения
                url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=1"
                async with monitor.session.get(url) as response:
                    if response.status == 200:
                        messages = await response.json()
                        print(f"   ✅ Доступен, сообщений: {len(messages)}")
                    else:
                        print(f"   ❌ Ошибка {response.status}: {response.reason}")
                        
            except Exception as e:
                print(f"   ❌ Ошибка канала {channel_id}: {e}")
        
        print(f"\n🤖 Тестирование OpenAI:")
        if monitor.openai_api_key:
            try:
                # Тестовый анализ
                test_content = "🚀 BIG ANNOUNCEMENT! We're launching mainnet next month with airdrop for early supporters!"
                analysis = await monitor.analyze_with_openai(test_content, "test_user", "test_channel")
                
                if analysis:
                    print(f"   ✅ OpenAI работает")
                    print(f"   Важность: {analysis.get('importance', 'N/A')}/10")
                    print(f"   Категория: {analysis.get('category', 'N/A')}")
                    print(f"   Резюме: {analysis.get('summary_ru', 'N/A')}")
                else:
                    print(f"   ❌ OpenAI не вернул результат")
                    
            except Exception as e:
                print(f"   ❌ Ошибка OpenAI: {e}")
        
        print(f"\n📱 Тестирование Telegram:")
        if monitor.telegram_bot_token and monitor.telegram_chat_id:
            try:
                # Тестовое сообщение
                test_message = "🧪 Тестовое сообщение от Discord Selfbot Monitor"
                telegram_url = f"https://api.telegram.org/bot{monitor.telegram_bot_token}/sendMessage"
                payload = {
                    'chat_id': monitor.telegram_chat_id,
                    'text': test_message,
                    'parse_mode': 'Markdown'
                }
                
                async with monitor.session.post(telegram_url, json=payload) as response:
                    if response.status == 200:
                        print(f"   ✅ Telegram работает")
                    else:
                        print(f"   ❌ Ошибка Telegram: {response.status}")
                        
            except Exception as e:
                print(f"   ❌ Ошибка Telegram: {e}")
        else:
            print(f"   ⚠️ Telegram не настроен")
        
        print(f"\n✅ Тестирование завершено!")
        print(f"Для запуска полного мониторинга выполните:")
        print(f"python discord_selfbot_monitor.py")
        
    finally:
        await monitor.session.close()

if __name__ == "__main__":
    asyncio.run(test_discord_selfbot()) 