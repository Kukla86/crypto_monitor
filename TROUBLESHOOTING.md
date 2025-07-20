# 🔧 Устранение проблем

## Проблемы с зависимостями

### Ошибка "Не удается разрешить импорт yaml"

**Симптомы:**
```
ModuleNotFoundError: No module named 'yaml'
```

**Решение:**
1. Активируйте виртуальное окружение:
   ```bash
   source venv/bin/activate
   ```

2. Установите PyYAML:
   ```bash
   pip install PyYAML
   ```

3. Проверьте установку:
   ```bash
   python -c "import yaml; print('PyYAML установлен')"
   ```

### Ошибка "externally-managed-environment"

**Симптомы:**
```
error: externally-managed-environment
```

**Решение:**
1. Всегда используйте виртуальное окружение:
   ```bash
   source venv/bin/activate
   ```

2. Или установите с флагом:
   ```bash
   python3 -m pip install --user PyYAML
   ```

### Проверка всех зависимостей

Запустите скрипт проверки:
```bash
source venv/bin/activate
python check_dependencies.py
```

### Установка всех зависимостей

```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Проблемы с конфигурацией

### Ошибка "Файл config.env не найден"

**Решение:**
1. Скопируйте пример конфигурации:
   ```bash
   cp env_example.txt config.env
   ```

2. Отредактируйте `config.env` с вашими API ключами

### Ошибка "Файл tokens.json не найден"

**Решение:**
Файл `tokens.json` уже существует в проекте. Если он отсутствует, создайте его на основе примера в документации.

## Проблемы с запуском

### Ошибка "no running event loop"

**Симптомы:**
```
RuntimeError: no running event loop
```

**Решение:**
Эта ошибка исправлена в `config_manager.py`. Используйте актуальную версию кода.

### Ошибка "ModuleNotFoundError"

**Решение:**
1. Убедитесь, что виртуальное окружение активировано
2. Установите недостающие зависимости
3. Проверьте версию Python (рекомендуется 3.8+)

## Проверка системы

Запустите диагностический скрипт:
```bash
source venv/bin/activate
python run_monitor.py
```

## Часто используемые команды

```bash
# Активация окружения
source venv/bin/activate

# Проверка зависимостей
python check_dependencies.py

# Запуск диагностики
python run_monitor.py

# Запуск мониторинга
python monitor.py

# Запуск веб-интерфейса
python web_dashboard.py

# Установка зависимостей
pip install -r requirements.txt

# Обновление pip
pip install --upgrade pip
```

## Логи

Проверьте логи для диагностики проблем:
- `monitoring.log` - основные логи
- `error.log` - ошибки
- Консольный вывод

## Поддержка

Если проблемы не решаются:
1. Проверьте версию Python (должна быть 3.8+)
2. Убедитесь, что все файлы конфигурации существуют
3. Проверьте права доступа к файлам
4. Убедитесь, что виртуальное окружение активировано 