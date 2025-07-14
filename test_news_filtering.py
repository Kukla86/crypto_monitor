import pytest
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from monitor import is_news_relevant_for_token


class TestNewsFiltering:
    """Тесты для фильтрации новостей по токенам"""
    
    def test_fuel_relevant_news(self):
        """Тест релевантных новостей для FUEL"""
        news_data = {
            'title': 'FUEL Network Announces Major Partnership',
            'description': 'The FUEL protocol has partnered with a major exchange'
        }
        
        assert is_news_relevant_for_token(news_data, 'FUEL') == True
    
    def test_fuel_irrelevant_news(self):
        """Тест нерелевантных новостей для FUEL"""
        news_data = {
            'title': 'Bitcoin Reaches New High',
            'description': 'Bitcoin has reached a new all-time high'
        }
        
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
    
    def test_arc_relevant_news(self):
        """Тест релевантных новостей для ARC"""
        news_data = {
            'title': 'ARC Protocol Update Released',
            'description': 'New features added to ARC blockchain'
        }
        
        assert is_news_relevant_for_token(news_data, 'ARC') == True
    
    def test_arc_irrelevant_news(self):
        """Тест нерелевантных новостей для ARC"""
        news_data = {
            'title': 'Ethereum Gas Fees Drop',
            'description': 'Ethereum network fees have decreased significantly'
        }
        
        assert is_news_relevant_for_token(news_data, 'ARC') == False
    
    def test_virtual_relevant_news(self):
        """Тест релевантных новостей для VIRTUAL"""
        news_data = {
            'title': 'Virtuals Protocol Launches New Feature',
            'description': 'Virtual token holders can now stake their tokens'
        }
        
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == True
    
    def test_virtual_irrelevant_news(self):
        """Тест нерелевантных новостей для VIRTUAL"""
        news_data = {
            'title': 'Solana Network Upgrade',
            'description': 'Solana blockchain receives major upgrade'
        }
        
        assert is_news_relevant_for_token(news_data, 'VIRTUAL') == False
    
    def test_case_insensitive_matching(self):
        """Тест нечувствительности к регистру"""
        news_data = {
            'title': 'Fuel Network Update',
            'description': 'The fuel protocol has been updated'
        }
        
        assert is_news_relevant_for_token(news_data, 'FUEL') == True
    
    def test_partial_word_matching(self):
        """Тест частичного совпадения слов"""
        news_data = {
            'title': 'Fueling the Future of DeFi',
            'description': 'New protocol aims to fuel the DeFi ecosystem'
        }
        
        # Должно найти "fuel" в "Fueling"
        assert is_news_relevant_for_token(news_data, 'FUEL') == True
    
    def test_empty_news_data(self):
        """Тест пустых данных новости"""
        news_data = {}
        
        assert is_news_relevant_for_token(news_data, 'FUEL') == False
    
    def test_unknown_token(self):
        """Тест неизвестного токена"""
        news_data = {
            'title': 'Some Random News',
            'description': 'Random description'
        }
        
        # Для неизвестного токена должно искать только название токена
        assert is_news_relevant_for_token(news_data, 'UNKNOWN') == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 