# app/routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta, date
from pydantic import BaseModel, model_validator
from typing import Literal, Optional

from app.database import get_db
from app.routers.auth import get_current_user
from app.models.task import Task

router = APIRouter()

class TaskCreateRequest(BaseModel):
    task_type: Literal["web_monitor", "date_reminder"]
    notification_channel: Literal["email", "messenger"]
    schedule_mins: Optional[int] = None
    monitor_mode: Optional[Literal["url", "topic"]] = None
    url: Optional[str] = None
    condition: Optional[str] = None
    topic: Optional[str] = None
    reminder_date: Optional[date] = None
    message: Optional[str] = None

    @model_validator(mode="after")
    def validate_required_fields(self):
        if self.task_type == "web_monitor":
            if self.monitor_mode is None:
                raise ValueError("monitor_mode is required for web_monitor tasks")
            if self.monitor_mode == "url" and (not self.url or not self.condition):
                raise ValueError("url and condition are required when monitor_mode is 'url'")
            if self.monitor_mode == "topic" and not self.topic:
                raise ValueError("topic is required when monitor_mode is 'topic'")
            if self.schedule_mins is None:
                raise ValueError("schedule_mins is required for web_monitor tasks")
            if self.schedule_mins < 60:
                self.schedule_mins = 60
        elif self.task_type == "date_reminder":
            if not self.reminder_date or not self.message:
                raise ValueError("reminder_date and message are required for date_reminder tasks")
        return self

@router.post("", response_model=dict)
async def create_task(
    payload: TaskCreateRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.utcnow()

    # Build config + schedule directly from the validated payload.
    if payload.task_type == "web_monitor":
        schedule_mins = payload.schedule_mins  # validator guarantees >= 60
        next_run = now + timedelta(minutes=schedule_mins)

        config_dict = {
            "monitor_mode": payload.monitor_mode,
            "notification_channel": payload.notification_channel,
        }
        if payload.monitor_mode == "url":
            config_dict["url"] = payload.url
            config_dict["condition"] = payload.condition
        else:  # topic mode
            config_dict["topic"] = payload.topic
    else:  # date_reminder
        # Reminder tasks are polled on a schedule until the reminder_date matches;
        # keep the existing schedule-based next_run behavior (default 60 mins).
        schedule_mins = payload.schedule_mins if payload.schedule_mins is not None else 60
        if schedule_mins < 60:
            schedule_mins = 60
        next_run = now + timedelta(minutes=schedule_mins)

        config_dict = {
            "reminder_date": payload.reminder_date.isoformat(),
            "message": payload.message,
            "notification_channel": payload.notification_channel,
        }

    db_task = Task(
        user_id=current_user_id,
        raw_input=None,
        task_type=payload.task_type,
        config=config_dict,
        schedule_mins=schedule_mins,
        status="active",
        next_run=next_run,
        created_at=now
    )
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)

    return {
        "id": db_task.id,
        "user_id": db_task.user_id,
        "raw_input": db_task.raw_input,
        "task_type": db_task.task_type,
        "config": db_task.config,
        "schedule_mins": db_task.schedule_mins,
        "status": db_task.status,
        "last_hash": db_task.last_hash,
        "last_run": db_task.last_run.isoformat() if db_task.last_run else None,
        "next_run": db_task.next_run.isoformat() if db_task.next_run else None,
        "created_at": db_task.created_at.isoformat() if db_task.created_at else None
    }

@router.get("", response_model=list)
async def list_tasks(
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Task).where(Task.user_id == current_user_id)
    result = await db.execute(query)
    tasks_list = result.scalars().all()
    return [
        {
            "id": t.id,
            "user_id": t.user_id,
            "raw_input": t.raw_input,
            "task_type": t.task_type,
            "config": t.config,
            "schedule_mins": t.schedule_mins,
            "status": t.status,
            "last_hash": t.last_hash,
            "last_run": t.last_run.isoformat() if t.last_run else None,
            "next_run": t.next_run.isoformat() if t.next_run else None,
            "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in tasks_list
    ]

@router.get("/{task_id}", response_model=dict)
async def get_task(
    task_id: int,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Task).where(Task.id == task_id, Task.user_id == current_user_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id,
        "user_id": task.user_id,
        "raw_input": task.raw_input,
        "task_type": task.task_type,
        "config": task.config,
        "schedule_mins": task.schedule_mins,
        "status": task.status,
        "last_hash": task.last_hash,
        "last_run": task.last_run.isoformat() if task.last_run else None,
        "next_run": task.next_run.isoformat() if task.next_run else None,
        "created_at": task.created_at.isoformat() if task.created_at else None
    }

@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Task).where(Task.id == task_id, Task.user_id == current_user_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    await db.commit()
    return {"status": "deleted"}

@router.patch("/{task_id}/pause", response_model=dict)
async def pause_task(
    task_id: int,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Task).where(Task.id == task_id, Task.user_id == current_user_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "paused"
    await db.commit()
    await db.refresh(task)
    return {
        "id": task.id,
        "status": task.status
    }

@router.patch("/{task_id}/resume", response_model=dict)
async def resume_task(
    task_id: int,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Task).where(Task.id == task_id, Task.user_id == current_user_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "active"
    schedule_mins = task.schedule_mins or 60
    task.next_run = datetime.utcnow() + timedelta(minutes=schedule_mins)
    await db.commit()
    await db.refresh(task)
    return {
        "id": task.id,
        "status": task.status,
        "next_run": task.next_run.isoformat() if task.next_run else None
    }
