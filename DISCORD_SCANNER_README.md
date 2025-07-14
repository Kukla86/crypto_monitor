# Discord Activity Scanner для Новых Проектов

## 📋 Описание

Модуль `discord_activity.py` предназначен для анализа активности Discord серверов новых криптопроектов. Когда Telegram-бот находит новый проект с фандрайзом, этот сканер проверяет Discord-сервер проекта и анализирует последние сообщения для определения активности и важных событий.

## 🚀 Возможности

- **Подключение к Discord серверам** через бот-токен
- **Сканирование целевых каналов** (announcements, general, chat, community, etc.)
- **AI анализ активности** через OpenAI GPT
- **Определение actionable событий** (mint, airdrop, whitelist, early roles)
- **Отправка отчетов в Telegram**
- **Сохранение данных** в SQLite и CSV

## ⚙️ Настройка

### 1. Discord Bot Token

Создайте Discord бота на [Discord Developer Portal](https://discord.com/developers/applications):

1. Создайте новое приложение
2. Перейдите в раздел "Bot"
3. Создайте бота и скопируйте токен
4. Добавьте токен в `.env`:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
```

### 2. Необходимые разрешения для бота

Бот должен иметь следующие разрешения:
- `Read Messages/View Channels`
- `Read Message History`
- `Use Slash Commands` (опционально)

### 3. Переменные окружения

Добавьте в `.env`:

```env
# Discord Bot
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# OpenAI (для AI анализа)
OPENAI_API_KEY=your_openai_api_key_here

# Telegram (для отправки отчетов)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

## 📖 Использование

### Базовое использование

```python
from discord_activity import scan_discord

# Сканирование Discord сервера
result = await scan_discord(
    invite_link="https://discord.gg/agoraxyz",
    project_name="Agora"
)

if result:
    print(f"Проект: {result.project_name}")
    print(f"Сообщений: {result.total_messages}")
    print(f"Actionable: {result.actionable}")
    print(f"Резюме: {result.summary}")
```

### Интеграция с основным мониторингом

```python
# В monitor.py или другом модуле
async def check_new_project(project_name: str, discord_link: str):
    """Проверка нового проекта"""
    
    # Сканируем Discord активность
    from discord_activity import scan_discord
    
    discord_result = await scan_discord(discord_link, project_name)
    
    if discord_result and discord_result.actionable:
        # Отправляем алерт о важном проекте
        await send_alert(
            level="HIGH",
            message=f"Новый активный проект: {project_name}",
            context={
                "discord_summary": discord_result.summary,
                "key_events": discord_result.key_events
            }
        )
```

## 🎯 Целевые каналы

Сканер автоматически мониторит каналы с названиями:

- `announcements` - анонсы
- `general` - общие обсуждения
- `chat` - чат
- `community` - сообщество
- `info` - информация
- `launch` - запуск
- `news` - новости
- `updates` - обновления
- `alpha` / `beta` - тестирование
- `testnet` / `mainnet` - сети
- `mint` / `airdrop` / `whitelist` - события

## 🔍 Actionable события

Сканер ищет ключевые слова для определения важных событий:

- `early role` / `og role` - ранние роли
- `whitelist` - белый список
- `mint` - минт
- `airdrop` - аирдроп
- `testnet` / `mainnet` - запуск сети
- `launch` - запуск
- `presale` / `fairlaunch` - предпродажа
- `alpha access` / `beta access` - ранний доступ
- `vip` / `founder` / `partner` - привилегированные роли

## 📊 Структура данных

### DiscordMessage
```python
@dataclass
class DiscordMessage:
    content: str          # Текст сообщения
    author: str           # Автор
    channel: str          # Канал
    timestamp: datetime   # Время
    message_id: int       # ID сообщения
```

### ActivitySummary
```python
@dataclass
class ActivitySummary:
    project_name: str     # Название проекта
    total_messages: int   # Количество сообщений
    active_channels: List[str]  # Активные каналы
    summary: str          # AI резюме
    actionable: bool      # Есть ли важные события
    key_events: List[str] # Ключевые события
    confidence: float     # Уверенность анализа
    timestamp: datetime   # Время анализа
```

## 📁 Файлы данных

### SQLite база данных
- `discord_activity.sqlite` - основная база данных
- Таблица: `discord_activity`

### CSV лог
- `activity_log.csv` - лог всех анализов
- Колонки: timestamp, project_name, total_messages, active_channels, summary, actionable, key_events, confidence

## 🔧 Настройка фильтров

### Изменение целевых каналов

```python
scanner = DiscordActivityScanner()
scanner.target_channels = [
    'announcements', 'general', 'chat', 'community',
    'your_custom_channel'  # Добавьте свои каналы
]
```

### Изменение ключевых слов

```python
scanner.actionable_keywords = [
    'early role', 'og role', 'whitelist', 'mint', 'airdrop',
    'your_custom_keyword'  # Добавьте свои ключевые слова
]
```

## 🚨 Обработка ошибок

Модуль обрабатывает следующие ошибки:

- **Discord.NotFound** - сервер не найден
- **Discord.Forbidden** - нет доступа к серверу/каналу
- **Rate limiting** - превышение лимитов API
- **AI API ошибки** - недоступность OpenAI

## 📈 Пример отчета в Telegram

```
✅ Discord Activity Report

🧩 Project: Agora
📝 Messages: 1,247
📢 Channels: announcements, general, community

📋 Summary:
Высокая активность в сообществе. Проект DeFi типа, 
стадия тестнета. Обнаружены упоминания early roles 
и whitelist. Сообщество очень энтузиастично.

🎯 Key Events: early role, whitelist, testnet

⚡ Actionable: YES
🎯 Confidence: 85%
🕐 Analyzed: 2024-01-15 14:30
```

## 🔮 Будущие улучшения

- [ ] Поддержка множественных Discord серверов
- [ ] Анализ изображений и эмодзи
- [ ] Интеграция с другими социальными платформами
- [ ] Машинное обучение для улучшения анализа
- [ ] Веб-интерфейс для просмотра результатов

## ⚠️ Важные замечания

1. **Не запускайте сейчас** - модуль подготовлен для будущего использования
2. **Соблюдайте rate limits** Discord API
3. **Используйте бот-токен** (не self-bot)
4. **Уважайте приватность** пользователей
5. **Соблюдайте ToS** Discord и других платформ

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи в консоли
2. Убедитесь в правильности токенов
3. Проверьте разрешения бота
4. Убедитесь в доступности Discord сервера 