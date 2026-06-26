# app/models/messenger_account.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class MessengerAccount(Base):
    __tablename__ = "messenger_accounts"
    id        = Column(Integer, primary_key=True)
    user_id   = Column(String, ForeignKey("users.id"), nullable=False)
    psid      = Column(String, unique=True, index=True)
    page_token = Column(String)
    linked_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="messenger_accounts")
