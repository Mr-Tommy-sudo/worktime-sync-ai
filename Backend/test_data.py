from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import models
from random_employee import create_random_employee
from tasks_pool import random_task, random_history


def generate_mvp_data(db: Session):
    """Очищает БД и наполняет демо-командой + событиями + логами агента + историей.

    Метрики (загрузка/конфликты) у разных сотрудников разные и реалистичные —
    встречи генерируются так, чтобы расчёт сам выдавал нужные диапазоны."""
    db.query(models.ActivityLog).delete()
    db.query(models.HistoryEvent).delete()
    db.query(models.Event).delete()
    db.query(models.Employee).delete()
    db.query(models.Team).delete()
    db.commit()

    # 1. Команда
    team = models.Team(name="Backend Development")
    db.add(team)
    db.commit()
    db.refresh(team)

    now = datetime.utcnow()

    # 2. Базовые сотрудники с разными «сюжетами» для жюри
    employees_seed = [
        dict(
            name="Иван Иванов", email="ivan@test.com", position="Senior Backend Developer",
            work_start="09:00", work_end="18:00", timezone="UTC+3", work_format="office",
            last_update=now - timedelta(days=5),
            target_load=0.72, target_conflict=0.05,  # норма
        ),
        dict(
            name="Анна Смирнова", email="anna@test.com", position="Backend Developer",
            work_start="10:00", work_end="19:00", timezone="UTC+3", work_format="remote",
            last_update=now - timedelta(days=95),
            target_load=0.95, target_conflict=0.32,  # устаревший график + конфликты
        ),
        dict(
            name="Пётр Петров", email="petr@test.com", position="Tech Lead",
            work_start="09:00", work_end="18:00", timezone="UTC+5", work_format="hybrid",
            last_update=now - timedelta(days=12),
            target_load=1.05, target_conflict=0.18,  # перегруз
        ),
        dict(
            name="Елена Соколова", email="elena@test.com", position="Junior Developer",
            work_start="11:00", work_end="20:00", timezone="UTC+3", work_format="remote",
            last_update=now - timedelta(days=2),
            target_load=0.62, target_conflict=0.40,  # частые ранние созвоны
        ),
    ]

    employees = []
    for seed in employees_seed:
        emp = models.Employee(
            team_id=team.id,
            name=seed["name"], email=seed["email"], position=seed["position"],
            work_days="mon,tue,wed,thu,fri",
            work_start=seed["work_start"], work_end=seed["work_end"],
            timezone=seed["timezone"], work_format=seed["work_format"],
            last_update=seed["last_update"],
            current_task=random_task(),
        )
        db.add(emp)
        employees.append((emp, seed))
    db.commit()

    # 3. Реалистичные события на основе target_load / target_conflict
    today = now.replace(minute=0, second=0, microsecond=0)
    event_titles = [
        "Синхронизация команды", "Архитектурный созвон", "1-на-1 с тимлидом",
        "Спринт-ревью", "Daily Standup", "Грумминг бэклога",
        "Демо для бизнеса", "Дизайн-ревью", "Звонок с клиентом",
    ]

    events = []
    for emp, seed in employees:
        sh = int(seed["work_start"].split(":")[0])
        eh = int(seed["work_end"].split(":")[0])
        work_hours = max(1, eh - sh)
        target_busy = int(seed["target_load"] * 22 * work_hours * 3600)
        target_count = random.randint(8, 14)
        avg = max(30 * 60, target_busy // target_count)

        # Часовой пояс сотрудника, чтобы корректно записывать UTC start_time
        tz_str = seed["timezone"]
        try:
            tz_offset = int(tz_str.replace("UTC", "")) if tz_str else 0
        except ValueError:
            tz_offset = 0

        accumulated = 0
        guard = 0
        while accumulated < target_busy and len(events) < 1_000 and guard < 200:
            guard += 1
            day_offset = random.randint(-10, 5)
            day_dt = today + timedelta(days=day_offset)
            # Только рабочие дни (понедельник..пятница), чтобы конфликты считались честно
            if day_dt.weekday() >= 5:
                continue
            outside = random.random() < seed["target_conflict"]
            if outside:
                hour_local = random.choice(list(range(0, sh)) + list(range(eh, 23)))
            else:
                hour_local = random.randint(sh, max(sh, eh - 1))
            duration = int(random.uniform(avg * 0.6, avg * 1.4))
            # Пишем UTC start_time: local_hour - tz_offset
            start_utc_hour = (hour_local - tz_offset) % 24
            start = day_dt.replace(hour=start_utc_hour)
            events.append(models.Event(
                employee_id=emp.id,
                title=random.choice(event_titles),
                start_time=start, end_time=start + timedelta(seconds=duration),
                event_type="meeting", source="calendar",
            ))
            accumulated += duration

    # Анна — больничный завтра-послезавтра
    anna = next(e for e, _ in employees if e.email == "anna@test.com")
    sick_start = today + timedelta(days=1, hours=-today.hour)
    sick_end = sick_start + timedelta(days=2)
    events.append(models.Event(
        employee_id=anna.id, title="Больничный",
        start_time=sick_start, end_time=sick_end,
        event_type="sick_leave", source="hr_system",
    ))

    # Иван — отпуск через неделю
    ivan = next(e for e, _ in employees if e.email == "ivan@test.com")
    vac_start = today + timedelta(days=7, hours=-today.hour)
    vac_end = vac_start + timedelta(days=14)
    events.append(models.Event(
        employee_id=ivan.id, title="Отпуск",
        start_time=vac_start, end_time=vac_end,
        event_type="vacation", source="hr_system",
    ))

    db.add_all(events)

    # 4. Фейковые логи TrackerAgent (для красивого Stacked Bar)
    activity_profiles = {
        ivan.id: [
            ("Visual Studio Code", "main.py — worktime",  4 * 3600 + 30 * 60),
            ("Telegram",           "Backend Chat",        1 * 3600 + 30 * 60),
            ("Figma",              "Дашборд UI",          45 * 60),
            ("Google Meet",        "Daily Standup",       45 * 60),
        ],
        anna.id: [
            ("Visual Studio Code", "schemas.py",          3 * 3600 + 15 * 60),
            ("Slack",              "Threads",             1 * 3600),
            ("Notion",             "Tech Spec",           40 * 60),
            ("Google Chrome",      "Stack Overflow",      1 * 3600),
        ],
    }
    petr = next(e for e, _ in employees if e.email == "petr@test.com")
    elena = next(e for e, _ in employees if e.email == "elena@test.com")
    activity_profiles[petr.id] = [
        ("Google Meet",        "Strategy",            3 * 3600),
        ("Outlook",            "Inbox",               2 * 3600),
        ("Jira",               "Sprint Board",        1 * 3600 + 30 * 60),
        ("Visual Studio Code", "review",              45 * 60),
    ]
    activity_profiles[elena.id] = [
        ("Visual Studio Code", "Onboarding repo",     2 * 3600),
        ("Telegram",           "Mentor Chat",         1 * 3600 + 20 * 60),
        ("YouTrack",           "Tasks",               50 * 60),
        ("Discord",            "Voice Channel",       30 * 60),
    ]

    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    logs = []
    for emp_id, apps in activity_profiles.items():
        for day_offset in range(0, 7):
            day_anchor = today0 - timedelta(days=day_offset) + timedelta(hours=9)
            for app_name, win_title, base_seconds in apps:
                jitter = random.uniform(0.85, 1.15) if day_offset > 0 else 1.0
                seconds = int(base_seconds * jitter)
                if seconds <= 0:
                    continue
                logs.append(models.ActivityLog(
                    employee_id=emp_id, app_name=app_name,
                    window_title=win_title, duration_seconds=seconds,
                    logged_at=day_anchor,
                ))
                day_anchor += timedelta(seconds=seconds)
    db.add_all(logs)

    # 5. История графика (Timeline)
    history = [
        models.HistoryEvent(employee_id=ivan.id,  happened_at=now - timedelta(days=5),
            title="График подтверждён", description="Сотрудник подтвердил актуальность.",
            icon="fa-circle-check"),
        models.HistoryEvent(employee_id=ivan.id,  happened_at=now - timedelta(days=40),
            title="Изменён формат работы", description="С удалёнки на офис.",
            icon="fa-arrows-rotate"),
        models.HistoryEvent(employee_id=ivan.id,  happened_at=now - timedelta(days=120),
            title="Добавлен отпуск", description="Две недели в августе.",
            icon="fa-umbrella-beach"),

        models.HistoryEvent(employee_id=anna.id,  happened_at=now - timedelta(days=95),
            title="Последнее подтверждение графика", description="Сотрудник давно не обновлял данные.",
            icon="fa-triangle-exclamation"),
        models.HistoryEvent(employee_id=anna.id,  happened_at=now - timedelta(days=200),
            title="Изменён часовой пояс", description="Переезд в другой город.",
            icon="fa-earth-europe"),

        models.HistoryEvent(employee_id=petr.id,  happened_at=now - timedelta(days=12),
            title="График подтверждён", description="", icon="fa-circle-check"),
        models.HistoryEvent(employee_id=petr.id,  happened_at=now - timedelta(days=60),
            title="Изменён формат работы", description="Переход на гибрид.",
            icon="fa-arrows-rotate"),

        models.HistoryEvent(employee_id=elena.id, happened_at=now - timedelta(days=2),
            title="График подтверждён", description="", icon="fa-circle-check"),
        models.HistoryEvent(employee_id=elena.id, happened_at=now - timedelta(days=15),
            title="Сотрудник добавлен в команду", description="Онбординг завершён.",
            icon="fa-user-plus"),
    ]
    db.add_all(history)

    # Истории задач для seed-сотрудников
    now_dt = datetime.utcnow()
    for emp, _seed in employees:
        past = random_history(3)
        for i, t in enumerate(past, start=1):
            db.add(models.TaskHistory(
                employee_id=emp.id,
                text=t,
                started_at=now_dt - timedelta(days=14 * i + random.randint(0, 5)),
                ended_at=now_dt - timedelta(days=14 * (i - 1) + random.randint(0, 4)),
            ))
        db.add(models.TaskHistory(
            employee_id=emp.id,
            text=emp.current_task,
            started_at=now_dt - timedelta(days=random.randint(1, 10)),
            ended_at=None,
        ))

    # Очистим таблицу task_history тоже при regenerate (на всякий)
    db.commit()
    print("✅ Синтетические данные для MVP успешно сгенерированы!")
