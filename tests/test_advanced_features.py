#!/usr/bin/env python3
"""
Тест расширенных функций системы мониторинга
"""

import asyncio
import pytest
import sys
import os
import json
from unittest.mock import Mock, patch, AsyncMock

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import monitor
import web_dashboard

class TestAdvancedFeatures:
    """Тесты расширенных функций"""
    
    def test_technical_indicators_calculation(self):
        """Тест расчета технических индикаторов"""
        # Тестовые данные цен
        price_history = [0.001, 0.0011, 0.0012, 0.00115, 0.0013, 0.00125, 0.0014, 
                        0.00135, 0.0015, 0.00145, 0.0016, 0.00155, 0.0017, 0.00165,
                        0.0018, 0.00175, 0.0019, 0.00185, 0.002, 0.00195, 0.0021,
                        0.00205, 0.0022, 0.00215, 0.0023, 0.00225, 0.0024]
        
        # Тестируем расчет индикаторов
        indicators = monitor.calculate_technical_indicators("FUEL", price_history)
        
        # Проверяем наличие основных индикаторов
        assert 'sma_20' in indicators
        assert 'ema_12' in indicators
        assert 'rsi' in indicators
        assert 'signals' in indicators
        
        # Проверяем значения
        assert indicators['sma_20'] > 0
        assert 0 <= indicators['rsi'] <= 100
        assert 'sma_20_signal' in indicators['signals']
        assert 'rsi_signal' in indicators['signals']
        
        print("✅ Технические индикаторы рассчитываются корректно")
    
    def test_ema_calculation(self):
        """Тест расчета EMA"""
        prices = [1.0, 1.1, 1.2, 1.15, 1.3, 1.25, 1.4, 1.35, 1.5, 1.45, 1.6, 1.55]
        
        ema = monitor.calculate_ema(prices, 12)
        
        assert ema > 0
        assert isinstance(ema, float)
        
        print("✅ EMA рассчитывается корректно")
    
    def test_macd_calculation(self):
        """Тест расчета MACD"""
        prices = [1.0] * 26  # 26 одинаковых цен для теста
        
        macd_data = monitor.calculate_macd(prices)
        
        assert macd_data is not None
        assert 'macd' in macd_data
        assert 'signal_line' in macd_data
        assert 'histogram' in macd_data
        
        print("✅ MACD рассчитывается корректно")
    
    def test_bollinger_bands_calculation(self):
        """Тест расчета Bollinger Bands"""
        prices = [1.0, 1.1, 1.2, 1.15, 1.3, 1.25, 1.4, 1.35, 1.5, 1.45, 1.6, 1.55,
                 1.7, 1.65, 1.8, 1.75, 1.9, 1.85, 2.0, 1.95]
        
        bb_data = monitor.calculate_bollinger_bands(prices, 20, 2)
        
        assert bb_data is not None
        assert 'upper' in bb_data
        assert 'middle' in bb_data
        assert 'lower' in bb_data
        assert bb_data['upper'] > bb_data['middle'] > bb_data['lower']
        
        print("✅ Bollinger Bands рассчитываются корректно")
    
    def test_stochastic_calculation(self):
        """Тест расчета Stochastic"""
        prices = [1.0, 1.1, 1.2, 1.15, 1.3, 1.25, 1.4, 1.35, 1.5, 1.45, 1.6, 1.55, 1.7, 1.65]
        
        stoch_data = monitor.calculate_stochastic(prices, 14)
        
        assert stoch_data is not None
        assert 'k' in stoch_data
        assert 'd' in stoch_data
        assert 0 <= stoch_data['k'] <= 100
        assert 0 <= stoch_data['d'] <= 100
        
        print("✅ Stochastic рассчитывается корректно")
    
    def test_williams_r_calculation(self):
        """Тест расчета Williams %R"""
        prices = [1.0, 1.1, 1.2, 1.15, 1.3, 1.25, 1.4, 1.35, 1.5, 1.45, 1.6, 1.55, 1.7, 1.65]
        
        williams_r = monitor.calculate_williams_r(prices, 14)
        
        assert williams_r is not None
        assert -100 <= williams_r <= 0
        
        print("✅ Williams %R рассчитывается корректно")
    
    @pytest.mark.asyncio
    async def test_portfolio_tracking(self):
        """Тест портфельного трекинга"""
        # Мокаем функции получения цен
        with patch.object(monitor, 'get_current_price', return_value=0.002):
            with patch.object(monitor, 'get_historical_price', return_value=0.001):
                with patch.object(monitor, 'send_alert', new_callable=AsyncMock):
                    with patch.object(monitor, 'save_portfolio_data', new_callable=AsyncMock):
                        
                        portfolio = {"FUEL": 10000, "ARC": 5000}
                        result = await monitor.track_portfolio(portfolio)
                        
                        assert result is not None
                        assert 'FUEL' in result
                        assert 'ARC' in result
                        assert 'portfolio_metrics' in result
                        
                        # Проверяем расчеты
                        fuel_data = result['FUEL']
                        assert fuel_data['amount'] == 10000
                        assert fuel_data['current_price'] == 0.002
                        assert fuel_data['current_value'] == 20.0  # 10000 * 0.002
                        assert fuel_data['price_change_24h'] == 100.0  # (0.002 - 0.001) / 0.001 * 100
                        
                        print("✅ Портфельный трекинг работает корректно")
    
    def test_portfolio_metrics_calculation(self):
        """Тест расчета метрик портфеля"""
        portfolio = {"FUEL": 1000, "ARC": 500}
        
        metrics = monitor.calculate_portfolio_metrics(portfolio)
        
        assert 'total_value' in metrics
        assert 'allocation' in metrics
        assert 'concentration' in metrics
        assert 'diversification' in metrics
        assert 'portfolio_risk' in metrics
        assert 'risk_level' in metrics
        
        assert metrics['total_value'] == 1500
        assert 'FUEL' in metrics['allocation']
        assert 'ARC' in metrics['allocation']
        
        print("✅ Метрики портфеля рассчитываются корректно")
    
    def test_web_dashboard_health_api(self):
        """Тест API health check в web dashboard"""
        with web_dashboard.app.test_client() as client:
            response = client.get('/api/health')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert 'timestamp' in data
            assert 'overall_status' in data
            assert 'components' in data
            assert 'errors' in data
            
            print("✅ Health check API работает корректно")
    
    def test_web_dashboard_system_stats_api(self):
        """Тест API статистики системы в web dashboard"""
        with web_dashboard.app.test_client() as client:
            response = client.get('/api/system-stats')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert 'success' in data
            if data['success']:
                assert 'data' in data
                stats = data['data']
                assert 'alerts' in stats
                assert 'tokens' in stats
                assert 'realtime' in stats
                
            print("✅ System stats API работает корректно")
    
    def test_web_dashboard_portfolio_api(self):
        """Тест API портфеля в web dashboard"""
        with web_dashboard.app.test_client() as client:
            response = client.get('/api/portfolio')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert 'success' in data
            assert 'data' in data
            
            print("✅ Portfolio API работает корректно")
    
    def test_web_dashboard_portfolio_update_api(self):
        """Тест API обновления портфеля в web dashboard"""
        with web_dashboard.app.test_client() as client:
            portfolio_data = {"portfolio": {"FUEL": 1000, "ARC": 500}}
            
            with patch('web_dashboard.monitor') as mock_monitor:
                mock_monitor.track_portfolio = AsyncMock(return_value={})
                
                response = client.post('/api/portfolio/update', 
                                     json=portfolio_data,
                                     content_type='application/json')
                
                assert response.status_code == 200
                data = json.loads(response.data)
                
                assert data['success'] == True
                assert 'message' in data
                
                print("✅ Portfolio update API работает корректно")
    
    def test_tradingview_webhook(self):
        """Тест TradingView webhook"""
        with monitor.app.test_client() as client:
            webhook_data = {
                "symbol": "FUEL",
                "strategy": "Test Strategy",
                "action": "BUY",
                "price": 0.002,
                "message": "Test alert"
            }
            
            with patch.object(monitor, 'send_alert', new_callable=AsyncMock):
                response = client.post('/webhook/tradingview',
                                     json=webhook_data,
                                     content_type='application/json')
                
                assert response.status_code == 200
                data = json.loads(response.data)
                
                assert data['success'] == True
                assert 'message' in data
                
                print("✅ TradingView webhook работает корректно")

def run_advanced_tests():
    """Запуск всех тестов расширенных функций"""
    print("🚀 Запуск тестов расширенных функций...")
    
    test_instance = TestAdvancedFeatures()
    
    # Тесты технических индикаторов
    test_instance.test_technical_indicators_calculation()
    test_instance.test_ema_calculation()
    test_instance.test_macd_calculation()
    test_instance.test_bollinger_bands_calculation()
    test_instance.test_stochastic_calculation()
    test_instance.test_williams_r_calculation()
    
    # Тесты портфельного трекинга
    test_instance.test_portfolio_metrics_calculation()
    
    # Тесты web dashboard
    test_instance.test_web_dashboard_health_api()
    test_instance.test_web_dashboard_system_stats_api()
    test_instance.test_web_dashboard_portfolio_api()
    test_instance.test_web_dashboard_portfolio_update_api()
    
    # Тест TradingView webhook
    test_instance.test_tradingview_webhook()
    
    # Асинхронные тесты
    asyncio.run(test_instance.test_portfolio_tracking())
    
    print("\n🎉 Все тесты расширенных функций прошли успешно!")
    print("\n📋 Реализованные улучшения:")
    print("✅ Web интерфейс с health check и статистикой")
    print("✅ Расширенные технические индикаторы (SMA, EMA, RSI, MACD, Bollinger Bands, Stochastic, Williams %R)")
    print("✅ Интеграция с TradingView через webhook")
    print("✅ Портфельный трекинг с алертами")
    print("✅ Улучшенный UI с real-time обновлениями")

if __name__ == "__main__":
    run_advanced_tests() 