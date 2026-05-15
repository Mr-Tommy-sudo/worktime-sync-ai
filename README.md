# AI-Таймкипер — Backend. Документация

## Структура проекта

```
├── database.py       # Инициализация БД, схема таблиц, mock-данные
├── ai_parser.py      # Интеграция с LLM (парсинг свободного текста → JSON)
├── api_functions.py  # CRUD-функции для Streamlit-интерфейса
├── worktime.db       # SQLite-файл (создаётся автоматически)
└── README.md
```

---

## Быстрый старт

### 1. Инициализация базы данных

```bash
python database.py
```

Создаст файл `worktime.db` и заполнит его тестовыми данными:
- 3 пользователя, 3 проекта, 7 записей времени за последнюю неделю.

### 2. Установка зависимостей

```bash
pip install requests
```

Стандартная библиотека (`sqlite3`, `json`) входит в Python 3.x.

### 3. Настройка LLM-провайдера

Задайте переменную окружения с API-ключом нужного провайдера:

```bash
# Anthropic Claude (по умолчанию)
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export LLM_PROVIDER=openai
export OPENAI_API_KEY="sk-..."

# GigaChat
export LLM_PROVIDER=gigachat
export GIGACHAT_TOKEN="your-token"

# YandexGPT
export LLM_PROVIDER=yandexgpt
export YANDEX_API_KEY="your-key"
export YANDEX_FOLDER_ID="your-folder-id"
```

---

## Схема базы данных

```sql
users (
    id          INTEGER PRIMARY KEY,
    name        TEXT,           -- "Алексей Петров"
    email       TEXT UNIQUE,    -- "a.petrov@company.ru"
    role        TEXT,           -- "employee" | "manager" | "admin"
    created_at  TEXT            -- дата добавления
)

projects (
    id          INTEGER PRIMARY KEY,
    name        TEXT,           -- "Редизайн сайта"
    description TEXT,
    status      TEXT,           -- "active" | "completed" | "paused"
    created_at  TEXT
)

time_logs (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER FK → users.id,
    project_id  INTEGER FK → projects.id,
    log_date    TEXT,           -- "YYYY-MM-DD"
    hours       REAL,           -- 0 < hours ≤ 24
    raw_text    TEXT,           -- исходный текст от AI-парсера
    created_at  TEXT
)
```

---

## Справочник функций

### `api_functions.py`

#### `get_all_projects(status=None) → list[dict]`
Список всех проектов. Используйте для выпадающего списка в Streamlit.

```python
from api_functions import get_all_projects

projects = get_all_projects()
# [{"id": 1, "name": "Редизайн сайта", "status": "active"}, ...]

# Только активные
active = get_all_projects(status="active")
```

---

#### `get_all_users() → list[dict]`
Список всех сотрудников.

```python
from api_functions import get_all_users
users = get_all_users()
# [{"id": 1, "name": "Алексей Петров", "email": "...", "role": "employee"}, ...]
```

---

#### `save_time_log(user_id, project_id, log_date, hours, raw_text=None) → int`
Сохраняет новую запись. Возвращает ID созданной записи.

```python
from api_functions import save_time_log

new_id = save_time_log(
    user_id=1,
    project_id=2,
    log_date="2025-01-15",  # или str(date.today())
    hours=3.5,
    raw_text="Настройка CRM 3.5 часа",  # текст от AI-парсера
)
print(f"Создана запись #{new_id}")
```

---

#### `get_user_logs(user_id, log_date=None) → list[dict]`
Записи сотрудника за конкретный день. Если дата не указана — возвращает **сегодняшние** записи.

```python
from api_functions import get_user_logs

today  = get_user_logs(user_id=1)
past   = get_user_logs(user_id=1, log_date="2025-01-10")
# [{"log_id": 3, "log_date": "...", "hours": 3.5, "project_name": "...", ...}, ...]
```

---

#### `get_hr_dashboard_stats(weeks_back=1) → list[dict]`
Сводная таблица для HR: кто, над чем, сколько часов за последние N недель.

```python
from api_functions import get_hr_dashboard_stats
import pandas as pd

stats = get_hr_dashboard_stats()       # последние 7 дней
df    = pd.DataFrame(stats)
# Колонки: user_name, project_name, total_hours, days_worked

# В Streamlit:
# st.dataframe(df)
# st.bar_chart(df.set_index("user_name")["total_hours"])
```

---

#### `delete_time_log(log_id) → bool`
Удаляет запись по ID. Возвращает `True` если удалена, `False` если не найдена.

```python
from api_functions import delete_time_log
deleted = delete_time_log(log_id=3)
```

---

### `ai_parser.py`

#### `parse_text_to_json(user_text, system_prompt=None) → dict`
Парсит свободный текст через LLM и возвращает структурированный словарь.

```python
from ai_parser import parse_text_to_json

result = parse_text_to_json("Сегодня 4 часа занимался редизайном главной страницы")
# → {"project_id": 1, "hours": 4.0, "raw_text": "Сегодня 4 часа..."}

# Используем результат для сохранения в БД:
from api_functions import save_time_log
from datetime import date

save_time_log(
    user_id=current_user_id,
    project_id=result["project_id"] or 1,   # fallback если AI не распознал
    log_date=str(date.today()),
    hours=result["hours"],
    raw_text=result["raw_text"],
)
```

**Обработка ошибок:**
```python
try:
    result = parse_text_to_json(user_text)
except ValueError as e:
    # LLM вернул невалидный JSON
    st.error(f"AI не смог распознать текст: {e}")
except RuntimeError as e:
    # Проблема с API (сеть, ключ, лимиты)
    st.error(f"Ошибка связи с AI: {e}")
```

---

## Типичный Streamlit-сценарий

```python
import streamlit as st
from datetime import date
from api_functions import get_all_projects, save_time_log, get_hr_dashboard_stats
from ai_parser import parse_text_to_json

# 1. Получить текст от пользователя
user_text = st.text_area("Что делал сегодня?")

if st.button("Сохранить"):
    # 2. Распарсить через AI
    try:
        parsed = parse_text_to_json(user_text)
        project_id = parsed["project_id"]
        hours      = parsed["hours"]
    except Exception:
        # 3. Fallback — показать выпадающий список
        projects   = get_all_projects(status="active")
        project_id = st.selectbox("Проект", [p["id"] for p in projects])
        hours      = st.number_input("Часы", min_value=0.5, max_value=24.0)

    # 4. Сохранить
    save_time_log(
        user_id=st.session_state["user_id"],
        project_id=project_id,
        log_date=str(date.today()),
        hours=hours,
        raw_text=user_text,
    )
    st.success("Сохранено!")

# 5. Показать дашборд
st.subheader("HR-статистика за неделю")
st.dataframe(get_hr_dashboard_stats())
```

---

## Примечания

- `worktime.db` можно открыть любым SQLite-просмотрщиком (например, [DB Browser for SQLite](https://sqlitebrowser.org/)).
- Функция `parse_text_to_json` безопасно обрабатывает ошибки — интерфейс не сломается, даже если AI не ответит.
- Для сброса тестовых данных просто удалите `worktime.db` и запустите `python database.py` повторно.
