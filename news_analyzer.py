#!/usr/bin/env python3
"""
AI-Based Crypto News Analyzer — With Impact Filtering
Анализатор крипто-новостей с AI-фильтрацией по важности
"""

import asyncio
import json
import logging
import os
import openai
from typing import Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv('config.env')

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

class NewsAnalyzer:
    """AI-анализатор крипто-новостей с фильтрацией по важности"""
    
    def __init__(self):
        self.prompt_template = """
You are a crypto analyst. For the news below, return JSON with:
{
  'summary': 'brief human-readable summary',
  'impact': 'high | medium | low | none',
  'reason': 'why this impact level was selected',
  'action_required': true/false,
  'skip': true/false
}

🔴 Impact = "high" if:
- Token listing or delisting (CEX or DEX)
- Major hack, exploit, regulation news
- Mainnet, testnet, launch announcement
- Airdrop confirmation or claim phase
- Role or early access information (e.g. Discord OG / Whitelist)
- NFT mint or NFT-related announcement (initial drop or collection launch)
- Fundraising round (seed / private / Series A+)
- Large whale movement or liquidity unlock
- Public product launch or roadmap milestone

🟡 Impact = "medium" if:
- AMA events, interviews with founders
- Minor partnerships
- Project joins hackathon, minor integrations
- Blog posts with indirect news
- Updates to product or UI

⚪ Impact = "low" or "none" if:
- Market recap or price commentary
- Generic influencer tweets / community memes
- No actionable or novel info
- Repeat posts with no change
- Unverified rumors or hype

News to analyze:
{news_text}

Only output valid JSON, no extra text.
"""
    
    async def analyze_news(self, news_text: str, source: str = "unknown") -> Dict[str, Any]:
        """
        Анализирует новость с помощью AI и возвращает структурированный результат
        
        Args:
            news_text: Текст новости для анализа
            source: Источник новости (telegram, twitter, rss, etc.)
            
        Returns:
            Dict с результатами анализа или None если AI недоступен
        """
        try:
            if not OPENAI_API_KEY:
                logger.warning("OpenAI API ключ не настроен")
                await self._send_ai_unavailable_alert("OpenAI API ключ не настроен")
                return None
            
            # Подготавливаем промпт
            prompt = self.prompt_template.format(news_text=news_text[:2000])  # Ограничиваем длину
            
            # Вызываем OpenAI API
            response = await openai.ChatCompletion.acreate(
                model="gpt-4o-mini",  # Используем более быструю модель
                messages=[
                    {"role": "system", "content": "You are a crypto news analyst. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Низкая температура для консистентности
                max_tokens=500
            )
            
            # Парсим ответ
            ai_response = response.choices[0].message.content.strip()
            
            # Извлекаем JSON из ответа
            json_start = ai_response.find('{')
            json_end = ai_response.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = ai_response[json_start:json_end]
                result = json.loads(json_str)
                
                # Добавляем метаданные
                result['source'] = source
                result['analyzed_at'] = datetime.now().isoformat()
                result['ai_model'] = 'gpt-4o-mini'
                
                logger.info(f"AI анализ завершен: {result['impact']} - {result['summary'][:50]}...")
                return result
            else:
                logger.error(f"Не удалось извлечь JSON из ответа AI: {ai_response}")
                await self._send_ai_unavailable_alert("Не удалось извлечь JSON из ответа AI")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от AI: {e}")
            await self._send_ai_unavailable_alert(f"Ошибка парсинга JSON от AI: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка AI анализа: {e}")
            await self._send_ai_unavailable_alert(f"Ошибка AI анализа: {e}")
            return None
    
    async def _send_ai_unavailable_alert(self, error_message: str):
        """
        Отправляет алерт в Telegram о недоступности AI
        """
        try:
            # Импортируем send_alert из monitor.py
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            
            # Динамический импорт чтобы избежать циклических зависимостей
            try:
                from monitor import send_alert
                
                alert_message = f"""🤖 AI АНАЛИЗ НЕДОСТУПЕН

❌ Ошибка: {error_message}

⚠️ Новости не будут обрабатываться без AI-анализа
🔧 Проверьте настройки OpenAI API

⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

                await send_alert('CRITICAL', alert_message)
                logger.info("Отправлен алерт о недоступности AI")
                
            except ImportError:
                logger.error("Не удалось импортировать send_alert из monitor.py")
                
        except Exception as e:
            logger.error(f"Ошибка отправки алерта о недоступности AI: {e}")
    
    def _fallback_analysis(self, news_text: str, source: str) -> Dict[str, Any]:
        """
        Fallback анализ без AI - ПРОСТЫЕ ПРАВИЛА (ОТКЛЮЧЕН)
        """
        # Этот метод больше не используется, но оставляем для совместимости
        logger.warning("Fallback анализ отключен - новости не будут обрабатываться без AI")
        return None
    
    def should_send_alert(self, analysis: Dict[str, Any]) -> bool:
        """
        Определяет, нужно ли отправлять алерт на основе анализа
        
        Args:
            analysis: Результат анализа новости (может быть None)
            
        Returns:
            True если нужно отправить алерт
        """
        if analysis is None:
            return False
            
        return (
            not analysis.get('skip', False) and 
            analysis.get('action_required', False) and
            analysis.get('impact') in ['high', 'medium']
        )
    
    def get_alert_level(self, analysis: Dict[str, Any]) -> str:
        """
        Определяет уровень алерта на основе анализа
        
        Args:
            analysis: Результат анализа новости (может быть None)
            
        Returns:
            Уровень алерта: 'high', 'medium', 'low'
        """
        if analysis is None:
            return 'low'
            
        impact = analysis.get('impact', 'low')
        
        if impact == 'high':
            return 'high'
        elif impact == 'medium':
            return 'medium'
        else:
            return 'low'
    
    def format_alert_message(self, analysis: Dict[str, Any], original_text: str) -> str:
        """
        Форматирует сообщение алерта на основе анализа
        
        Args:
            analysis: Результат анализа новости (может быть None)
            original_text: Оригинальный текст новости
            
        Returns:
            Отформатированное сообщение для алерта
        """
        if analysis is None:
            return f"""❌ НОВОСТЬ НЕ ОБРАБОТАНА

🤖 AI анализ недоступен
📄 Оригинал: {original_text[:200]}{'...' if len(original_text) > 200 else ''}"""
        
        impact = analysis.get('impact', 'low')
        summary = analysis.get('summary', '')
        reason = analysis.get('reason', '')
        source = analysis.get('source', 'unknown')
        
        # Определяем эмодзи и тег для уровня важности
        if impact == 'high':
            emoji = "🚨"
            tag = "[🚨 СРОЧНО]"
        elif impact == 'medium':
            emoji = "⚠️"
            tag = "[⚠️ ВАЖНО]"
        else:
            emoji = "ℹ️"
            tag = "[ℹ️ ИНФО]"
        
        message = f"""
{tag} {emoji} НОВОСТЬ {emoji}

📰 {summary}

🔍 Причина важности: {reason}
📡 Источник: {source}

📄 Оригинал:
{original_text[:300]}{'...' if len(original_text) > 300 else ''}
"""
        return message.strip()

# Глобальный экземпляр анализатора
news_analyzer = NewsAnalyzer()

async def analyze_crypto_news(news_text: str, source: str = "unknown") -> Dict[str, Any]:
    """
    Удобная функция для анализа крипто-новостей
    
    Args:
        news_text: Текст новости
        source: Источник новости
        
    Returns:
        Результат анализа
    """
    return await news_analyzer.analyze_news(news_text, source)

async def should_alert_news(analysis: Dict[str, Any]) -> bool:
    """
    Проверяет, нужно ли отправлять алерт для новости
    
    Args:
        analysis: Результат анализа новости
        
    Returns:
        True если нужно отправить алерт
    """
    return news_analyzer.should_send_alert(analysis)

async def format_news_alert(analysis: Dict[str, Any], original_text: str) -> str:
    """
    Форматирует алерт для новости
    
    Args:
        analysis: Результат анализа новости
        original_text: Оригинальный текст новости
        
    Returns:
        Отформатированное сообщение алерта
    """
    return news_analyzer.format_alert_message(analysis, original_text)

# Тестовая функция
async def test_news_analyzer():
    """Тестирует анализатор новостей"""
    test_news = [
        {
            "text": "🚀 FUEL Network announces mainnet launch on March 15th! Get ready for the future of modular blockchains.",
            "source": "telegram"
        },
        {
            "text": "Just checked the price of ARC, looking good today! 📈",
            "source": "twitter"
        },
        {
            "text": "Breaking: Major hack detected on DeFi protocol. $50M stolen from liquidity pools.",
            "source": "rss"
        },
        {
            "text": "Join our AMA with the FUEL team tomorrow at 3 PM UTC!",
            "source": "discord"
        }
    ]
    
    print("🧪 ТЕСТИРОВАНИЕ AI АНАЛИЗАТОРА НОВОСТЕЙ")
    print("=" * 50)
    
    for i, news in enumerate(test_news, 1):
        print(f"\n📰 Тест {i}: {news['source'].upper()}")
        print(f"Текст: {news['text']}")
        
        analysis = await analyze_crypto_news(news['text'], news['source'])
        
        print(f"📊 Результат анализа:")
        print(f"  • Важность: {analysis['impact']}")
        print(f"  • Резюме: {analysis['summary']}")
        print(f"  • Причина: {analysis['reason']}")
        print(f"  • Требует действия: {analysis['action_required']}")
        print(f"  • Пропустить: {analysis['skip']}")
        print(f"  • Отправить алерт: {await should_alert_news(analysis)}")
        
        if await should_alert_news(analysis):
            alert_message = await format_news_alert(analysis, news['text'])
            print(f"  • Сообщение алерта:\n{alert_message}")

if __name__ == "__main__":
    asyncio.run(test_news_analyzer()) 