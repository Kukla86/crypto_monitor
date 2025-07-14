# Whale Tracker - Отслеживание Топ-30 Держателей Токенов

## 📋 Описание

Модуль `whale_tracker.py` предназначен для мониторинга изменений балансов крупных держателей (китов) криптовалютных токенов. При добавлении нового токена система автоматически отслеживает топ-30 держателей (исключая биржи) и отправляет алерты в Telegram при значительных изменениях их балансов.

## 🚀 Возможности

- **Автоматическое отслеживание** топ-30 держателей токенов
- **Исключение бирж** из мониторинга (Binance, Coinbase, Kraken, etc.)
- **Обнаружение изменений** баланса в реальном времени
- **AI анализ** значимости изменений
- **Telegram алерты** с детальной информацией
- **Сохранение истории** изменений в SQLite
- **Поддержка Ethereum** (готово к расширению на другие сети)

## ⚙️ Настройка

### 1. Etherscan API Key

Получите бесплатный API ключ на [Etherscan](https://etherscan.io/apis):

1. Зарегистрируйтесь на Etherscan
2. Перейдите в раздел API-KEYs
3. Создайте новый ключ
4. Добавьте в `.env`:

```env
ETHERSCAN_API_KEY=your_etherscan_api_key_here
```

### 2. Переменные окружения

Добавьте в `.env`:

```env
# Etherscan API
ETHERSCAN_API_KEY=your_etherscan_api_key_here

# Telegram (для алертов)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### 3. Установка зависимостей

```bash
pip install web3 aiohttp python-dotenv
```

## 📖 Использование

### Базовое использование

```python
from whale_tracker import WhaleTracker

# Создаем трекер
tracker = WhaleTracker()

# Добавляем токен для мониторинга
await tracker.add_token_monitoring(
    symbol="FUEL",
    contract_address="0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c"
)

# Запускаем мониторинг
await tracker.start_monitoring(interval_minutes=30)
```

### Интеграция с основным мониторингом

```python
# В monitor.py
async def add_new_token_monitoring(symbol: str, contract_address: str):
    """Добавление нового токена в whale мониторинг"""
    
    from whale_tracker import WhaleTracker
    
    tracker = WhaleTracker()
    success = await tracker.add_token_monitoring(symbol, contract_address)
    
    if success:
        logger.info(f"Токен {symbol} добавлен в whale мониторинг")
        # Отправляем уведомление
        await send_alert(
            level="INFO",
            message=f"Whale мониторинг запущен для {symbol}",
            token_symbol=symbol
        )
```

## 🎯 Функциональность

### 1. Отслеживание держателей

- **Получение топ-100** держателей через Etherscan API
- **Фильтрация бирж** (автоматическое исключение известных адресов)
- **Выбор топ-30** небиржевых держателей
- **Расчет процентов** от общего предложения

### 2. Обнаружение изменений

- **Сравнение балансов** между обновлениями
- **Порог срабатывания** >1% изменения
- **Отслеживание новых** держателей в топ-30
- **История изменений** в базе данных

### 3. Алерты в Telegram

```
📈 WHALE ALERT - FUEL

🐋 Держатель: 0x1234...5678
📊 Действие: ПОКУПКА
💰 Изменение: 1,000,000 FUEL
📈 Процент: +15.23%
💎 Новый баланс: 8,500,000 FUEL
🕐 Время: 2024-01-15 14:30

🔍 Etherscan
```

## 📊 Структура данных

### WhaleHolder
```python
@dataclass
class WhaleHolder:
    address: str           # Адрес кошелька
    balance: Decimal       # Баланс токенов
    percentage: float      # Процент от общего предложения
    rank: int             # Ранг в топе
    last_updated: datetime # Время последнего обновления
    is_exchange: bool     # Является ли биржей
    exchange_name: str    # Название биржи
```

### BalanceChange
```python
@dataclass
class BalanceChange:
    address: str          # Адрес кошелька
    old_balance: Decimal  # Старый баланс
    new_balance: Decimal  # Новый баланс
    change_amount: Decimal # Количество изменений
    change_percentage: float # Процент изменения
    timestamp: datetime   # Время изменения
    token_symbol: str     # Символ токена
```

## 🏦 Исключаемые биржи

Система автоматически исключает известные адреса бирж:

- **Binance** - основные адреса
- **Coinbase** - основные адреса
- **Kraken** - основные адреса
- **OKX** - основные адреса
- **Bybit** - основные адреса
- **Gate.io** - основные адреса
- **HTX** - основные адреса
- **DEX роутеры** - Uniswap, SushiSwap, PancakeSwap
- **Dead адреса** - сожженные токены

## 📁 Файлы данных

### SQLite база данных
- `whale_tracker.db` - основная база данных

#### Таблицы:
1. **monitored_tokens** - токены под мониторингом
2. **whale_holders** - данные о держателях
3. **balance_changes** - история изменений баланса

### Структура таблиц

```sql
-- Токены под мониторингом
CREATE TABLE monitored_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT UNIQUE,
    contract_address TEXT,
    chain TEXT,
    added_at DATETIME,
    last_updated DATETIME
);

-- Держатели токенов
CREATE TABLE whale_holders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_symbol TEXT,
    address TEXT,
    balance TEXT,
    percentage REAL,
    rank INTEGER,
    is_exchange BOOLEAN,
    exchange_name TEXT,
    last_updated DATETIME,
    UNIQUE(token_symbol, address)
);

-- Изменения баланса
CREATE TABLE balance_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_symbol TEXT,
    address TEXT,
    old_balance TEXT,
    new_balance TEXT,
    change_amount TEXT,
    change_percentage REAL,
    timestamp DATETIME
);
```

## 🔧 Настройка параметров

### Изменение интервала мониторинга

```python
# Обновление каждые 15 минут
await tracker.start_monitoring(interval_minutes=15)
```

### Изменение порога алертов

```python
# В методе check_balance_changes
if abs(change_percentage) > 0.5:  # 0.5% вместо 1%
    # Отправляем алерт
```

### Добавление новых бирж

```python
tracker.exchange_addresses.update({
    '0xNEW_EXCHANGE_ADDRESS': 'New Exchange Name'
})
```

## 📈 Примеры алертов

### Покупка китом
```
📈 WHALE ALERT - FUEL

🐋 Держатель: 0x1234...5678
📊 Действие: ПОКУПКА
💰 Изменение: 2,500,000 FUEL
📈 Процент: +25.67%
💎 Новый баланс: 12,500,000 FUEL
🕐 Время: 2024-01-15 14:30

🔍 Etherscan
```

### Продажа китом
```
📉 WHALE ALERT - FUEL

🐋 Держатель: 0x8765...4321
📊 Действие: ПРОДАЖА
💰 Изменение: -1,800,000 FUEL
📈 Процент: -18.45%
💎 Новый баланс: 7,950,000 FUEL
🕐 Время: 2024-01-15 15:45

🔍 Etherscan
```

### Новый держатель в топ-30
```
🐋 WHALE ALERT - FUEL

🐋 Держатель: 0x9999...8888
📊 Действие: НОВЫЙ В ТОП-30
💰 Изменение: 5,000,000 FUEL
📈 Процент: +100.00%
💎 Новый баланс: 5,000,000 FUEL
🕐 Время: 2024-01-15 16:20

🔍 Etherscan
```

## 🚨 Обработка ошибок

Модуль обрабатывает следующие ошибки:

- **Etherscan API ошибки** - превышение лимитов, недоступность
- **HTTP ошибки** - проблемы с сетью
- **Ошибки БД** - проблемы с SQLite
- **Telegram ошибки** - проблемы с отправкой алертов

## 🔮 Будущие улучшения

- [ ] Поддержка BSC, Polygon, других сетей
- [ ] Анализ паттернов поведения китов
- [ ] Интеграция с DEX для отслеживания транзакций
- [ ] Веб-интерфейс для просмотра данных
- [ ] Машинное обучение для предсказания движений
- [ ] Поддержка NFT коллекций

## ⚠️ Важные замечания

1. **Rate Limits** - Etherscan имеет лимиты на бесплатные запросы
2. **Точность данных** - зависит от обновления Etherscan
3. **Приватность** - адреса кошельков публичны в блокчейне
4. **Ложные срабатывания** - некоторые изменения могут быть внутренними переводами

## 📞 Поддержка

При возникновении проблем:
1. Проверьте Etherscan API ключ
2. Убедитесь в правильности адреса контракта
3. Проверьте логи в консоли
4. Убедитесь в доступности Etherscan API

## 🎯 Пример интеграции

```python
# В основном мониторинге
async def setup_whale_tracking():
    """Настройка whale мониторинга для всех токенов"""
    
    from whale_tracker import WhaleTracker
    
    tracker = WhaleTracker()
    
    # Добавляем все токены из конфигурации
    for symbol, token_data in TOKENS.items():
        if 'contract' in token_data:
            await tracker.add_token_monitoring(
                symbol=symbol,
                contract_address=token_data['contract']
            )
    
    # Запускаем мониторинг в фоне
    asyncio.create_task(tracker.start_monitoring(interval_minutes=30))
``` 