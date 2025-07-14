import pytest
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from monitor import is_news_relevant_for_token


class TestImprovedNewsFiltering:
    """Тесты для улучшенной фильтрации новостей"""
    
    def test_bitcoin_news_rejected(self):
        """Тест отклонения новостей про Bitcoin"""
        news_data = {
            'title': 'Bitcoin Reaches New All-Time High',
            'description': 'Bitcoin has reached a new all-time high of $50,000'
        }
        
        # Новость про Bitcoin должна быть отклонена для всех токенов
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == False
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_ethereum_news_rejected(self):
        """Тест отклонения новостей про Ethereum"""
        news_data = {
            'title': 'Ethereum Gas Fees Drop Significantly',
            'description': 'Ethereum network fees have decreased to new lows'
        }
        
        # Новость про Ethereum должна быть отклонена
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == False
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_solana_news_rejected(self):
        """Тест отклонения новостей про Solana"""
        news_data = {
            'title': 'Solana Network Upgrade Announced',
            'description': 'Solana blockchain will receive major upgrade'
        }
        
        # Новость про Solana должна быть отклонена
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == False
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_fuel_network_news_accepted(self):
        """Тест принятия новостей про Fuel Network"""
        news_data = {
            'title': 'Fuel Network Announces Major Partnership',
            'description': 'Fuel Network has partnered with a major exchange'
        }
        
        # Новость про Fuel Network должна быть принята
        assert is_news_relevant_for_token(news_data, 'FUEL') == True
        assert is_news_relevant_for_token(news_data, 'ARC') == False
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_arc_protocol_news_accepted(self):
        """Тест принятия новостей про ARC Protocol"""
        news_data = {
            'title': 'ARC Protocol Launches New Feature',
            'description': 'ARC Protocol has launched a new staking feature'
        }
        
        # Новость про ARC Protocol должна быть принята
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == True
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_ai_rig_complex_news_accepted(self):
        """Тест принятия новостей про AI Rig Complex"""
        news_data = {
            'title': 'AI Rig Complex Announces Major Partnership',
            'description': 'AI Rig Complex has partnered with a major AI company'
        }
        
        # Новость про AI Rig Complex должна быть принята
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == True
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_ai_rig_news_accepted(self):
        """Тест принятия новостей про AI Rig"""
        news_data = {
            'title': 'AI Rig Token Launch',
            'description': 'AI Rig has launched their native token'
        }
        
        # Новость про AI Rig должна быть принята
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == True
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_rig_complex_news_accepted(self):
        """Тест принятия новостей про Rig Complex"""
        news_data = {
            'title': 'Rig Complex Network Update',
            'description': 'Rig Complex has released a major network update'
        }
        
        # Новость про Rig Complex должна быть принята
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == True
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_virtuals_protocol_news_accepted(self):
        """Тест принятия новостей про Virtuals Protocol"""
        news_data = {
            'title': 'Virtuals Protocol Token Launch',
            'description': 'Virtuals Protocol has launched their native token'
        }
        
        # Новость про Virtuals Protocol должна быть принята
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == False
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == True
    
    def test_mixed_news_rejected(self):
        """Тест отклонения новостей с запрещенными словами"""
        news_data = {
            'title': 'Bitcoin and Ethereum Market Analysis',
            'description': 'Analysis of Bitcoin and Ethereum market trends'
        }
        
        # Новость с запрещенными словами должна быть отклонена
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == False
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_general_crypto_news_rejected(self):
        """Тест отклонения общих криптовалютных новостей"""
        news_data = {
            'title': 'Crypto Market Overview',
            'description': 'General overview of cryptocurrency market trends'
        }
        
        # Общая новость без упоминания конкретных токенов должна быть отклонена
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
        assert is_news_relevant_for_token(news_data, 'ARC') == False
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_fuel_ecosystem_news_accepted(self):
        """Тест принятия новостей про Fuel ecosystem"""
        news_data = {
            'title': 'Fuel Ecosystem Expansion',
            'description': 'Fuel ecosystem continues to expand with new projects'
        }
        
        # Новость про Fuel ecosystem должна быть принята
        assert is_news_relevant_for_token(news_data, 'FUEL') == True
    
    def test_arc_ecosystem_news_accepted(self):
        """Тест принятия новостей про ARC ecosystem"""
        news_data = {
            'title': 'ARC Ecosystem Development',
            'description': 'ARC ecosystem development reaches new milestone'
        }
        
        # Новость про ARC ecosystem должна быть принята
        assert is_news_relevant_for_token(news_data, 'ARC') == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 