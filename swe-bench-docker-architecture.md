# SWE-bench Docker Architecture Documentation

## Overview

SWE-bench uses a containerized evaluation system to ensure reproducible results across different platforms. The Docker architecture consists of three image layers, each adding specific functionality for test execution.

## 🏗️ 3-Layer Docker Architecture

### 1. Base Image
**Purpose**: Common dependencies for all evaluations  
**Contents**: 
- Ubuntu with basic system packages
- Git, wget, curl, build-essential
- Python 3 and pip
- Miniconda for Python environment management
- Nonroot user for security

**Python Example**:
```dockerfile
FROM --platform={platform} ubuntu:{ubuntu_version}
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt update && apt install -y \
    wget git build-essential libffi-dev \
    python3 python3-pip python-is-python3 \
    jq curl locales tzdata

# Install Miniconda
RUN wget 'https://repo.anaconda.com/miniconda/Miniconda3-{conda_version}-Linux-{conda_arch}.sh' \
    && bash miniconda.sh -b -p /opt/miniconda3
ENV PATH=/opt/miniconda3/bin:$PATH
RUN conda init --all && conda config --append channels conda-forge

RUN adduser --disabled-password --gecos 'dog' nonroot
```

### 2. Environment Image
**Purpose**: Python environments for various configurations  
**Contents**:
- Inherits from base image
- Executes `setup_env.sh` for Python environment setup
- Creates conda environment "testbed"
- Automatically activates environment on startup

**Python Example**:
```dockerfile
FROM --platform={platform} {base_image_key}

COPY ./setup_env.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_env.sh
RUN chmod +x /root/setup_env.sh
RUN /bin/bash -c "source ~/.bashrc && /root/setup_env.sh"

WORKDIR /testbed/

# Automatic testbed environment activation
RUN echo "source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed" > /root/.bashrc
```

### 3. Instance Image
**Purpose**: Specific dependencies for each evaluation task  
**Contents**:
- Inherits from environment image
- Executes `setup_repo.sh` for repository cloning
- Installs specific project dependencies
- Configures working directory `/testbed`

**Python Example**:
```dockerfile
FROM --platform={platform} {env_image_name}

COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
```

## 🔄 Image Building Process

### Build Stages:

1. **Base Image Build**
   - Created for each platform (Linux x86_64, ARM64)
   - Installs common system dependencies
   - Configures Miniconda

2. **Environment Image Build**
   - Created based on base image
   - Executes `setup_env.sh` for Python setup
   - Creates conda environment "testbed"
   - Cached for reuse

3. **Instance Image Build**
   - Created for each evaluation instance
   - Клонируется конкретный репозиторий
   - Устанавливаются зависимости проекта
   - Применяется патч для исправления

### Управление кэшированием:

| Уровень кэша | Описание | Использование диска | Производительность |
|--------------|----------|---------------------|-------------------|
| `none` | Без кэширования | ~120GB во время выполнения | Самая медленная |
| `base` | Только базовый образ | ~120GB во время выполнения | Медленная |
| `env` (по умолчанию) | Базовый + environment | ~100GB | Средняя |
| `instance` | Все образы | ~2,000GB | Самая быстрая |

## 🚀 Процесс выполнения тестов

### 1. Подготовка контейнера
```python
def run_instance(test_spec: TestSpec, pred: dict, ...):
    # Создание лог-директории
    instance_id = test_spec.instance_id
    log_dir = RUN_EVALUATION_LOG_DIR / run_id / model_name / instance_id
    
    # Сборка instance image
    build_container(test_spec, pred, client, build_dir)
```

### 2. Применение патча
```python
GIT_APPLY_CMDS = [
    "git apply --verbose",
    "git apply --verbose --reject", 
    "patch --batch --fuzz=5 -p1 -i",
]

# Патч сохраняется в /tmp/patch.diff
DOCKER_PATCH = "/tmp/patch.diff"
```

### 3. Выполнение тестов
```python
# Тесты выполняются в /testbed директории
DOCKER_WORKDIR = "/testbed"

# Команды для выполнения тестов
test_commands = test_spec.get_test_commands()
for cmd in test_commands:
    result = exec_run_with_timeout(container, cmd, timeout)
```

### 4. Обработка результатов
```python
# Анализ вывода тестов
test_output = container.exec_run("cat /testbed/test_output.txt")
test_results = parse_test_output(test_output)

# Проверка статуса
if ">>>>> All Tests Passed" in test_output:
    status = "PASSED"
elif ">>>>> Some Tests Failed" in test_output:
    status = "FAILED"
```

## 📊 Логирование и отчетность

### Структура логов:
```
logs/
├── build_images/
│   ├── base/           # Логи сборки базовых образов
│   ├── env/            # Логи сборки environment образов  
│   └── instances/      # Логи сборки instance образов
├── run_evaluation/     # Логи выполнения оценки
└── run_validation/     # Логи валидации
```

### Ключевые сообщения:
- `>>>>> Applied Patch` - патч успешно применен
- `>>>>> Patch Apply Failed` - ошибка применения патча
- `>>>>> Init Succeeded` - инициализация успешна
- `>>>>> All Tests Passed` - все тесты прошли
- `>>>>> Some Tests Failed` - некоторые тесты провалились
- `>>>>> Tests Timed Out` - тесты превысили таймаут

## 🔧 Интеграция с валидационной системой

### Точки интеграции:

1. **Загрузка data points**
   - JSON файлы из `data_points/` директории
   - Парсинг полей: `instance_id`, `patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`

2. **Конвертация в predictions**
   ```python
   prediction = {
       "instance_id": data_point["instance_id"],
       "model_name_or_path": "gold",  # для валидации golden patches
       "model_patch": data_point["patch"]
   }
   ```

3. **Запуск оценки**
   ```python
   from swebench.harness.run_evaluation import run_instance
   
   # Создание TestSpec
   test_spec = make_test_spec(data_point)
   
   # Запуск оценки
   result = run_instance(test_spec, prediction, ...)
   ```

4. **Валидация результатов**
   - Проверка `FAIL_TO_PASS` тестов (должны пройти после патча)
   - Проверка `PASS_TO_PASS` тестов (должны продолжать проходить)
   - Анализ логов выполнения

## ⚡ Оптимизация производительности

### Рекомендации по workers:
- Использовать меньше `min(0.75 * os.cpu_count(), 24)` workers
- Для 8-ядерной машины: 6 workers
- Для 16-ядерной машины: 12 workers

### Управление ресурсами:
```bash
# Просмотр использования Docker
docker system df

# Очистка неиспользуемых ресурсов
docker system prune -a

# Удаление конкретных ресурсов
docker container prune  # остановленные контейнеры
docker image prune      # неиспользуемые образы
```

## 🚨 Обработка ошибок

### Типы ошибок:
1. **Ошибки сборки образов**
   - Недостаточно дискового пространства
   - Проблемы с сетью при загрузке пакетов
   - Ошибки в setup скриптах

2. **Ошибки применения патча**
   - Патч не может быть применен к репозиторию
   - Конфликты с текущим состоянием кода

3. **Ошибки выполнения тестов**
   - Тесты превышают таймаут
   - Зависимости не установлены корректно
   - Проблемы с окружением

### Стратегии восстановления:
- Автоматическая очистка ресурсов при ошибках
- Логирование детальной информации для диагностики
- Возможность повторного запуска с исправленными параметрами

## 📝 Заключение

SWE-bench Docker архитектура обеспечивает:
- **Воспроизводимость** результатов на различных платформах
- **Изоляцию** окружений для каждой задачи оценки
- **Масштабируемость** через параллельное выполнение
- **Эффективность** через многоуровневое кэширование образов

Эта архитектура является основой для создания надежной валидационной системы, которая может проверять качество SWE-bench data points в изолированных контейнерах.

