# app/routers/notifications.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.routers.auth import get_current_user
from app.models.notification import Notification

router = APIRouter()

@router.get("", response_model=list)
async def list_notifications(
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Notification).where(Notification.user_id == current_user_id).order_by(Notification.sent_at.desc())
    result = await db.execute(query)
    notifs = result.scalars().all()
    return [
        {
            "id": n.id,
            "user_id": n.user_id,
            "task_id": n.task_id,
            "channel": n.channel,
            "status": n.status,
            "payload": n.payload,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None
        }
        for n in notifs
    ]

@router.get("/task/{task_id}", response_model=list)
async def list_task_notifications(
    task_id: int,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Notification).where(
        Notification.task_id == task_id,
        Notification.user_id == current_user_id
    ).order_by(Notification.sent_at.desc())
    result = await db.execute(query)
    notifs = result.scalars().all()
    return [
        {
            "id": n.id,
            "user_id": n.user_id,
            "task_id": n.task_id,
            "channel": n.channel,
            "status": n.status,
            "payload": n.payload,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None
        }
        for n in notifs
    ]
