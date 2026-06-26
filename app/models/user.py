# app/models/user.py
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)  # Clerk ID
    clerk_id = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    plan_tier = Column(String, default="free")  # free, paid
    stripe_id = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    messenger_accounts = relationship("MessengerAccount", back_populates="user", cascade="all, delete-orphan")
