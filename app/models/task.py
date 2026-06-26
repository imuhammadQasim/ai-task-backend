# app/models/task.py
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class Task(Base):
    __tablename__ = "tasks"
    id            = Column(Integer, primary_key=True)
    user_id       = Column(String, ForeignKey("users.id"), nullable=False)
    raw_input     = Column(String)           # what user typed
    task_type     = Column(String)           # "web_monitor" | "date_reminder"
    config        = Column(JSON)             # url, condition, etc.
    schedule_mins = Column(Integer)          # how often to check
    status        = Column(String, default="active")
    last_hash     = Column(String)           # MD5 of last scraped content
    last_run      = Column(DateTime)
    next_run      = Column(DateTime)
    created_at    = Column(DateTime, default=datetime.utcnow)
    
    user          = relationship("User", back_populates="tasks")
    runs          = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="task", cascade="all, delete-orphan")
