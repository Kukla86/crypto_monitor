# 📋 Инструкция по настройке GitHub репозитория

## 1. Создание репозитория на GitHub

1. Перейдите на [GitHub.com](https://github.com)
2. Нажмите кнопку "New repository" (зеленый "+" в правом верхнем углу)
3. Заполните форму:
   - **Repository name**: `crypto-news-monitor`
   - **Description**: `Advanced cryptocurrency monitoring system with real-time alerts, social media tracking, and AI-powered analysis`
   - **Visibility**: Public
   - **Initialize with**: НЕ ставьте галочки (у нас уже есть файлы)
4. Нажмите "Create repository"

## 2. Загрузка кода

После создания репозитория выполните команды:

```bash
# Добавить удаленный репозиторий (если еще не добавлен)
git remote add origin https://github.com/YOUR_USERNAME/crypto-news-monitor.git

# Отправить код на GitHub
git push -u origin main
```

## 3. Проверка

Перейдите на страницу репозитория и убедитесь, что все файлы загружены:
- `monitor.py` - основной файл системы
- `requirements.txt` - зависимости
- `README.md` - документация
- `.gitignore` - исключения для Git

## 4. Настройка GitHub Pages (опционально)

Если хотите добавить веб-демо:

1. Перейдите в Settings → Pages
2. Source: Deploy from a branch
3. Branch: main
4. Folder: / (root)
5. Save

## 5. Настройка Actions (опционально)

Для автоматического тестирования создайте `.github/workflows/test.yml`:

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.10
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    - name: Run tests
      run: |
        python -m pytest tests/
```

## 6. Защита ветки main

1. Settings → Branches
2. Add rule для main
3. Включите:
   - Require pull request reviews
   - Require status checks to pass
   - Include administrators

## 7. Настройка Issues и Projects

1. **Issues**: Включите для отслеживания багов и предложений
2. **Projects**: Создайте проект для планирования развития
3. **Wiki**: Опционально для дополнительной документации

## 8. Настройка Collaborators

Если планируете работать в команде:
1. Settings → Collaborators
2. Add people
3. Выберите права доступа (Write/Admin)

## 9. Настройка Security

1. **Dependabot**: Settings → Security & analysis → Enable Dependabot alerts
2. **Code scanning**: Settings → Security & analysis → Enable CodeQL
3. **Secret scanning**: Settings → Security & analysis → Enable Secret scanning

## 10. Финальная проверка

✅ Репозиторий создан и доступен по адресу: `https://github.com/YOUR_USERNAME/crypto-news-monitor`
✅ Код загружен
✅ README.md содержит актуальную информацию
✅ .gitignore настроен правильно
✅ Twitter мониторинг отключен (как указано в README)

## 🎉 Готово!

Ваш проект теперь доступен на GitHub и готов к использованию! 