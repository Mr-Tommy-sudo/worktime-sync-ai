from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional, Dict

class ExceptionCreate(BaseModel):
    type: str  # vacation, sick, business_trip, personal
    start_date: datetime
    end_date: datetime

class EmployeeCreate(BaseModel):
    name: str
    email: str
    team_id: int
    work_days: str
    work_start: str
    work_end: str
    timezone: str
    work_format: str
    exceptions: List[ExceptionCreate] = []

class EventCreate(BaseModel):
    employee_id: int
    title: str
    start_time: datetime
    end_time: datetime
    event_type: str
    source: str

class MetricsResponse(BaseModel):
    employee_id: int
    name: str
    days_since_last_update: int
    relevance_score: float  # A_i
    conflict_ratio: float   # C_i
    load_level: float       # L_i
    integrated_risk: float  # R_i
    meetings_outside_work: int
    conflicts_count: int
    needs_review: bool
    risk_level: str  # low, medium, high, critical

class TeamAvailability(BaseModel):
    team_id: int
    team_name: str
    common_windows: List[Dict[str, str]]
    best_meeting_times: List[str]
    problematic_days: List[str]
    employees_out_of_sync: List[str]

class RecommendationResponse(BaseModel):
    employee_id: int
    recommendations: List[str]

class AIAssistantQuery(BaseModel):
    question: str
    team_id: Optional[int] = None


class ActivityIn(BaseModel):
    """Входящие логи от TrackerAgent (POST /api/activity)."""
    user_id: int
    app_name: str
    window_title: Optional[str] = None
    duration_seconds: int


class TeamCreate(BaseModel):
    name: str


class RandomEmployeeRequest(BaseModel):
    team_id: int


class TaskUpdateRequest(BaseModel):
    text: str


class QuickEventRequest(BaseModel):
    employee_id: int
    event_type: str  # vacation | sick_leave | duty | day_off
    date: str        # YYYY-MM-DD
    hour: Optional[int] = None  # если задан — событие на этот час


class ChatMessage(BaseModel):
    role: str  # system | user | assistant
    content: str


class GigaChatRequest(BaseModel):
    messages: List[ChatMessage]
    team_id: Optional[int] = None