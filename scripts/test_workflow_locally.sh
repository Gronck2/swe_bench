#!/bin/bash
# Локальный тест GitHub Actions workflow

set -e

echo "🧪 Локальное тестирование GitHub Actions workflow"
echo "=================================================="

# Активируем виртуальное окружение
source venv/bin/activate

echo "✅ Активировано виртуальное окружение"

# Устанавливаем зависимости
echo "📦 Установка зависимостей..."
python -m pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    pip install rich click swebench docker
fi

echo "✅ Зависимости установлены"

# Симуляция получения измененных файлов
echo "🔍 Поиск измененных data point файлов..."

# Получаем измененные файлы (симуляция git diff)
if [ "$1" = "all" ]; then
    # Тестируем все файлы
    CHANGED_FILES=$(find data_points -name "*.json" | head -3)
else
    # Тестируем только новые/измененные файлы
    CHANGED_FILES=$(git status --porcelain | grep "^[AM].*data_points.*\.json$" | cut -c4- || true)
    
    # Если нет измененных файлов, используем тестовый файл
    if [ -z "$CHANGED_FILES" ]; then
        CHANGED_FILES="data_points/astropy__astropy-11693.json"
        echo "⚠️  Нет измененных файлов, используем тестовый: $CHANGED_FILES"
    fi
fi

if [ -n "$CHANGED_FILES" ]; then
    echo "📁 Найденные файлы для валидации:"
    echo "$CHANGED_FILES"
    
    # Экспортируем переменную окружения
    export CHANGED_FILES
    
    echo "🚀 Запуск валидации..."
    python scripts/validate_changed.py
    
    # Проверяем результат
    if [ $? -eq 0 ]; then
        echo "✅ Валидация прошла успешно!"
        echo "🎉 Workflow завершился без ошибок"
    else
        echo "❌ Валидация провалилась!"
        echo "💥 Workflow завершился с ошибками"
        exit 1
    fi
else
    echo "ℹ️  Нет data point файлов для валидации"
    echo "✅ Workflow завершился (нечего валидировать)"
fi

echo "=================================================="
echo "🏁 Локальное тестирование завершено"
