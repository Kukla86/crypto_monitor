#!/usr/bin/env python3
"""
Скрипт для проверки зависимостей проекта
Проверяет наличие всех необходимых модулей
"""

import sys
import importlib
from typing import List, Dict, Tuple

def check_module(module_name: str, package_name: str = None) -> Tuple[bool, str]:
    """Проверяет наличие модуля"""
    try:
        importlib.import_module(module_name)
        return True, f"✅ {package_name or module_name}"
    except ImportError as e:
        return False, f"❌ {package_name or module_name}: {e}"

def main():
    """Основная функция проверки зависимостей"""
    print("🔍 Проверка зависимостей проекта...\n")
    
    # Список основных зависимостей
    dependencies = [
        ("aiohttp", "aiohttp"),
        ("requests", "requests"),
        ("asyncio", "asyncio"),
        ("websockets", "websockets"),
        ("sqlite3", "sqlite3"),
        ("yaml", "PyYAML"),
        ("json", "json"),
        ("os", "os"),
        ("logging", "logging"),
        ("datetime", "datetime"),
        ("typing", "typing"),
        ("time", "time"),
        ("random", "random"),
        ("threading", "threading"),
        ("collections", "collections"),
        ("telethon", "telethon"),
        ("discord", "discord.py"),
        ("subprocess", "subprocess"),
        ("sys", "sys"),
        ("hashlib", "hashlib"),
        ("openai", "openai"),
        ("xml.etree.ElementTree", "xml"),
        ("re", "re"),
        ("bs4", "beautifulsoup4"),
        ("flask", "Flask"),
        ("dotenv", "python-dotenv"),
        ("cachetools", "cachetools"),
        ("redis", "redis"),
        ("pandas", "pandas"),
        ("matplotlib", "matplotlib"),
        ("numpy", "numpy"),
        ("plotly", "plotly"),
        ("sklearn", "scikit-learn"),
        ("scipy", "scipy"),
        ("tweepy", "tweepy"),
        ("snscrape", "snscrape"),
        ("transformers", "transformers"),
        ("torch", "torch"),
        ("nltk", "nltk"),
        ("textblob", "textblob"),
        ("lxml", "lxml"),
        ("feedparser", "feedparser"),
        ("selenium", "selenium"),
        ("playwright", "playwright"),
        ("cryptography", "cryptography"),
        ("bcrypt", "bcrypt"),
        ("structlog", "structlog"),
        ("prometheus_client", "prometheus-client"),
        ("pytest", "pytest"),
        ("pytest_asyncio", "pytest-asyncio"),
        ("pytest_cov", "pytest-cov"),
        ("click", "click"),
        ("rich", "rich"),
        ("tqdm", "tqdm"),
        ("colorama", "colorama"),
        ("ccxt", "ccxt"),
        ("psutil", "psutil"),
        ("cpuinfo", "py-cpuinfo"),
        ("sphinx", "sphinx"),
    ]
    
    results = []
    all_passed = True
    
    for module_name, package_name in dependencies:
        success, message = check_module(module_name, package_name)
        results.append((success, message))
        if not success:
            all_passed = False
    
    # Выводим результаты
    print("📋 Результаты проверки:\n")
    for success, message in results:
        print(message)
    
    print(f"\n{'='*50}")
    if all_passed:
        print("🎉 Все зависимости установлены корректно!")
        return 0
    else:
        print("⚠️  Некоторые зависимости отсутствуют. Установите их командой:")
        print("   pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 