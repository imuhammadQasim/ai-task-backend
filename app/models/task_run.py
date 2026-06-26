# app/models/task_run.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class TaskRun(Base):
    __tablename__ = "task_runs"
    id              = Column(Integer, primary_key=True)
    task_id         = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    ran_at          = Column(DateTime, default=datetime.utcnow)
    change_detected = Column(Boolean, default=False)
    notif_sent      = Column(Boolean, default=False)
    result_summary  = Column(String)

    task = relationship("Task", back_populates="runs")
