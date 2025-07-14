#!/bin/bash

echo "🔧 Установка зависимостей для социального мониторинга..."

echo "✅ Twitter API заблокирован. Используем Nitter RSS для получения твитов."

# Установка остальных зависимостей
pip3 install -r requirements.txt

echo "✅ Установка завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Настройте TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE в config.env"
echo "2. Настройте DISCORD_BOT_TOKEN в config.env"
echo "3. Запустите систему мониторинга: python3 monitor.py" 
echo "⚠️ Twitter API заблокирован. Используем Nitter RSS для получения твитов."