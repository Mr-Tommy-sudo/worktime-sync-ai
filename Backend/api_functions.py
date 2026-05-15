"""
api_functions.py — Функции для работы с БД. Вызываются из Streamlit-интерфейса.

Быстрый старт для BI-аналитика:
    from api_functions import get_all_projects, save_time_log, get_user_logs, get_hr_dashboard_stats

    projects = get_all_projects()
    logs     = get_user_logs(user_id=1, date="2025-01-15")
    stats    = get_hr_dashboard_stats()

Все функции возвращают списки Python-словарей (list[dict]) — удобно для
pandas.DataFrame(result) или st.dataframe(result) в Streamlit.
"""

import sqlite3
from datetime import date, timedelta
from typing import Optional

from Backend.database import get_connection, init_db


# ─── Вспомогательная функция ──────────────────────────────────────────────────

def _rows_to_dicts(cursor: sqlite3.Cursor) -> list[dict]:
    """Конвертирует sqlite3.Row-объекты в обычные Python-словари."""
    return [dict(row) for row in cursor.fetchall()]


# ─── 1. Проекты ───────────────────────────────────────────────────────────────

def get_all_projects(status: Optional[str] = None) -> list[dict]:
    """
    Возвращает список всех проектов (для выпадающего списка в Streamlit).

    Args:
        status: Фильтр по статусу — "active" | "completed" | "paused" | None (все).

    Returns:
        [{"id": 1, "name": "Редизайн сайта", "description": "...", "status": "active"}, ...]

    Пример:
        projects = get_all_projects()
        active   = get_all_projects(status="active")
    """
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT id, name, description, status FROM projects WHERE status = ? ORDER BY name",
                (status,),
            )
        else:
            rows = conn.execute(
                "SELECT id, name, description, status FROM projects ORDER BY name"
            )
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_project_by_id(project_id: int) -> Optional[dict]:
    """
    Возвращает один проект по ID или None, если не найден.

    Пример:
        project = get_project_by_id(1)
        # → {"id": 1, "name": "Редизайн сайта", ...}
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, description, status FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ─── 2. Пользователи ─────────────────────────────────────────────────────────

def get_all_users() -> list[dict]:
    """
    Возвращает список всех сотрудников.

    Returns:
        [{"id": 1, "name": "Алексей Петров", "email": "...", "role": "employee"}, ...]

    Пример:
        users = get_all_users()
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, email, role FROM users ORDER BY name"
        )
        return _rows_to_dicts(rows)
    finally:
        conn.close()


# ─── 3. Записи времени — запись ───────────────────────────────────────────────

def save_time_log(
    user_id: int,
    project_id: int,
    log_date: str,
    hours: float,
    raw_text: Optional[str] = None,
) -> int:
    """
    Сохраняет новую запись рабочего времени в БД (INSERT).

    Args:
        user_id:    ID сотрудника (из таблицы users).
        project_id: ID проекта (из таблицы projects).
        log_date:   Дата в формате "YYYY-MM-DD", например "2025-01-15".
        hours:      Количество часов (дробное, > 0 и ≤ 24).
        raw_text:   Исходный текст пользователя от AI-парсера (опционально).

    Returns:
        int: ID созданной записи.

    Raises:
        ValueError:  Если hours вне диапазона (0, 24].
        RuntimeError: Если user_id или project_id не существуют в БД.

    Пример (в Streamlit, после получения данных от AI):
        new_id = save_time_log(
            user_id=1,
            project_id=2,
            log_date="2025-01-15",
            hours=3.5,
            raw_text="Настраивал CRM 3.5 часа",
        )
    """
    if not (0 < hours <= 24):
        raise ValueError(f"hours должно быть в диапазоне (0, 24], получено: {hours}")

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO time_logs (user_id, project_id, log_date, hours, raw_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, project_id, log_date, hours, raw_text),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise RuntimeError(
            f"Ошибка FK: user_id={user_id} или project_id={project_id} не существуют. {exc}"
        ) from exc
    finally:
        conn.close()


# ─── 4. Записи времени — чтение ───────────────────────────────────────────────

def get_user_logs(
    user_id: int,
    log_date: Optional[str] = None,
) -> list[dict]:
    """
    Возвращает записи конкретного сотрудника за указанную дату.
    Если дата не указана — возвращает записи за сегодня.

    Args:
        user_id:  ID сотрудника.
        log_date: Дата в формате "YYYY-MM-DD". По умолчанию — сегодня.

    Returns:
        [
          {
            "log_id": 3,
            "log_date": "2025-01-15",
            "hours": 3.5,
            "raw_text": "...",
            "project_name": "CRM-интеграция",
            "user_name": "Алексей Петров"
          },
          ...
        ]

    Пример:
        today_logs = get_user_logs(user_id=1)
        past_logs  = get_user_logs(user_id=1, log_date="2025-01-10")
    """
    target_date = log_date or str(date.today())

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                tl.id          AS log_id,
                tl.log_date,
                tl.hours,
                tl.raw_text,
                p.name         AS project_name,
                u.name         AS user_name
            FROM time_logs tl
            JOIN projects p ON p.id = tl.project_id
            JOIN users    u ON u.id = tl.user_id
            WHERE tl.user_id = ? AND tl.log_date = ?
            ORDER BY tl.created_at DESC
            """,
            (user_id, target_date),
        )
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_all_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Возвращает все записи времени с фильтрацией по диапазону дат.

    Args:
        start_date: Начало диапазона "YYYY-MM-DD" (включительно).
        end_date:   Конец диапазона "YYYY-MM-DD" (включительно).

    Пример:
        all_logs  = get_all_logs()
        week_logs = get_all_logs(start_date="2025-01-13", end_date="2025-01-19")
    """
    conn = get_connection()
    try:
        query = """
            SELECT
                tl.id          AS log_id,
                u.name         AS user_name,
                p.name         AS project_name,
                tl.log_date,
                tl.hours,
                tl.raw_text
            FROM time_logs tl
            JOIN projects p ON p.id = tl.project_id
            JOIN users    u ON u.id = tl.user_id
            WHERE 1=1
        """
        params: list = []

        if start_date:
            query += " AND tl.log_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND tl.log_date <= ?"
            params.append(end_date)

        query += " ORDER BY tl.log_date DESC, u.name"
        return _rows_to_dicts(conn.execute(query, params))
    finally:
        conn.close()


# ─── 5. HR-дашборд ────────────────────────────────────────────────────────────

def get_hr_dashboard_stats(weeks_back: int = 1) -> list[dict]:
    """
    Сводная таблица для HR / менеджера: имя сотрудника, проект, сумма часов за неделю.

    Args:
        weeks_back: Сколько недель назад считать. 1 = текущая и прошлая неделя (7 дней).

    Returns:
        [
          {
            "user_name": "Алексей Петров",
            "project_name": "CRM-интеграция",
            "total_hours": 7.5,
            "days_worked": 2
          },
          ...
        ]
        Отсортировано: сначала сотрудник с наибольшим суммарным временем.

    Пример в Streamlit:
        import pandas as pd
        stats = get_hr_dashboard_stats()
        df    = pd.DataFrame(stats)
        st.dataframe(df)
    """
    start = str(date.today() - timedelta(weeks=weeks_back))
    end   = str(date.today())

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                u.name              AS user_name,
                p.name              AS project_name,
                ROUND(SUM(tl.hours), 2) AS total_hours,
                COUNT(DISTINCT tl.log_date) AS days_worked
            FROM time_logs tl
            JOIN users    u ON u.id = tl.user_id
            JOIN projects p ON p.id = tl.project_id
            WHERE tl.log_date BETWEEN ? AND ?
            GROUP BY u.id, p.id
            ORDER BY total_hours DESC, u.name, p.name
            """,
            (start, end),
        )
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_user_weekly_summary(user_id: int) -> dict:
    """
    Итоговая сводка по одному сотруднику за текущую неделю.

    Returns:
        {
          "user_name": "Мария Соколова",
          "total_hours": 8.5,
          "days_worked": 2,
          "logs": [...]   # все записи за неделю
        }

    Пример:
        summary = get_user_weekly_summary(user_id=2)
    """
    start = str(date.today() - timedelta(days=7))
    end   = str(date.today())

    conn = get_connection()
    try:
        totals = conn.execute(
            """
            SELECT
                u.name              AS user_name,
                ROUND(SUM(tl.hours), 2) AS total_hours,
                COUNT(DISTINCT tl.log_date) AS days_worked
            FROM time_logs tl
            JOIN users u ON u.id = tl.user_id
            WHERE tl.user_id = ? AND tl.log_date BETWEEN ? AND ?
            GROUP BY u.id
            """,
            (user_id, start, end),
        ).fetchone()

        logs = get_all_logs(start_date=start, end_date=end)
        user_logs = [log for log in logs if True]  # уже отфильтровано ниже

        user_logs = conn.execute(
            """
            SELECT tl.log_date, tl.hours, p.name AS project_name, tl.raw_text
            FROM time_logs tl
            JOIN projects p ON p.id = tl.project_id
            WHERE tl.user_id = ? AND tl.log_date BETWEEN ? AND ?
            ORDER BY tl.log_date DESC
            """,
            (user_id, start, end),
        )

        result = dict(totals) if totals else {"user_name": "—", "total_hours": 0, "days_worked": 0}
        result["logs"] = _rows_to_dicts(user_logs)
        return result
    finally:
        conn.close()


# ─── 6. Удаление записи ───────────────────────────────────────────────────────

def delete_time_log(log_id: int) -> bool:
    """
    Удаляет запись по её ID.

    Returns:
        True — запись удалена, False — запись не найдена.

    Пример:
        deleted = delete_time_log(log_id=3)
    """
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM time_logs WHERE id = ?", (log_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ─── Быстрый тест при запуске напрямую ───────────────────────────────────────

if __name__ == "__main__":
    import json

    # Убеждаемся, что БД инициализирована
    init_db()

    print("=== get_all_projects() ===")
    print(json.dumps(get_all_projects(), ensure_ascii=False, indent=2))

    print("\n=== get_all_users() ===")
    print(json.dumps(get_all_users(), ensure_ascii=False, indent=2))

    print("\n=== get_user_logs(user_id=1) ===")
    print(json.dumps(get_user_logs(user_id=1), ensure_ascii=False, indent=2))

    print("\n=== get_hr_dashboard_stats() ===")
    print(json.dumps(get_hr_dashboard_stats(), ensure_ascii=False, indent=2))

    print("\n=== Тест save_time_log() ===")
    new_id = save_time_log(
        user_id=1,
        project_id=1,
        log_date=str(date.today()),
        hours=1.5,
        raw_text="Тестовая запись через api_functions",
    )
    print(f"Создана запись с ID={new_id}")
