# app/models/notification.py
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class Notification(Base):
    __tablename__ = "notifications"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    task_id    = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    channel    = Column(String, nullable=False)  # "email" | "messenger"
    status     = Column(String, default="pending")  # "pending" | "sent" | "failed"
    payload    = Column(JSON)
    sent_at    = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")
    task = relationship("Task", back_populates="notifications")
