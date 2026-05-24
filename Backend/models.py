from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
import datetime


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)

    employees = relationship("Employee", back_populates="team", cascade="all, delete")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"))

    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    position = Column(String, default="Сотрудник")

    work_days = Column(String, default="mon,tue,wed,thu,fri")
    work_start = Column(String, default="09:00")
    work_end = Column(String, default="18:00")
    timezone = Column(String, default="UTC+3")
    work_format = Column(String, default="office")

    last_update = Column(DateTime, default=datetime.datetime.utcnow)

    # Новое: статус «active» / «reserve» (свободен)
    status = Column(String, default="active", index=True)

    # Новое: текущая задача
    current_task = Column(String, default="")

    team = relationship("Team", back_populates="employees")
    events = relationship("Event", back_populates="employee", cascade="all, delete")
    activity_logs = relationship("ActivityLog", back_populates="employee", cascade="all, delete")
    history_events = relationship("HistoryEvent", back_populates="employee", cascade="all, delete")
    task_history = relationship("TaskHistory", back_populates="employee", cascade="all, delete")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))

    title = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)

    event_type = Column(String)
    source = Column(String)

    employee = relationship("Employee", back_populates="events")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)

    app_name = Column(String, index=True)
    window_title = Column(String)
    duration_seconds = Column(Integer, default=0)
    logged_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    employee = relationship("Employee", back_populates="activity_logs")


class HistoryEvent(Base):
    __tablename__ = "history_events"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)

    happened_at = Column(DateTime, default=datetime.datetime.utcnow)
    title = Column(String)
    description = Column(String)
    icon = Column(String, default="fa-circle-info")

    employee = relationship("Employee", back_populates="history_events")


class TaskHistory(Base):
    """История задач сотрудника (все, что он работал когда-либо)."""
    __tablename__ = "task_history"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    text = Column(String)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

    employee = relationship("Employee", back_populates="task_history")
