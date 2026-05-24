from datetime import datetime, timedelta
from typing import List, Dict
import models

def parse_timezone(tz_str: str) -> int:
    """Вспомогательная функция: парсит строку 'UTC+3' в число 3 для расчетов времени."""
    try:
        if "+" in tz_str:
            return int(tz_str.split("+")[1])
        elif "-" in tz_str:
            return -int(tz_str.split("-")[1])
        return 0
    except:
        return 0

def get_local_time(utc_time: datetime, tz_str: str) -> datetime:
    """Переводит время сервера (UTC) в локальное время сотрудника."""
    return utc_time + timedelta(hours=parse_timezone(tz_str))

def days_since_last_update(employee: models.Employee) -> int:
    """Возвращает количество дней с последнего обновления графика."""
    if not employee.last_update:
        return 90
    return max(0, (datetime.utcnow() - employee.last_update).days)

def relevance_score(employee: models.Employee, max_days_without_update: int = 90) -> float:
    """Расчет показателя актуальности рабочего графика A_i."""
    d = days_since_last_update(employee)
    return max(0.0, 1.0 - (d / max_days_without_update))

def is_within_work_hours(event: models.Event, work_start: str, work_end: str, work_days: List[str], timezone: str) -> bool:
    """Проверяет, попадает ли событие в рабочие часы с учетом часового пояса."""
    local_start = get_local_time(event.start_time, timezone)
    
    weekday = local_start.strftime("%a").lower()
    if weekday not in work_days:
        return False
        
    start_hour, start_min = map(int, work_start.split(":"))
    end_hour, end_min = map(int, work_end.split(":"))
    
    event_time_in_minutes = local_start.hour * 60 + local_start.minute
    work_start_in_minutes = start_hour * 60 + start_min
    work_end_in_minutes = end_hour * 60 + end_min
    
    return work_start_in_minutes <= event_time_in_minutes < work_end_in_minutes

def conflict_ratio(employee: models.Employee, events: List[models.Event], work_start: str, work_end: str, work_days: List[str]) -> float:
    """Расчет коэффициента конфликтов рабочего времени C_i."""
    total = len(events)
    if total == 0:
        return 0.0
    outside = sum(1 for ev in events if not is_within_work_hours(ev, work_start, work_end, work_days, employee.timezone))
    return outside / total

def load_level(employee: models.Employee, events: List[models.Event], work_start: str, work_end: str, work_days: List[str]) -> float:
    """Оценка перегрузки сотрудника L_i."""
    busy_seconds = 0
    for ev in events:
        if ev.event_type in ["meeting", "task"]:
            busy_seconds += max(0, (ev.end_time - ev.start_time).total_seconds())
            
    start_hour, start_min = map(int, work_start.split(":"))
    end_hour, end_min = map(int, work_end.split(":"))
    work_hours_per_day = (end_hour + end_min/60.0) - (start_hour + start_min/60.0)
    
    # Считаем загрузку из расчета 22 рабочих дней (упрощение для MVP)
    total_work_seconds = 22 * work_hours_per_day * 3600
    
    return min(1.0, busy_seconds / total_work_seconds) if total_work_seconds > 0 else 0.0

def integrated_risk(relevance: float, conflict: float, load: float, timezone_conflict: bool, hr_mismatch: bool,
                    w1=0.3, w2=0.3, w3=0.2, w4=0.1, w5=0.1) -> float:
    """Интегральный риск неактуальности R_i."""
    return w1*(1 - relevance) + w2*conflict + w3*load + w4*(1 if timezone_conflict else 0) + w5*(1 if hr_mismatch else 0)

def team_common_windows(employees: List[models.Employee], events_dict: Dict[int, List[models.Event]]) -> List[str]:
    """
    Расчет командной доступности T_team.
    Ищет топ-3 свободных окна на следующий день, где доступны все участники с учетом их часовых поясов.
    """
    if not employees:
        return []
        
    # Берем "завтрашний" день
    tomorrow_utc = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    available_slots = []
    
    # Сканируем каждый час с 05:00 до 22:00 по UTC
    for hour in range(5, 23):
        slot_start_utc = tomorrow_utc + timedelta(hours=hour)
        slot_end_utc = slot_start_utc + timedelta(hours=1)
        
        all_available = True
        for emp in employees:
            local_start = get_local_time(slot_start_utc, emp.timezone)
            work_days = emp.work_days.split(",")
            
            # 1. Проверяем, рабочий ли это день
            weekday = local_start.strftime("%a").lower()
            if weekday not in work_days:
                all_available = False
                break
                
            # 2. Проверяем, попадает ли час в рабочий график сотрудника
            start_h = int(emp.work_start.split(":")[0])
            end_h = int(emp.work_end.split(":")[0])
            if local_start.hour < start_h or local_start.hour >= end_h:
                all_available = False
                break
                
            # 3. Проверяем, нет ли пересечений с событиями в календаре (встречами)
            emp_events = events_dict.get(emp.id, [])
            for ev in emp_events:
                # Если время встречи пересекается со слотом
                if max(slot_start_utc, ev.start_time) < min(slot_end_utc, ev.end_time):
                    all_available = False
                    break
                    
            if not all_available:
                break
                
        if all_available:
            available_slots.append(f"{slot_start_utc.strftime('%d.%m.%Y %H:%M')} (UTC)")
            
    return available_slots[:3] # Возвращаем 2-3 лучших окна для встречи команды по требованию MVP

def get_risk_level(risk: float) -> str:
    """Группировка сотрудников по уровню риска."""
    if risk <= 0.2: return "Низкий риск"
    if risk <= 0.5: return "Средний риск"
    if risk <= 0.8: return "Высокий риск"
    return "Критический риск"