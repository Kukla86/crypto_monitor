# Crypto Monitor - Система мониторинга криптовалют

Современная система мониторинга криптовалют с поддержкой on-chain данных, CEX, DEX, социальных сетей, AI анализа и веб-интерфейса.

## 🚀 Возможности

### 📊 Мониторинг данных
- **On-chain данные**: Ethereum, Solana блокчейны
- **CEX биржи**: Binance, Bybit, OKX, HTX, Gate.io и другие
- **DEX агрегаторы**: DexScreener, DeFi Llama, GeckoTerminal
- **Социальные сети**: Twitter, Telegram, Discord, GitHub
- **Аналитика**: DeBank, Arkham, BubbleMaps

### 🤖 AI и анализ
- Анализ настроений в социальных сетях
- Предсказание трендов с помощью ML
- Автоматическое определение важных событий
- Анализ новостей и их влияния на цены

### 📱 Уведомления
- Telegram бот с детальными алертами
- Discord интеграция
- Email уведомления
- Веб-интерфейс в реальном времени

### 🎛️ Управление
- Современный веб-дашборд
- REST API для интеграции
- Гибкая конфигурация через YAML
- Кэширование для оптимизации производительности

## 📋 Требования

- Python 3.8+
- SQLite3
- Доступ к интернету
- API ключи для различных сервисов

## 🚀 Быстрый старт

```bash
# Клонирование и настройка
git clone https://github.com/your-username/crypto-monitor.git
cd crypto-monitor

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Установка зависимостей
pip install -r requirements.txt

# Проверка системы
python run_monitor.py

# Запуск мониторинга
python monitor.py
```

## 🛠️ Установка

### 1. Клонирование репозитория
```bash
git clone https://github.com/your-username/crypto-monitor.git
cd crypto-monitor
```

### 2. Создание виртуального окружения
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

### 3. Установка зависимостей
```bash
pip install -r requirements.txt
```

**Примечание:** Если возникают проблемы с установкой, см. [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

### 4. Настройка переменных окружения
Скопируйте файл конфигурации:
```bash
cp env_example.txt config.env
```

Отредактируйте `config.env` и добавьте ваши API ключи:
```env
# API ключи
ETHERSCAN_API_KEY=your_etherscan_api_key
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
ALCHEMY_API_KEY=your_alchemy_api_key
HELIUS_API_KEY=your_helius_api_key

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=your_phone_number

# Discord
DISCORD_USER_TOKEN=your_discord_user_token

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Настройки мониторинга
CHECK_INTERVAL=60
PRICE_CHANGE_THRESHOLD=15
VOLUME_CHANGE_THRESHOLD=100
WEBSOCKET_ENABLED=true
REAL_TIME_ALERTS=true

# Логирование
LOG_LEVEL=INFO
LOG_FILE=monitoring.log
```

## ⚙️ Конфигурация

### Источники данных
Редактируйте `config/sources.yaml` для настройки источников данных:

```yaml
sources:
  onchain:
    ethereum:
      enabled: true
      priority: "high"
      endpoints:
        - name: "Etherscan"
          url: "https://api.etherscan.io/api"
          rate_limit: 5
  cex:
    binance:
      enabled: true
      priority: "high"
      endpoints:
        - name: "REST API"
          url: "https://api.binance.com/api/v3"
          rate_limit: 1200
```

### Токены
Настройте токены в `tokens.json`:

```json
{
  "tokens": {
    "FUEL": {
      "symbol": "FUEL",
      "name": "Fuel",
      "chain": "ethereum",
      "contract": "0x675b68aa4d9c2d3bb3f0397048e62e6b7192079c",
      "decimals": 18,
      "priority": "high",
      "min_amount_usd": 500000
    }
  }
}
```

## 🚀 Запуск

### Проверка системы
Перед запуском проверьте, что все настроено корректно:
```bash
python run_monitor.py
```

### Основной мониторинг
```bash
python monitor.py
```

### Веб-интерфейс
```bash
python web_dashboard.py
```

### Запуск в фоне (Linux/Mac)
```bash
nohup python monitor.py > monitor.log 2>&1 &
nohup python web_dashboard.py > web.log 2>&1 &
```

## 📊 Веб-интерфейс

После запуска веб-интерфейса откройте браузер и перейдите по адресу:
```
http://localhost:5000
```

### Доступные страницы:
- **Дашборд** (`/`) - Общий обзор системы
- **Токены** (`/tokens`) - Детальная информация о токенах
- **Алерты** (`/alerts`) - История и настройки алертов
- **Настройки** (`/config`) - Конфигурация системы
- **Аналитика** (`/analytics`) - Графики и аналитика

## 🔌 API

Система предоставляет REST API для интеграции:

### Статус системы
```bash
GET /api/status
```

### Список токенов
```bash
GET /api/tokens
```

### Информация о токене
```bash
GET /api/tokens/{symbol}
```

### Алерты
```bash
GET /api/alerts
```

### Конфигурация
```bash
GET /api/config
```

### Статистика кэша
```bash
GET /api/cache
```

### Очистка кэша
```bash
POST /api/cache/{cache_name}/clear
```

## 🤖 AI и ML

### Анализ настроений
Система автоматически анализирует настроения в социальных сетях:
- Twitter твиты
- Telegram сообщения
- Discord сообщения
- GitHub коммиты

### Предсказание трендов
ML модели предсказывают:
- Направление движения цен
- Вероятность значительных изменений
- Рекомендации по торговле

### Анализ новостей
- Автоматическое определение важности новостей
- Анализ влияния на цены токенов
- Классификация по типам событий

## 🔧 Разработка

### Структура проекта
```
crypto-monitor/
├── monitor.py              # Основной файл мониторинга
├── web_dashboard.py        # Веб-интерфейс
├── config_manager.py       # Менеджер конфигурации
├── cache_manager.py        # Менеджер кэширования
├── config/
│   └── sources.yaml        # Конфигурация источников
├── templates/
│   └── dashboard.html      # Шаблон дашборда
├── tokens.json             # Конфигурация токенов
├── requirements.txt        # Зависимости
└── README.md              # Документация
```

### Добавление новых источников
1. Добавьте конфигурацию в `config/sources.yaml`
2. Реализуйте функции в `monitor.py`
3. Добавьте обработку в веб-интерфейс

### Добавление новых токенов
1. Добавьте токен в `tokens.json`
2. Настройте социальные аккаунты
3. Добавьте специфичную логику мониторинга

## 🧪 Тестирование

### Запуск тестов
```bash
pytest tests/
```

### Тестирование конкретных модулей
```bash
pytest tests/test_monitor.py
pytest tests/test_config.py
pytest tests/test_cache.py
```

### Покрытие кода
```bash
pytest --cov=. tests/
```

## 🔒 Безопасность

### Рекомендации
- Храните API ключи в переменных окружения
- Используйте HTTPS для веб-интерфейса
- Ограничьте доступ к API
- Регулярно обновляйте зависимости

### Переменные окружения
Никогда не коммитьте файлы с API ключами:
```bash
# Добавьте в .gitignore
config.env
*.key
secrets/
```

## 📈 Мониторинг и логирование

### Логи
Система создает несколько логов:
- `monitoring.log` - Основные логи
- `error.log` - Ошибки
- `web.log` - Логи веб-интерфейса

### Метрики
Отслеживаются следующие метрики:
- Количество запросов к API
- Время отклика источников
- Эффективность кэша
- Количество алертов

## 🚨 Устранение неполадок

### Частые проблемы

#### Ошибка подключения к API
```bash
# Проверьте API ключи
echo $ETHERSCAN_API_KEY

# Проверьте интернет соединение
ping api.etherscan.io
```

#### Проблемы с веб-интерфейсом
```bash
# Проверьте порт
netstat -tulpn | grep 5000

# Перезапустите веб-сервер
pkill -f web_dashboard.py
python web_dashboard.py
```

#### Проблемы с кэшем
```bash
# Очистите кэш через API
curl -X POST http://localhost:5000/api/cache/price_data/clear
```

### Логи для отладки
```bash
# Просмотр логов в реальном времени
tail -f monitoring.log

# Поиск ошибок
grep "ERROR" monitoring.log
```

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Добавьте тесты
5. Создайте Pull Request

### Стандарты кода
- Следуйте PEP 8
- Добавляйте docstrings
- Пишите тесты для новой функциональности
- Обновляйте документацию

## 📄 Лицензия

MIT License - см. файл LICENSE для деталей.

## 📞 Поддержка

- Создайте Issue в GitHub
- Напишите на email: support@example.com
- Присоединяйтесь к Discord серверу

## 🔄 Обновления

### Автоматические обновления
```bash
# Обновите код
git pull origin main

# Обновите зависимости
pip install -r requirements.txt --upgrade

# Перезапустите сервисы
pkill -f monitor.py
python monitor.py
```

### Ручные обновления
1. Скачайте новую версию
2. Создайте резервную копию конфигурации
3. Обновите файлы
4. Проверьте совместимость
5. Перезапустите систему

---

**Crypto Monitor** - мощная система мониторинга криптовалют с современным интерфейсом и AI возможностями. 