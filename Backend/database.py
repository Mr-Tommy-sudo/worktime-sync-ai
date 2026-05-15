"""
database.py — Инициализация БД и заполнение тестовыми данными.

Использование:
    python database.py          # создаёт worktime.db и наполняет mock-данными
    from database import init_db
    init_db()                   # только создание таблиц (без mock-данных)
"""

import sqlite3
import os
from datetime import date, timedelta

DB_PATH = "worktime.db"


def get_connection() -> sqlite3.Connection:
    """Возвращает соединение с БД. Row-factory даёт доступ к колонкам по имени."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """
    Создаёт файл worktime.db и все необходимые таблицы (если они ещё не существуют).

    Таблицы:
        users      — сотрудники
        projects   — проекты компании
        time_logs  — записи рабочего времени
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ── users ──────────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            email      TEXT    NOT NULL UNIQUE,
            role       TEXT    NOT NULL DEFAULT 'employee',  -- 'employee' | 'manager' | 'admin'
            created_at TEXT    NOT NULL DEFAULT (date('now'))
        )
    """)

    # ── projects ───────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            description TEXT,
            status      TEXT    NOT NULL DEFAULT 'active',   -- 'active' | 'completed' | 'paused'
            created_at  TEXT    NOT NULL DEFAULT (date('now'))
        )
    """)

    # ── time_logs ──────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS time_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            log_date   TEXT    NOT NULL,   -- формат: YYYY-MM-DD
            hours      REAL    NOT NULL CHECK (hours > 0 AND hours <= 24),
            raw_text   TEXT,               -- исходная фраза пользователя (от AI-парсера)
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Таблицы созданы / уже существуют → {DB_PATH}")


def seed_mock_data() -> None:
    """
    Наполняет БД фейковыми данными для BI-аналитика.
    Запускается только если таблицы пустые, чтобы не дублировать данные.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Проверяем, есть ли уже данные
    if cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        print("[DB] Mock-данные уже есть, пропускаем заполнение.")
        conn.close()
        return

    # ── Users ──────────────────────────────────────────────────────────────────
    users = [
        ("Алексей Петров",   "a.petrov@company.ru",   "employee"),
        ("Мария Соколова",   "m.sokolova@company.ru",  "employee"),
        ("Дмитрий Иванов",   "d.ivanov@company.ru",    "manager"),
    ]
    cursor.executemany(
        "INSERT INTO users (name, email, role) VALUES (?, ?, ?)", users
    )

    # ── Projects ───────────────────────────────────────────────────────────────
    projects = [
        ("Редизайн сайта",        "Полный редизайн корпоративного сайта",          "active"),
        ("CRM-интеграция",        "Интеграция новой CRM-системы с 1С",             "active"),
        ("Мобильное приложение",  "MVP мобильного приложения для клиентов",        "active"),
    ]
    cursor.executemany(
        "INSERT INTO projects (name, description, status) VALUES (?, ?, ?)", projects
    )

    # ── Time logs (последние 7 дней) ────────────────────────────────────────────
    today = date.today()
    logs = [
        # (user_id, project_id, log_date,                              hours, raw_text)
        (1, 1, str(today - timedelta(days=1)), 4.0,  "Работал над макетами главной страницы 4 часа"),
        (1, 2, str(today - timedelta(days=1)), 3.5,  "Настройка коннектора CRM, 3.5 часа"),
        (2, 1, str(today - timedelta(days=2)), 6.0,  "Вёрстка нового лендинга весь день, примерно 6 часов"),
        (2, 3, str(today - timedelta(days=1)), 2.5,  "Ревью дизайна мобилки 2.5 часа"),
        (3, 2, str(today - timedelta(days=3)), 5.0,  "Встречи и планирование интеграции — 5 часов"),
        (3, 3, str(today - timedelta(days=2)), 3.0,  "Написал тест-кейсы для мобилки — 3 часа"),
        (1, 3, str(today),                    2.0,  "Сегодня занимался API мобильного приложения 2 часа"),
    ]
    cursor.executemany(
        "INSERT INTO time_logs (user_id, project_id, log_date, hours, raw_text) VALUES (?, ?, ?, ?, ?)",
        logs,
    )

    conn.commit()
    conn.close()
    print("[DB] Mock-данные успешно загружены (3 пользователя, 3 проекта, 7 записей).")


if __name__ == "__main__":
    init_db()
    seed_mock_data()
    print(f"[DB] База данных готова: {os.path.abspath(DB_PATH)}")
