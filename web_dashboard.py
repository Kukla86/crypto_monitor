#!/usr/bin/env python3
"""
Веб-интерфейс для системы мониторинга криптовалют
"""

from flask import Flask, render_template, jsonify, request
import sqlite3
import json
from datetime import datetime, timedelta
import os
import asyncio
import threading
import time

app = Flask(__name__)

# Глобальная переменная для кэширования health check
health_cache = {'data': None, 'timestamp': 0, 'cache_duration': 30}

def get_db_connection():
    """Создание подключения к БД с обработкой ошибок"""
    try:
        conn = sqlite3.connect('crypto_monitor.db')
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        return None

@app.route('/')
def dashboard():
    """Главная страница дашборда"""
    return render_template('dashboard.html')

@app.route('/api/health')
def get_health_status():
    """API для получения статуса здоровья системы"""
    try:
        # Проверяем кэш
        current_time = time.time()
        if (health_cache['data'] and 
            current_time - health_cache['timestamp'] < health_cache['cache_duration']):
            return jsonify(health_cache['data'])
        
        # Импортируем monitor для health check
        import monitor
        
        # Запускаем health check в отдельном потоке
        def run_health_check():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                health_data = loop.run_until_complete(monitor.health_check())
                loop.close()
                
                # Обновляем кэш
                health_cache['data'] = health_data
                health_cache['timestamp'] = current_time
                
            except Exception as e:
                health_cache['data'] = {
                    'timestamp': datetime.now().isoformat(),
                    'overall_status': 'unhealthy',
                    'components': {},
                    'errors': [f'Health check error: {e}']
                }
                health_cache['timestamp'] = current_time
        
        # Запускаем health check в фоне
        thread = threading.Thread(target=run_health_check)
        thread.daemon = True
        thread.start()
        
        # Возвращаем кэшированные данные или базовый статус
        if health_cache['data']:
            return jsonify(health_cache['data'])
        else:
            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'overall_status': 'checking',
                'components': {},
                'errors': []
            })
            
    except Exception as e:
        return jsonify({
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'error',
            'components': {},
            'errors': [f'API error: {e}']
        })

@app.route('/api/system-stats')
def get_system_stats():
    """API для получения статистики системы"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Статистика по алертам
        cursor.execute('''
            SELECT 
                COUNT(*) as total_alerts,
                COUNT(CASE WHEN level = 'CRITICAL' THEN 1 END) as critical_alerts,
                COUNT(CASE WHEN level = 'WARNING' THEN 1 END) as warning_alerts,
                COUNT(CASE WHEN timestamp >= datetime('now', '-1 hour') THEN 1 END) as recent_alerts
            FROM alerts
        ''')
        alert_stats = cursor.fetchone()
        
        # Статистика по токенам
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT symbol) as total_tokens,
                COUNT(*) as total_records
            FROM token_data
        ''')
        token_stats = cursor.fetchone()
        
        # Статистика по real-time данным
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT symbol) as active_tokens,
                COUNT(*) as realtime_records
            FROM realtime_data
            WHERE timestamp >= datetime('now', '-1 hour')
        ''')
        realtime_stats = cursor.fetchone()
        
        # Последние обновления
        cursor.execute('''
            SELECT MAX(timestamp) as last_update
            FROM token_data
        ''')
        last_update = cursor.fetchone()
        
        conn.close()
        
        stats = {
            'alerts': {
                'total': alert_stats['total_alerts'],
                'critical': alert_stats['critical_alerts'],
                'warning': alert_stats['warning_alerts'],
                'recent_1h': alert_stats['recent_alerts']
            },
            'tokens': {
                'total': token_stats['total_tokens'],
                'records': token_stats['total_records']
            },
            'realtime': {
                'active_tokens': realtime_stats['active_tokens'],
                'records_1h': realtime_stats['realtime_records']
            },
            'last_update': last_update['last_update'],
            'uptime': get_uptime()
        }
        
        return jsonify({'success': True, 'data': stats})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def get_uptime():
    """Получение времени работы системы"""
    try:
        # Простая реализация - можно улучшить
        return "Running"
    except:
        return "Unknown"

@app.route('/api/token-data')
def get_token_data():
    """API для получения данных токенов"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получение последних данных для каждого токена
        cursor.execute('''
            SELECT symbol, price, volume_24h, tvl, social_mentions, timestamp
            FROM token_data 
            WHERE id IN (
                SELECT MAX(id) 
                FROM token_data 
                GROUP BY symbol
            )
            ORDER BY timestamp DESC
        ''')
        
        token_data = []
        for row in cursor.fetchall():
            token_data.append({
                'symbol': row['symbol'],
                'price': row['price'],
                'volume_24h': row['volume_24h'],
                'tvl': row['tvl'],
                'social_mentions': row['social_mentions'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify({'success': True, 'data': token_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/realtime-data')
def get_realtime_data():
    """API для получения real-time данных"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получение последних real-time данных
        cursor.execute('''
            SELECT symbol, price, volume_24h, price_change_24h, source, timestamp
            FROM realtime_data 
            WHERE id IN (
                SELECT MAX(id) 
                FROM realtime_data 
                GROUP BY symbol
            )
            ORDER BY timestamp DESC
        ''')
        
        realtime_data = []
        for row in cursor.fetchall():
            realtime_data.append({
                'symbol': row['symbol'],
                'price': row['price'],
                'volume_24h': row['volume_24h'],
                'price_change_24h': row['price_change_24h'],
                'source': row['source'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify({'success': True, 'data': realtime_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/alerts')
def get_alerts():
    """API для получения алертов"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получение последних алертов
        cursor.execute('''
            SELECT level, message, token_symbol, timestamp
            FROM alerts 
            ORDER BY timestamp DESC 
            LIMIT 50
        ''')
        
        alerts = []
        for row in cursor.fetchall():
            alerts.append({
                'level': row['level'],
                'message': row['message'],
                'token_symbol': row['token_symbol'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify({'success': True, 'data': alerts})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/technical-indicators')
def get_technical_indicators():
    """API для получения технических индикаторов"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получение последних технических индикаторов
        cursor.execute('''
            SELECT symbol, indicator_name, value, signal, timestamp
            FROM technical_indicators 
            WHERE id IN (
                SELECT MAX(id) 
                FROM technical_indicators 
                GROUP BY symbol, indicator_name
            )
            ORDER BY symbol, indicator_name
        ''')
        
        indicators = []
        for row in cursor.fetchall():
            indicators.append({
                'symbol': row['symbol'],
                'indicator_name': row['indicator_name'],
                'value': row['value'],
                'signal': row['signal'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify({'success': True, 'data': indicators})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/price-history')
def get_price_history():
    """API для получения истории цен"""
    try:
        symbol = request.args.get('symbol', 'FUEL')
        hours = int(request.args.get('hours', 24))
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получение истории цен за последние N часов
        cursor.execute('''
            SELECT price, volume_24h, timestamp
            FROM token_data 
            WHERE symbol = ? 
            AND timestamp >= datetime('now', '-{} hours')
            ORDER BY timestamp ASC
        '''.format(hours), (symbol,))
        
        price_history = []
        for row in cursor.fetchall():
            price_history.append({
                'price': row['price'],
                'volume': row['volume_24h'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify({'success': True, 'data': price_history})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/volume-data')
def get_volume_data():
    """API для получения данных по объему торгов"""
    try:
        hours = int(request.args.get('hours', 24))
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получение данных по объему за последние N часов
        cursor.execute('''
            SELECT symbol, volume_24h, timestamp
            FROM token_data 
            WHERE timestamp >= datetime('now', '-{} hours')
            ORDER BY symbol, timestamp ASC
        '''.format(hours))
        
        volume_data = {}
        for row in cursor.fetchall():
            symbol = row['symbol']
            if symbol not in volume_data:
                volume_data[symbol] = []
            
            volume_data[symbol].append({
                'volume': row['volume_24h'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify({'success': True, 'data': volume_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/error-stats')
def get_error_stats():
    """API для получения статистики ошибок"""
    try:
        # Импортируем error_handler для получения статистики
        try:
            from error_handler import error_handler
            stats = error_handler.get_stats()
            return jsonify({'success': True, 'data': stats})
        except ImportError:
            return jsonify({
                'success': True, 
                'data': {
                    'total_errors': 0,
                    'retryable_errors': 0,
                    'critical_errors': 0,
                    'api_errors': 0,
                    'network_errors': 0,
                    'database_errors': 0,
                    'last_error_time': None,
                    'recent_errors': []
                }
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/portfolio')
def get_portfolio_data():
    """API для получения данных портфеля"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получение последних данных портфеля
        cursor.execute('''
            SELECT symbol, amount, current_price, current_value, price_change_24h, 
                   value_change_24h, percentage_of_portfolio, timestamp
            FROM portfolio_tracking 
            WHERE id IN (
                SELECT MAX(id) 
                FROM portfolio_tracking 
                GROUP BY symbol
            )
            ORDER BY current_value DESC
        ''')
        
        portfolio_data = []
        for row in cursor.fetchall():
            portfolio_data.append({
                'symbol': row['symbol'],
                'amount': row['amount'],
                'current_price': row['current_price'],
                'current_value': row['current_value'],
                'price_change_24h': row['price_change_24h'],
                'value_change_24h': row['value_change_24h'],
                'percentage_of_portfolio': row['percentage_of_portfolio'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify({'success': True, 'data': portfolio_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/portfolio/history')
def get_portfolio_history():
    """API для получения истории портфеля"""
    try:
        symbol = request.args.get('symbol', 'FUEL')
        days = int(request.args.get('days', 7))
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получение истории портфеля
        cursor.execute('''
            SELECT current_value, price_change_24h, timestamp
            FROM portfolio_tracking 
            WHERE symbol = ? 
            AND timestamp >= datetime('now', '-{} days')
            ORDER BY timestamp ASC
        '''.format(days), (symbol,))
        
        history_data = []
        for row in cursor.fetchall():
            history_data.append({
                'value': row['current_value'],
                'change': row['price_change_24h'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        return jsonify({'success': True, 'data': history_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/portfolio/update', methods=['POST'])
def update_portfolio():
    """API для обновления портфеля"""
    try:
        data = request.get_json()
        if not data or 'portfolio' not in data:
            return jsonify({'success': False, 'error': 'Portfolio data required'})
        
        # Импортируем monitor для трекинга портфеля
        import asyncio
        import monitor
        
        # Запускаем трекинг портфеля
        def run_portfolio_tracking():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(monitor.track_portfolio(data['portfolio']))
                loop.close()
                return result
            except Exception as e:
                return {'error': str(e)}
        
        # Запускаем в отдельном потоке
        import threading
        thread = threading.Thread(target=run_portfolio_tracking)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': 'Portfolio tracking started'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/news')
def get_news():
    """API для получения новостей"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        # Получаем последние новости из social_alerts
        cursor.execute('''
            SELECT timestamp, source, level, original_text, translated_text, 
                   link, token, keywords, important_news
            FROM social_alerts 
            WHERE source = 'news_analysis'
            ORDER BY timestamp DESC
            LIMIT 20
        ''')
        
        news_items = []
        for row in cursor.fetchall():
            news_items.append({
                'timestamp': row['timestamp'],
                'source': row['source'],
                'level': row['level'],
                'title': row['original_text'],
                'title': row['original_text'],
                'description': row['translated_text'],
                'link': row['link'],
                'token': row['token'],
                'keywords': json.loads(row['keywords']) if row['keywords'] else [],
                'important': bool(row['important_news'])
            })
        
        conn.close()
        
        return jsonify({'success': True, 'data': news_items})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/news/trends')
def get_news_trends():
    """API для получения трендов новостей"""
    try:
        symbol = request.args.get('symbol', 'FUEL')
        days = int(request.args.get('days', 7))
        
        # Запускаем анализ трендов в отдельном потоке
        def run_trends_analysis():
            try:
                import monitor
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                trends = loop.run_until_complete(monitor.analyze_news_trends(symbol, days))
                loop.close()
                print(f"News trends for {symbol}: {trends}")
            except Exception as e:
                print(f"News trends analysis error: {e}")
        
        thread = threading.Thread(target=run_trends_analysis)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': 'Trends analysis started'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/news/fetch', methods=['POST'])
def fetch_latest_news():
    """API для принудительного получения новостей"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'FUEL')
        
        # Запускаем получение новостей в отдельном потоке
        def run_news_fetch():
            try:
                import monitor
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                news_items = loop.run_until_complete(monitor.fetch_crypto_news(symbol))
                loop.close()
                print(f"Fetched {len(news_items)} news items for {symbol}")
            except Exception as e:
                print(f"News fetch error: {e}")
        
        thread = threading.Thread(target=run_news_fetch)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': f'News fetch started for {symbol}'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.errorhandler(404)
def not_found(error):
    """Обработка 404 ошибок"""
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Обработка 500 ошибок"""
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 