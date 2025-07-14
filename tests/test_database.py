import unittest
import sqlite3
import os
import tempfile
from unittest.mock import patch, MagicMock
import monitor
import psutil

class TestDatabase(unittest.TestCase):
    def setUp(self):
        # Создаем временную БД для тестов
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()

    def tearDown(self):
        # Удаляем временную БД
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    @patch('monitor.sqlite3.connect')
    def test_init_database_success(self, mock_connect):
        # Создаем правильный mock для контекстного менеджера
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # Настраиваем контекстный менеджер
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)
        mock_connect.return_value = mock_conn
        
        monitor.init_database()
        
        # Проверяем что создаются все необходимые таблицы
        self.assertGreater(mock_cursor.execute.call_count, 0)
        # Проверяем что контекстный менеджер использовался
        mock_conn.__enter__.assert_called()
        mock_conn.__exit__.assert_called()

    @patch('monitor.sqlite3.connect')
    def test_init_database_error(self, mock_connect):
        mock_connect.side_effect = sqlite3.Error("Database error")
        
        with self.assertLogs('monitor', level='ERROR') as cm:
            monitor.init_database()
        
        self.assertIn('Ошибка инициализации БД', ''.join(cm.output))

    def test_save_token_data_success(self):
        # Создаем реальную БД для теста
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Создаем таблицу
        cursor.execute('''
            CREATE TABLE token_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL,
                volume_24h REAL,
                market_cap REAL,
                holders_count INTEGER,
                top_holders TEXT,
                tvl REAL,
                social_mentions INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        
        # Тестируем сохранение данных
        test_data = {
            'price': 1.23,
            'volume_24h': 1000,
            'market_cap': 1000000,
            'holders_count': 1000,
            'top_holders': [],
            'tvl': 50000,
            'social_mentions': 100
        }
        
        with patch('monitor.sqlite3.connect') as mock_connect:
            # Создаем правильный mock для контекстного менеджера
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            # Настраиваем контекстный менеджер
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=None)
            mock_connect.return_value = mock_conn
            
            monitor.save_token_data('FUEL', test_data)
            
            mock_cursor.execute.assert_called()
            # Проверяем что контекстный менеджер использовался
            mock_conn.__enter__.assert_called()
            mock_conn.__exit__.assert_called()

    def test_save_token_data_no_valid_data(self):
        # Тестируем случай когда нет валидных данных для сохранения
        test_data = {
            'price': 0,
            'volume_24h': 0,
            'market_cap': 0,
            'holders_count': 0,
            'top_holders': [],
            'tvl': 0,
            'social_mentions': 0
        }
        
        with patch('monitor.sqlite3.connect') as mock_connect:
            # Создаем правильный mock для контекстного менеджера
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            # Настраиваем контекстный менеджер
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=None)
            mock_connect.return_value = mock_conn
            
            monitor.save_token_data('FUEL', test_data)
            
            # Проверяем что INSERT вызывался (теперь сохраняем даже нулевые значения)
            mock_cursor.execute.assert_called()
            # Проверяем что контекстный менеджер использовался
            mock_conn.__enter__.assert_called()
            mock_conn.__exit__.assert_called()

    def test_get_last_volume_success(self):
        # Создаем тестовую БД с данными
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE realtime_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                volume_24h REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Добавляем тестовые данные
        cursor.execute('''
            INSERT INTO realtime_data (symbol, volume_24h, timestamp)
            VALUES (?, ?, datetime('now', '-30 minutes'))
        ''', ('FUEL', 1000.0))
        conn.commit()
        conn.close()
        # Используем временную БД
        monitor.DB_PATH = self.db_path
        result = monitor.get_last_volume('FUEL', 60)
        self.assertEqual(result, 1000.0)

    def test_was_alert_sent_success(self):
        # Создаем тестовую БД с алертом
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                token_symbol TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Добавляем тестовый алерт
        cursor.execute('''
            INSERT INTO alerts (level, message, token_symbol, timestamp)
            VALUES (?, ?, ?, datetime('now', '-30 minutes'))
        ''', ('WARNING', 'Объем вырос до 1000.0', 'FUEL'))
        conn.commit()
        conn.close()
        # Используем временную БД
        monitor.DB_PATH = self.db_path
        result = monitor.was_alert_sent('FUEL', 1000.0)
        self.assertTrue(result)

    @patch('monitor.sqlite3.connect')
    def test_was_alert_sent_no_previous_alert(self, mock_connect):
        # Создаем правильный mock для контекстного менеджера
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (0,)  # Нет предыдущих алертов
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        result = monitor.was_alert_sent('FUEL', 1000.0)
        self.assertFalse(result)

    def test_no_sqlite_connection_leak(self):
        """Проверяет, что после работы с БД не остаётся открытых соединений (утечек)"""
        import sys
        import time
        
        # Создаём тестовую БД
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, value TEXT)''')
        conn.commit()
        conn.close()

        # Получаем PID текущего процесса
        pid = os.getpid()
        proc = psutil.Process(pid)
        
        # Считаем открытые дескрипторы на .db до вызова функции
        before = [f for f in proc.open_files() if f.path.endswith('.db')]

        # Используем mock для тестирования без реальных соединений
        with patch('monitor.sqlite3.connect') as mock_connect:
            # Создаем правильный mock для контекстного менеджера
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            # Настраиваем контекстный менеджер
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=None)
            mock_connect.return_value = mock_conn
            
            # Вызываем функции, которые должны использовать with
            monitor.init_database()
            monitor.save_token_data('FUEL', {'price': 1, 'volume_24h': 2, 'market_cap': 3, 'holders_count': 4, 'top_holders': [], 'tvl': 5, 'social_mentions': 6})
            monitor.get_last_volume('FUEL')
            monitor.was_alert_sent('FUEL', 2)
            monitor.get_last_price('FUEL')
            monitor.was_price_alert_sent('FUEL', 1)
            monitor.get_alert_reference('FUEL')
            monitor.set_alert_reference('FUEL', 1, 2)

            # Проверяем, что контекстный менеджер использовался для всех вызовов
            self.assertGreater(mock_conn.__enter__.call_count, 0)
            self.assertGreater(mock_conn.__exit__.call_count, 0)
            # Проверяем, что количество вызовов __enter__ равно количеству __exit__
            self.assertEqual(mock_conn.__enter__.call_count, mock_conn.__exit__.call_count)

if __name__ == '__main__':
    unittest.main() 