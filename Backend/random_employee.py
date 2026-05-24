"""Генерация одного реалистичного сотрудника со случайными событиями.

Логика подбирается так, чтобы расчётные показатели попали в живые диапазоны:
- загрузка (L)        — 60..110 %
- конфликты (C)       — 0..40 %
- актуальность (A)    — 0.4..1.0  (через last_update)
"""
import random
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

import models
from tasks_pool import random_task, random_history

FIRST_NAMES_M = ["Александр", "Михаил", "Дмитрий", "Артём", "Сергей", "Никита", "Илья", "Роман", "Кирилл", "Антон"]
FIRST_NAMES_F = ["Анна", "Мария", "Ольга", "Елена", "Дарья", "Ирина", "Юлия", "Ксения", "Светлана", "Татьяна"]
LAST_NAMES_M = ["Смирнов", "Иванов", "Кузнецов", "Петров", "Соколов", "Новиков", "Морозов", "Васильев", "Зайцев", "Павлов"]
LAST_NAMES_F = ["Смирнова", "Иванова", "Кузнецова", "Петрова", "Соколова", "Новикова", "Морозова", "Васильева", "Зайцева", "Павлова"]
PATRONYMICS_M = ["Александрович", "Сергеевич", "Иванович", "Дмитриевич", "Михайлович", "Андреевич"]
PATRONYMICS_F = ["Александровна", "Сергеевна", "Ивановна", "Дмитриевна", "Михайловна", "Андреевна"]

POSITIONS = [
    "Backend Developer", "Frontend Developer", "QA Engineer", "DevOps Engineer",
    "Project Manager", "Product Manager", "UI/UX Designer", "Data Analyst",
    "Tech Lead", "Бизнес-аналитик", "ML Engineer",
]

WORK_FORMATS = ["office", "remote", "hybrid"]
TIMEZONES = ["UTC+2", "UTC+3", "UTC+5", "UTC+7", "UTC+0"]
WORK_RANGES = [("09:00", "18:00"), ("10:00", "19:00"), ("11:00", "20:00"), ("08:00", "17:00")]

MEETING_TITLES = [
    "Синхронизация команды", "1-на-1 с тимлидом", "Спринт-ревью", "Планирование",
    "Демо для бизнеса", "Архитектурный созвон", "Daily Standup", "Дизайн-ревью",
    "Грумминг бэклога", "Звонок с клиентом",
]


def _transliterate(name: str) -> str:
    table = {
        "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z",
        "и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r",
        "с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch",
        "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"," ":".",
    }
    return "".join(table.get(c.lower(), "") for c in name)


def create_random_employee(db: Session, team_id: int) -> models.Employee:
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise ValueError("Команда не найдена")

    is_male = random.random() < 0.5
    if is_male:
        first = random.choice(FIRST_NAMES_M)
        last = random.choice(LAST_NAMES_M)
        patron = random.choice(PATRONYMICS_M)
    else:
        first = random.choice(FIRST_NAMES_F)
        last = random.choice(LAST_NAMES_F)
        patron = random.choice(PATRONYMICS_F)

    full_name = f"{last} {first} {patron}"
    work_format = random.choice(WORK_FORMATS)
    work_start, work_end = random.choice(WORK_RANGES)

    days_since_update = random.randint(2, 140)  # разнообразная актуальность
    last_update = datetime.utcnow() - timedelta(days=days_since_update)

    # Уникальный email с эпохой, чтобы не словить UNIQUE constraint
    email_local = _transliterate(f"{first}.{last}").strip(".") or "user"
    email = f"{email_local}.{int(datetime.utcnow().timestamp())}{random.randint(10,99)}@example.com"

    employee = models.Employee(
        team_id=team_id,
        name=full_name,
        email=email,
        position=random.choice(POSITIONS),
        work_days="mon,tue,wed,thu,fri",
        work_start=work_start,
        work_end=work_end,
        timezone=random.choice(TIMEZONES),
        work_format=work_format,
        last_update=last_update,
        current_task=random_task(),
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    # История задач (3 прошлые задачи)
    now_dt = datetime.utcnow()
    past_tasks = random_history(3)
    for i, t in enumerate(past_tasks, start=1):
        db.add(models.TaskHistory(
            employee_id=employee.id,
            text=t,
            started_at=now_dt - timedelta(days=14 * i + random.randint(0, 5)),
            ended_at=now_dt - timedelta(days=14 * (i - 1) + random.randint(0, 4)),
        ))
    # Текущая задача — открытая запись
    db.add(models.TaskHistory(
        employee_id=employee.id,
        text=employee.current_task,
        started_at=now_dt - timedelta(days=random.randint(1, 10)),
        ended_at=None,
    ))
    db.commit()

    # ===== Реалистичные события =====
    # Целевая загрузка 60..110 %, конфликты 0..40 %
    target_load = random.uniform(0.6, 1.1)
    target_conflict = random.uniform(0.0, 0.4)

    sh = int(work_start.split(":")[0])
    eh = int(work_end.split(":")[0])
    work_hours = max(1, eh - sh)
    # 22 рабочих дня по work_hours часов
    target_busy_seconds = int(target_load * 22 * work_hours * 3600)

    # Парсим часовой пояс, чтобы корректно записывать UTC start_time
    try:
        tz_offset = int(employee.timezone.replace("UTC", ""))
    except ValueError:
        tz_offset = 0

    events = []
    today = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    accumulated = 0
    safety_counter = 0

    # Сколько встреч хотим — где-то 8..16
    target_event_count = random.randint(8, 16)
    avg_seconds = max(30 * 60, target_busy_seconds // target_event_count)

    while accumulated < target_busy_seconds and len(events) < target_event_count and safety_counter < 200:
        safety_counter += 1
        day_offset = random.randint(-10, 5)  # часть в прошлом, часть в будущем
        day_dt = today + timedelta(days=day_offset)
        if day_dt.weekday() >= 5:
            continue  # пропускаем выходные
        # Доля встреч вне рабочего времени = target_conflict
        outside_hours = random.random() < target_conflict
        if outside_hours:
            hour_local = random.choice(list(range(0, sh)) + list(range(eh, 23)))
        else:
            hour_local = random.randint(sh, max(sh, eh - 1))

        duration_seconds = int(random.uniform(avg_seconds * 0.6, avg_seconds * 1.4))
        start_utc_hour = (hour_local - tz_offset) % 24
        start = day_dt.replace(hour=start_utc_hour)
        end = start + timedelta(seconds=duration_seconds)

        events.append(models.Event(
            employee_id=employee.id,
            title=random.choice(MEETING_TITLES),
            start_time=start,
            end_time=end,
            event_type="meeting",
            source="calendar",
        ))
        accumulated += duration_seconds

    # Иногда добавим отпуск или больничный, чтобы профиль играл
    extra_roll = random.random()
    if extra_roll < 0.25:
        start = today + timedelta(days=random.randint(1, 3))
        end = start + timedelta(days=random.randint(2, 7))
        events.append(models.Event(
            employee_id=employee.id,
            title="Отпуск",
            start_time=start.replace(hour=0),
            end_time=end.replace(hour=23),
            event_type="vacation",
            source="hr_system",
        ))
    elif extra_roll < 0.4:
        start = today + timedelta(days=random.randint(0, 2))
        end = start + timedelta(days=random.randint(1, 3))
        events.append(models.Event(
            employee_id=employee.id,
            title="Больничный",
            start_time=start.replace(hour=0),
            end_time=end.replace(hour=23),
            event_type="sick_leave",
            source="hr_system",
        ))

    db.add_all(events)

    # История графика
    db.add_all([
        models.HistoryEvent(
            employee_id=employee.id,
            happened_at=last_update,
            title="График подтверждён" if days_since_update < 60 else "Последнее подтверждение графика",
            description="" if days_since_update < 60 else "Сотрудник давно не обновлял данные.",
            icon="fa-circle-check" if days_since_update < 60 else "fa-triangle-exclamation",
        ),
        models.HistoryEvent(
            employee_id=employee.id,
            happened_at=datetime.utcnow() - timedelta(days=random.randint(60, 300)),
            title="Сотрудник добавлен в команду",
            description="Онбординг завершён.",
            icon="fa-user-plus",
        ),
    ])
    db.commit()
    return employee
