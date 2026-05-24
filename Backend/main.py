from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from database import SessionLocal, engine, Base
import models, schemas, calculations, ai_assistant
from activity_palette import normalize as normalize_app, format_minutes

# Создаем таблицы в БД
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WorkTime Sync API", 
    description="Интеллектуальная система актуализации рабочего времени (Кейс №3)"
)

# Разрешаем браузеру (фронтенду) общаться с бэкендом
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# 1. СИНТЕТИЧЕСКИЕ ДАННЫЕ (ДЛЯ MVP)
# ==========================================
@app.post("/generate_test_data/")
def generate_test_data(db: Session = Depends(get_db)):
    """Очищает БД и генерирует тестовую команду из кейса"""
    from test_data import generate_mvp_data
    generate_mvp_data(db)
    return {"message": "Синтетические данные для MVP успешно сгенерированы"}


@app.get("/api/teams")
def list_teams(db: Session = Depends(get_db)):
    """Список всех команд (для селектора в UI)."""
    teams = db.query(models.Team).all()
    result = [
        {"id": t.id, "name": t.name, "members_count": sum(1 for e in t.employees if (e.status or "active") == "active")}
        for t in teams
    ]
    # Виртуальная команда «В резерве» — id=0
    reserve_count = db.query(models.Employee).filter(models.Employee.status == "reserve").count()
    result.append({"id": 0, "name": "В резерве", "members_count": reserve_count})
    return result


@app.get("/api/reserve")
def list_reserve(db: Session = Depends(get_db)):
    """Сотрудники в статусе reserve (свободные / отпущенные)."""
    rows = db.query(models.Employee).filter(models.Employee.status == "reserve").all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "position": e.position,
            "work_format": e.work_format,
            "timezone": e.timezone,
            "current_task": e.current_task or "",
            "team_id": e.team_id,
        }
        for e in rows
    ]


@app.post("/api/teams")
def create_team(payload: schemas.TeamCreate, db: Session = Depends(get_db)):
    """Создание новой команды."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название команды не может быть пустым")
    existing = db.query(models.Team).filter(models.Team.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Команда с таким названием уже существует")
    team = models.Team(name=name)
    db.add(team)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "name": team.name, "members_count": 0}


@app.post("/api/employees/random")
def create_random_employee(payload: schemas.RandomEmployeeRequest, db: Session = Depends(get_db)):
    """Создаёт сотрудника со случайными реалистичными данными и событиями."""
    from random_employee import create_random_employee as _gen
    try:
        emp = _gen(db, payload.team_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": emp.id,
        "name": emp.name,
        "position": emp.position,
        "work_format": emp.work_format,
        "timezone": emp.timezone,
        "team_id": emp.team_id,
    }


# ==========================================
# 2. КОМПЛЕКСНЫЙ ДАШБОРД (ДЛЯ ФРОНТЕНДА)
# ==========================================
@app.get("/api/dashboard/team/{team_id}")
def get_team_dashboard(team_id: int, db: Session = Depends(get_db)):
    """Отдает всю информацию по команде за один запрос (удобно для UI)"""
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Команда не найдена")

    dashboard_data = []
    events_dict = {}

    active_employees = [e for e in team.employees if (e.status or "active") == "active"]

    # Собираем события для ИИ
    for emp in active_employees:
        events = db.query(models.Event).filter(models.Event.employee_id == emp.id).all()
        events_dict[emp.id] = events

    # Инициализируем AI Assistant
    ai = ai_assistant.AIAssistant(active_employees, events_dict)

    for emp in active_employees:
        events = events_dict[emp.id]
        work_days = emp.work_days.split(",")
        
        # Расчеты из calculations.py
        days = calculations.days_since_last_update(emp)
        relevance = calculations.relevance_score(emp)
        conflict = calculations.conflict_ratio(emp, events, emp.work_start, emp.work_end, work_days)
        load = calculations.load_level(emp, events, emp.work_start, emp.work_end, work_days)
        
        # Интегральный риск (заглушки для часовых поясов и HR)
        risk = calculations.integrated_risk(relevance, conflict, load, False, False)
        
        outside_meetings = sum(1 for ev in events if not calculations.is_within_work_hours(ev, emp.work_start, emp.work_end, work_days, emp.timezone))
        
        # Получаем рекомендации от AI
        recs = ai.generate_recommendations(emp)

        dashboard_data.append({
            "employee": {
                "id": emp.id,
                "name": emp.name,
                "position": emp.position,
                "work_format": emp.work_format,
                "timezone": emp.timezone,
                "last_update": emp.last_update,
                "current_task": emp.current_task or "",
                "status": emp.status or "active",
            },
            "metrics": schemas.MetricsResponse(
                employee_id=emp.id,
                name=emp.name,
                days_since_last_update=days,
                relevance_score=relevance,
                conflict_ratio=conflict,
                load_level=load,
                integrated_risk=risk,
                meetings_outside_work=outside_meetings,
                conflicts_count=len(events),
                needs_review=risk > 0.5,
                risk_level=calculations.get_risk_level(risk)
            ),
            "recommendations": recs
        })

    # Общие окна команды
    windows = ai.find_best_meeting_windows(team_id)

    return {
        "team_id": team.id,
        "team_name": team.name,
        "members_diagnostics": dashboard_data,
        "best_meeting_times": windows
    }


# ==========================================
# 3. ИСКУССТВЕННЫЙ ИНТЕЛЛЕКТ (ЧАТ-БОТ)
# ==========================================
@app.post("/ai/ask")
def ask_ai(query: schemas.AIAssistantQuery, db: Session = Depends(get_db)):
    """Эндпоинт для чат-бота, отвечающего на вопросы о команде"""
    employees = db.query(models.Employee).all()
    if query.team_id:
        employees = [e for e in employees if e.team_id == query.team_id]
        
    events_dict = {emp.id: db.query(models.Event).filter(models.Event.employee_id == emp.id).all() for emp in employees}
    
    ai = ai_assistant.AIAssistant(employees, events_dict)
    answer = ai.answer_question(query.question, query.team_id)
    
    return {"answer": answer}


# ==========================================
# 4. КОМАНДНАЯ ДОСТУПНОСТЬ (HEATMAP + ОКНА + ОТЩЕПЕНЦЫ)
# ==========================================
def _parse_hhmm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


def _format_date_range(start: datetime, end: datetime) -> str:
    """ДД.ММ.ГГГГ или 'с ДД.ММ по ДД.ММ' для одного года."""
    start_d = start.date()
    end_d = end.date()
    if start_d == end_d:
        return start_d.strftime("%d.%m.%Y")
    if start_d.year == end_d.year:
        return f"с {start_d.strftime('%d.%m')} по {end_d.strftime('%d.%m.%Y')}"
    return f"с {start_d.strftime('%d.%m.%Y')} по {end_d.strftime('%d.%m.%Y')}"


def _build_availability_map(team: models.Team, db: Session, target_date: datetime,
                             hour_start: int = 9, hour_end: int = 20):
    """Нарезает день на часовые слоты и собирает статус каждого сотрудника."""
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    employees = [e for e in team.employees if (e.status or "active") == "active"]
    employees_payload = [
        {
            "id": emp.id,
            "name": emp.name,
            "timezone": emp.timezone,
            "work_format": emp.work_format,
        }
        for emp in employees
    ]

    # Все события сотрудников команды на эти сутки
    emp_ids = [e.id for e in employees]
    events = []
    if emp_ids:
        events = (
            db.query(models.Event)
            .filter(models.Event.employee_id.in_(emp_ids))
            .filter(models.Event.start_time < day_end)
            .filter(models.Event.end_time > day_start)
            .all()
        )

    events_by_emp = {emp.id: [] for emp in employees}
    for ev in events:
        events_by_emp[ev.employee_id].append(ev)

    slots = []
    common_window_hours = []

    for hour in range(hour_start, hour_end):
        slot_start = day_start + timedelta(hours=hour)
        slot_end = slot_start + timedelta(hours=1)

        statuses = []
        all_available = True

        for emp in employees:
            work_days = emp.work_days.split(",")
            local = calculations.get_local_time(slot_start, emp.timezone)
            weekday = local.strftime("%a").lower()

            sh, sm = _parse_hhmm(emp.work_start)
            eh, em = _parse_hhmm(emp.work_end)
            local_min = local.hour * 60 + local.minute
            in_work_window = (
                weekday in work_days
                and sh * 60 + sm <= local_min < eh * 60 + em
            )

            # Пересечение с событиями
            collision = None
            for ev in events_by_emp[emp.id]:
                if max(slot_start, ev.start_time) < min(slot_end, ev.end_time):
                    collision = ev
                    break

            if collision is not None:
                if collision.event_type in ("exception", "vacation"):
                    status = "vacation"
                elif collision.event_type == "sick_leave":
                    status = "sick"
                else:
                    status = "busy"
                title = collision.title
                # Для отпусков и больничных — добавим читабельные даты
                if status in ("vacation", "sick"):
                    title = f"{collision.title} ({_format_date_range(collision.start_time, collision.end_time)})"
            elif not in_work_window:
                status = "off"
                title = "Вне рабочего графика"
            else:
                status = "free"
                title = ""

            if status != "free":
                all_available = False

            statuses.append({
                "employee_id": emp.id,
                "status": status,
                "title": title,
            })

        slot_label = f"{hour:02d}:00"
        slots.append({
            "hour": hour,
            "label": slot_label,
            "statuses": statuses,
            "team_available": all_available and bool(employees),
        })

        if all_available and employees:
            common_window_hours.append(slot_label)

    return {
        "team_id": team.id,
        "team_name": team.name,
        "date": day_start.strftime("%Y-%m-%d"),
        "hour_start": hour_start,
        "hour_end": hour_end,
        "employees": employees_payload,
        "slots": slots,
        "common_window_hours": common_window_hours,
    }


@app.get("/api/team/{team_id}/availability_map")
def availability_map(
    team_id: int,
    date: Optional[str] = Query(None, description="ISO дата YYYY-MM-DD; по умолчанию — завтра"),
    hour_start: int = Query(9, ge=0, le=23),
    hour_end: int = Query(20, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """Возвращает heatmap-сетку: для каждого часа — статус каждого сотрудника
    (free / busy / vacation / off) и флаг team_available."""
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Команда не найдена")
    if hour_end <= hour_start:
        raise HTTPException(status_code=400, detail="hour_end должен быть больше hour_start")

    if date:
        try:
            target = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный формат даты, ожидается YYYY-MM-DD")
    else:
        target = datetime.utcnow() + timedelta(days=1)

    return _build_availability_map(team, db, target, hour_start, hour_end)


@app.get("/api/team/{team_id}/availability")
def team_availability(team_id: int, db: Session = Depends(get_db)):
    """Окна, проблемные дни и список «отщепенцев» (кто выпадает из общего окна)."""
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Команда не найдена")

    employees = team.employees
    events_dict = {emp.id: db.query(models.Event).filter(models.Event.employee_id == emp.id).all() for emp in employees}

    # Топ-3 окна на ближайшие сутки
    common_windows = calculations.team_common_windows(employees, events_dict)

    # Сканируем 7 дней вперёд: какие даты вообще без общих окон
    problematic_days = []
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        # Проверяем, есть ли хоть один общий час в типовом диапазоне 9..20
        snap = _build_availability_map(team, db, day, 9, 20)
        if not snap["common_window_hours"]:
            problematic_days.append(day.strftime("%Y-%m-%d"))

    # Отщепенцы — те, у кого больше всего «выпадений» из рабочего окна команды
    # Считаем долю слотов, где сотрудник недоступен, на завтрашний день
    tomorrow_snap = _build_availability_map(team, db, today + timedelta(days=1), 9, 20)
    out_of_sync = []
    if tomorrow_snap["slots"]:
        total_slots = len(tomorrow_snap["slots"])
        per_emp = {emp["id"]: 0 for emp in tomorrow_snap["employees"]}
        for slot in tomorrow_snap["slots"]:
            for st in slot["statuses"]:
                if st["status"] != "free":
                    per_emp[st["employee_id"]] += 1
        for emp in employees:
            ratio = per_emp.get(emp.id, 0) / total_slots
            if ratio > 0.7:  # выпадает из 70%+ слотов
                out_of_sync.append({"id": emp.id, "name": emp.name, "off_ratio": round(ratio, 2)})

    return {
        "team_id": team.id,
        "team_name": team.name,
        "common_windows": common_windows,
        "problematic_days": problematic_days,
        "employees_out_of_sync": out_of_sync,
    }


@app.get("/api/team/{team_id}/recommendations")
def team_recommendations(team_id: int, db: Session = Depends(get_db)):
    """Сырые данные по перегруженным сотрудникам (L_i > 0.8) и текстовые рекомендации от AI."""
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Команда не найдена")

    employees = team.employees
    events_dict = {emp.id: db.query(models.Event).filter(models.Event.employee_id == emp.id).all() for emp in employees}
    ai = ai_assistant.AIAssistant(employees, events_dict)

    overloaded = []
    for emp in employees:
        events = events_dict[emp.id]
        work_days = emp.work_days.split(",")
        load = calculations.load_level(emp, events, emp.work_start, emp.work_end, work_days)
        if load > 0.8:
            overloaded.append({
                "employee": {"id": emp.id, "name": emp.name, "timezone": emp.timezone, "work_format": emp.work_format},
                "load_level": round(load, 3),
                "events_count": len(events),
                "recommendations": ai.generate_recommendations(emp),
            })

    return {
        "team_id": team.id,
        "team_name": team.name,
        "overloaded": overloaded,
        "summary": (
            f"Перегружены {len(overloaded)} сотрудников из {len(employees)}."
            if overloaded else "Перегруженных сотрудников нет."
        ),
    }


# ==========================================
# 5. ПРОФИЛЬ СОТРУДНИКА + АКТИВНОСТЬ ОТ АГЕНТА
# ==========================================
def _activity_summary(db: Session, employee_id: int, day: datetime) -> dict:
    """Группирует логи агента по приложениям за указанный день (UTC)."""
    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    logs = (
        db.query(models.ActivityLog)
        .filter(models.ActivityLog.employee_id == employee_id)
        .filter(models.ActivityLog.logged_at >= day_start)
        .filter(models.ActivityLog.logged_at < day_end)
        .all()
    )

    totals: dict[str, dict] = {}
    for log in logs:
        display, color = normalize_app(log.app_name)
        bucket = totals.setdefault(display, {"name": display, "color": color, "seconds": 0})
        bucket["seconds"] += int(log.duration_seconds or 0)

    total_seconds = sum(b["seconds"] for b in totals.values())

    apps_sorted = sorted(totals.values(), key=lambda b: b["seconds"], reverse=True)

    apps_payload = []
    for bucket in apps_sorted:
        seconds = bucket["seconds"]
        percentage = round(seconds / total_seconds * 100, 1) if total_seconds else 0.0
        minutes = seconds // 60
        apps_payload.append({
            "name": bucket["name"],
            "color": bucket["color"],
            "percentage": percentage,
            "time": format_minutes(minutes),
            "seconds": seconds,
        })

    return {
        "date": day_start.strftime("%Y-%m-%d"),
        "total_tracked_hours": round(total_seconds / 3600, 2),
        "total_tracked_label": format_minutes(total_seconds // 60),
        "apps": apps_payload,
    }


@app.get("/api/employee/{user_id}/activity_summary")
def employee_activity_summary(user_id: int, date: Optional[str] = None, db: Session = Depends(get_db)):
    """Сводка активности сотрудника за день (для горизонтального Stacked Bar)."""
    employee = db.query(models.Employee).filter(models.Employee.id == user_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный формат даты, ожидается YYYY-MM-DD")
    else:
        day = datetime.utcnow()

    return {"employee_id": employee.id, **_activity_summary(db, employee.id, day)}


@app.get("/api/employee/{user_id}/profile")
def employee_profile(user_id: int, db: Session = Depends(get_db)):
    """Полные данные для модалки профиля: метрики, активность, история, рекомендации."""
    employee = db.query(models.Employee).filter(models.Employee.id == user_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    events = db.query(models.Event).filter(models.Event.employee_id == employee.id).all()
    work_days = employee.work_days.split(",")

    relevance = calculations.relevance_score(employee)
    conflict = calculations.conflict_ratio(employee, events, employee.work_start, employee.work_end, work_days)
    load = calculations.load_level(employee, events, employee.work_start, employee.work_end, work_days)
    risk = calculations.integrated_risk(relevance, conflict, load, False, False)
    days = calculations.days_since_last_update(employee)

    burnout_alert = None
    if load > 0.8 or risk > 0.7:
        burnout_alert = (
            f"Высокий риск выгорания: загрузка {(load*100):.0f}%, риск {risk:.2f}."
        )
    elif days > 90:
        burnout_alert = f"График не обновлялся {days} дней — данные могут быть неактуальны."

    # Активность за сегодня
    activity = _activity_summary(db, employee.id, datetime.utcnow())

    # История изменений
    history_rows = (
        db.query(models.HistoryEvent)
        .filter(models.HistoryEvent.employee_id == employee.id)
        .order_by(models.HistoryEvent.happened_at.desc())
        .all()
    )
    history = [
        {
            "id": h.id,
            "happened_at": h.happened_at.isoformat(),
            "title": h.title,
            "description": h.description or "",
            "icon": h.icon or "fa-circle-info",
            "days_ago": (datetime.utcnow() - h.happened_at).days,
        }
        for h in history_rows
    ]

    # Рекомендации ИИ для этого сотрудника
    employees = [employee]
    events_dict = {employee.id: events}
    ai = ai_assistant.AIAssistant(employees, events_dict)
    recommendations = ai.generate_recommendations(employee)

    # История задач
    task_rows = (
        db.query(models.TaskHistory)
        .filter(models.TaskHistory.employee_id == employee.id)
        .order_by(models.TaskHistory.started_at.desc())
        .all()
    )
    task_history_payload = [
        {
            "id": r.id,
            "text": r.text,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "is_current": r.ended_at is None,
        }
        for r in task_rows
    ]

    return {
        "employee": {
            "id": employee.id,
            "name": employee.name,
            "email": employee.email,
            "position": employee.position,
            "team_id": employee.team_id,
            "timezone": employee.timezone,
            "work_format": employee.work_format,
            "work_days": employee.work_days,
            "work_start": employee.work_start,
            "work_end": employee.work_end,
            "last_update": employee.last_update.isoformat() if employee.last_update else None,
            "current_task": employee.current_task or "",
            "status": employee.status or "active",
        },
        "metrics": {
            "relevance_score": round(relevance, 2),
            "conflict_ratio": round(conflict, 2),
            "load_level": round(load, 2),
            "integrated_risk": round(risk, 2),
            "days_since_last_update": days,
            "risk_level": calculations.get_risk_level(risk),
        },
        "burnout_alert": burnout_alert,
        "activity": activity,
        "history": history,
        "recommendations": recommendations,
        "task_history": task_history_payload,
    }


@app.post("/api/activity")
def ingest_activity(payload: schemas.ActivityIn, db: Session = Depends(get_db)):
    """Принимает один лог от TrackerAgent (POST с полями user_id, app_name, ...)."""
    employee = db.query(models.Employee).filter(models.Employee.id == payload.user_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    log = models.ActivityLog(
        employee_id=payload.user_id,
        app_name=payload.app_name,
        window_title=payload.window_title,
        duration_seconds=int(payload.duration_seconds or 0),
        logged_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    return {"status": "ok", "id": log.id}


# ==========================================
# 6. БЫСТРЫЕ ДЕЙСТВИЯ (РЕЗЕРВ, ЗАДАЧИ, БЫСТРЫЕ СОБЫТИЯ)
# ==========================================
@app.patch("/api/employees/{user_id}/release")
def release_employee(user_id: int, db: Session = Depends(get_db)):
    """Перевод сотрудника в статус 'reserve' (в резерве / свободен)."""
    emp = db.query(models.Employee).filter(models.Employee.id == user_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.status = "reserve"
    # Запишем в историю графика
    db.add(models.HistoryEvent(
        employee_id=emp.id,
        title="Переведён в резерв",
        description="Сотрудник освобождён из текущей команды и переведён в статус «свободен».",
        icon="fa-user-slash",
    ))
    db.commit()
    return {"id": emp.id, "status": emp.status, "message": f"{emp.name} переведён в резерв"}


@app.patch("/api/employees/{user_id}/restore")
def restore_employee(user_id: int, db: Session = Depends(get_db)):
    """Возвращает резервиста в активный статус."""
    emp = db.query(models.Employee).filter(models.Employee.id == user_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.status = "active"
    db.commit()
    return {"id": emp.id, "status": emp.status}


@app.patch("/api/employees/{user_id}/task")
def update_task(user_id: int, payload: schemas.TaskUpdateRequest, db: Session = Depends(get_db)):
    """Обновляет 'Текущая задача'. Закрывает прошлую запись в истории и создаёт новую."""
    emp = db.query(models.Employee).filter(models.Employee.id == user_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    new_text = (payload.text or "").strip()
    if not new_text:
        raise HTTPException(status_code=400, detail="Текст задачи не может быть пустым")

    # Закрываем все открытые записи
    open_rows = (
        db.query(models.TaskHistory)
        .filter(models.TaskHistory.employee_id == emp.id)
        .filter(models.TaskHistory.ended_at.is_(None))
        .all()
    )
    now_dt = datetime.utcnow()
    for row in open_rows:
        row.ended_at = now_dt

    db.add(models.TaskHistory(
        employee_id=emp.id,
        text=new_text,
        started_at=now_dt,
        ended_at=None,
    ))
    emp.current_task = new_text
    db.commit()
    return {"id": emp.id, "current_task": emp.current_task}


@app.get("/api/employees/{user_id}/task_history")
def task_history(user_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(models.TaskHistory)
        .filter(models.TaskHistory.employee_id == user_id)
        .order_by(models.TaskHistory.started_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "text": r.text,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "is_current": r.ended_at is None,
        }
        for r in rows
    ]


@app.post("/api/events/quick")
def quick_event(payload: schemas.QuickEventRequest, db: Session = Depends(get_db)):
    """Создаёт событие на дату/час в 1 клик.
    event_type: vacation | sick_leave | duty | day_off."""
    emp = db.query(models.Employee).filter(models.Employee.id == payload.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    try:
        day = datetime.strptime(payload.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Дата должна быть в формате YYYY-MM-DD")

    titles = {
        "vacation": "Отпуск",
        "sick_leave": "Больничный",
        "duty": "Дежурство",
        "day_off": "Отгул",
    }
    if payload.event_type not in titles:
        raise HTTPException(status_code=400, detail="Неизвестный тип события")

    if payload.hour is not None:
        # Часовой слот
        start = day.replace(hour=int(payload.hour))
        end = start + timedelta(hours=1)
    else:
        # На весь день / диапазоны по умолчанию
        if payload.event_type == "duty":
            start = day.replace(hour=9)
            end = day.replace(hour=18)
        elif payload.event_type == "vacation":
            start = day.replace(hour=0)
            end = (day + timedelta(days=3)).replace(hour=23)
        elif payload.event_type == "sick_leave":
            start = day.replace(hour=0)
            end = (day + timedelta(days=2)).replace(hour=23)
        else:  # day_off
            start = day.replace(hour=0)
            end = day.replace(hour=23)

    event = models.Event(
        employee_id=emp.id,
        title=titles[payload.event_type],
        start_time=start,
        end_time=end,
        event_type=payload.event_type,
        source="manual_quick",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {
        "id": event.id,
        "title": event.title,
        "event_type": event.event_type,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
    }


# ==========================================
# 7. GIGACHAT (AI ПРОДЖЕКТ-МЕНЕДЖЕР)
# ==========================================
@app.get("/api/ai/health")
def ai_health():
    """Возвращает статус подключения к GigaChat для индикатора онлайн/оффлайн."""
    from gigachat_service import client
    return client.health()


@app.post("/api/ai/chat")
def ai_chat(payload: schemas.GigaChatRequest, db: Session = Depends(get_db)):
    """Главный эндпоинт чата. В system prompt подмешивает контекст команды.

    Если GigaChat не настроен или упал — отдаём fallback на локальный ассистент."""
    from gigachat_service import client, build_system_prompt, GigaChatNotConfigured, GigaChatError

    # Контекст: данные дашборда выбранной команды
    team_payload = None
    if payload.team_id:
        team = db.query(models.Team).filter(models.Team.id == payload.team_id).first()
        if team:
            # Используем тот же сборщик, что и /api/dashboard/team/{id}
            team_payload = get_team_dashboard(team.id, db=db)

    # Формируем messages для модели
    system_text = build_system_prompt(team_payload)
    messages = [{"role": "system", "content": system_text}]
    for m in payload.messages:
        messages.append({"role": m.role, "content": m.content})

    # Если ключа нет — fallback на локального ассистента
    if not client.configured:
        last_user = next((m.content for m in reversed(payload.messages) if m.role == "user"), "")
        employees = db.query(models.Employee).all()
        if payload.team_id:
            employees = [e for e in employees if e.team_id == payload.team_id and (e.status or "active") == "active"]
        events_dict = {emp.id: db.query(models.Event).filter(models.Event.employee_id == emp.id).all() for emp in employees}
        ai = ai_assistant.AIAssistant(employees, events_dict)
        return {
            "answer": ai.answer_question(last_user, payload.team_id),
            "provider": "local",
            "online": False,
        }

    try:
        answer = client.chat(messages)
        return {"answer": answer, "provider": "gigachat", "online": True}
    except GigaChatNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except GigaChatError as e:
        # Падаем на локального ассистента, но сообщаем об ошибке
        last_user = next((m.content for m in reversed(payload.messages) if m.role == "user"), "")
        employees = db.query(models.Employee).all()
        if payload.team_id:
            employees = [e for e in employees if e.team_id == payload.team_id and (e.status or "active") == "active"]
        events_dict = {emp.id: db.query(models.Event).filter(models.Event.employee_id == emp.id).all() for emp in employees}
        ai = ai_assistant.AIAssistant(employees, events_dict)
        return {
            "answer": f"⚠️ GigaChat недоступен ({e}). Отвечаю встроенной логикой.\n\n" + ai.answer_question(last_user, payload.team_id),
            "provider": "local",
            "online": False,
        }


# ==========================================
# 8. CRUD ОПЕРАЦИИ (ДЛЯ БУДУЩЕГО РАСШИРЕНИЯ)
# ==========================================
@app.post("/employees/")
def create_employee(emp: schemas.EmployeeCreate, db: Session = Depends(get_db)):
    """Добавление нового сотрудника вручную"""
    db_emp = models.Employee(**emp.model_dump(exclude={"exceptions"}))
    # Для MVP исключения пока можно опустить или реализовать через отдельную таблицу
    db.add(db_emp)
    db.commit()
    db.refresh(db_emp)
    return db_emp

@app.post("/events/")
def create_event(event: schemas.EventCreate, db: Session = Depends(get_db)):
    """Добавление нового события (встречи/отпуска) вручную"""
    db_event = models.Event(**event.model_dump())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event