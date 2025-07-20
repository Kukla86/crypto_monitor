#!/usr/bin/env python3
"""
Веб-интерфейс для системы мониторинга криптовалют
Предоставляет API эндпоинты и веб-страницы для управления системой
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import sqlite3
import asyncio
import threading
from pathlib import Path

# Импорты из нашего проекта
try:
    from config_manager import get_config_manager
    from cache_manager import get_cache_manager, get_cache_stats
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

try:
    from monitor import realtime_data, get_token_summary, get_market_overview
    MONITOR_AVAILABLE = True
except ImportError:
    MONITOR_AVAILABLE = False

# Настройка Flask приложения
app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные
config_manager = None
cache_manager = None

def init_managers():
    """Инициализация менеджеров"""
    global config_manager, cache_manager
    
    if CONFIG_AVAILABLE:
        try:
            config_manager = get_config_manager()
            logger.info("Config manager инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации config manager: {e}")
    
    if 'cache_manager' in globals():
        try:
            cache_manager = get_cache_manager()
            logger.info("Cache manager инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации cache manager: {e}")

# Инициализируем менеджеры при запуске
init_managers()

def get_db_connection():
    """Получение соединения с базой данных"""
    try:
        db_path = 'crypto_monitor.db'
        if config_manager:
            db_path = config_manager.get_api_key('database_path') or db_path
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None

# API эндпоинты

@app.route('/api/status')
def api_status():
    """Статус системы"""
    try:
        status = {
            'status': 'running',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0',
            'config_available': CONFIG_AVAILABLE,
            'monitor_available': MONITOR_AVAILABLE,
            'uptime': '00:00:00'  # TODO: добавить расчет uptime
        }
        
        # Добавляем информацию о менеджерах
        if config_manager:
            status['config_manager'] = 'active'
            status['config_summary'] = config_manager.get_config_summary()
        else:
            status['config_manager'] = 'inactive'
        
        if cache_manager:
            status['cache_manager'] = 'active'
            status['cache_stats'] = get_cache_stats()
        else:
            status['cache_manager'] = 'inactive'
        
        return jsonify(status)
    
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tokens')
def api_tokens():
    """Список токенов"""
    try:
        if not config_manager:
            return jsonify({'error': 'Config manager недоступен'}), 500
        
        tokens = config_manager.combined_config.get('tokens', {})
        return jsonify({
            'tokens': tokens,
            'count': len(tokens)
        })
    
    except Exception as e:
        logger.error(f"Ошибка получения токенов: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tokens/<symbol>')
def api_token_info(symbol):
    """Информация о конкретном токене"""
    try:
        if not config_manager:
            return jsonify({'error': 'Config manager недоступен'}), 500
        
        token_config = config_manager.get_token_config(symbol.upper())
        if not token_config:
            return jsonify({'error': f'Токен {symbol} не найден'}), 404
        
        # Добавляем realtime данные если доступны
        if MONITOR_AVAILABLE:
            try:
                realtime_info = realtime_data.get(symbol.upper(), {})
                token_config['realtime'] = realtime_info
            except Exception as e:
                logger.warning(f"Не удалось получить realtime данные для {symbol}: {e}")
        
        return jsonify(token_config)
    
    except Exception as e:
        logger.error(f"Ошибка получения информации о токене {symbol}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts')
def api_alerts():
    """Список алертов"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Не удалось подключиться к БД'}), 500
        
        # Получаем последние алерты
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM alerts 
            ORDER BY timestamp DESC 
            LIMIT 100
        """)
        
        alerts = []
        for row in cursor.fetchall():
            alerts.append(dict(row))
        
        conn.close()
        
        return jsonify({
            'alerts': alerts,
            'count': len(alerts)
        })
    
    except Exception as e:
        logger.error(f"Ошибка получения алертов: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config')
def api_config():
    """Конфигурация системы"""
    try:
        if not config_manager:
            return jsonify({'error': 'Config manager недоступен'}), 500
        
        return jsonify({
            'sources': config_manager.combined_config.get('sources', {}),
            'monitoring': config_manager.combined_config.get('monitoring', {}),
            'api_keys': {k: '***' if v else None for k, v in config_manager.combined_config.get('api_keys', {}).items()}
        })
    
    except Exception as e:
        logger.error(f"Ошибка получения конфигурации: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache')
def api_cache():
    """Статистика кэша"""
    try:
        if not cache_manager:
            return jsonify({'error': 'Cache manager недоступен'}), 500
        
        stats = get_cache_stats()
        cache_names = cache_manager.get_cache_names()
        
        return jsonify({
            'stats': stats,
            'cache_names': cache_names,
            'total_caches': len(cache_names)
        })
    
    except Exception as e:
        logger.error(f"Ошибка получения статистики кэша: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/<cache_name>/clear', methods=['POST'])
def api_clear_cache(cache_name):
    """Очистка конкретного кэша"""
    try:
        if not cache_manager:
            return jsonify({'error': 'Cache manager недоступен'}), 500
        
        cache_manager.clear_cache(cache_name)
        
        return jsonify({
            'message': f'Кэш {cache_name} очищен',
            'cache_name': cache_name
        })
    
    except Exception as e:
        logger.error(f"Ошибка очистки кэша {cache_name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sources')
def api_sources():
    """Список источников данных"""
    try:
        if not config_manager:
            return jsonify({'error': 'Config manager недоступен'}), 500
        
        sources = config_manager.combined_config.get('sources', {})
        
        # Добавляем статистику по типам источников
        source_stats = {}
        for source_type, source_list in sources.items():
            enabled_count = len(config_manager.get_enabled_sources(source_type))
            total_count = len(source_list)
            source_stats[source_type] = {
                'enabled': enabled_count,
                'total': total_count,
                'sources': source_list
            }
        
        return jsonify({
            'sources': source_stats,
            'total_types': len(sources)
        })
    
    except Exception as e:
        logger.error(f"Ошибка получения источников: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sources/<source_type>/<source_name>/toggle', methods=['POST'])
def api_toggle_source(source_type, source_name):
    """Включение/выключение источника"""
    try:
        if not config_manager:
            return jsonify({'error': 'Config manager недоступен'}), 500
        
        # TODO: Реализовать переключение источника
        # Это потребует изменения в config_manager
        
        return jsonify({
            'message': f'Источник {source_name} типа {source_type} переключен',
            'source_type': source_type,
            'source_name': source_name
        })
    
    except Exception as e:
        logger.error(f"Ошибка переключения источника {source_type}/{source_name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/charts/<symbol>')
def api_charts(symbol):
    """Данные для графиков"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Не удалось подключиться к БД'}), 500
        
        # Получаем исторические данные
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, price, volume 
            FROM token_data 
            WHERE symbol = ? 
            ORDER BY timestamp DESC 
            LIMIT 100
        """, (symbol.upper(),))
        
        data = []
        for row in cursor.fetchall():
            data.append({
                'timestamp': row['timestamp'],
                'price': row['price'],
                'volume': row['volume']
            })
        
        conn.close()
        
        return jsonify({
            'symbol': symbol.upper(),
            'data': data,
            'count': len(data)
        })
    
    except Exception as e:
        logger.error(f"Ошибка получения данных для графиков {symbol}: {e}")
        return jsonify({'error': str(e)}), 500

# Веб-страницы

@app.route('/')
def dashboard():
    """Главная страница дашборда"""
    return render_template('dashboard.html')

@app.route('/tokens')
def tokens_page():
    """Страница токенов"""
    return render_template('tokens.html')

@app.route('/alerts')
def alerts_page():
    """Страница алертов"""
    return render_template('alerts.html')

@app.route('/config')
def config_page():
    """Страница конфигурации"""
    return render_template('config.html')

@app.route('/analytics')
def analytics_page():
    """Страница аналитики"""
    return render_template('analytics.html')

# Обработчики ошибок

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Страница не найдена'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

# Утилиты

def format_number(value, decimals=2):
    """Форматирование чисел"""
    if value is None:
        return 'N/A'
    
    try:
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.{decimals}f}B"
        elif value >= 1_000_000:
            return f"{value / 1_000_000:.{decimals}f}M"
        elif value >= 1_000:
            return f"{value / 1_000:.{decimals}f}K"
        else:
            return f"{value:.{decimals}f}"
    except:
        return str(value)

def format_timestamp(timestamp):
    """Форматирование временных меток"""
    try:
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            dt = timestamp
        
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return str(timestamp)

# Регистрируем фильтры для шаблонов
app.jinja_env.filters['format_number'] = format_number
app.jinja_env.filters['format_timestamp'] = format_timestamp

if __name__ == '__main__':
    # Создаем директорию для шаблонов если не существует
    templates_dir = Path('templates')
    templates_dir.mkdir(exist_ok=True)
    
    # Запускаем Flask приложение
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    ) 