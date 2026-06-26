# app/routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Literal

from app.database import get_db
from app.routers.auth import get_current_user
from app.models.task import Task
from app.services import parser

router = APIRouter()

class TaskCreateRequest(BaseModel):
    raw_input: str
    notification_channel: Literal["email", "messenger"]

@router.post("", response_model=dict)
async def create_task(
    payload: TaskCreateRequest,
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        parsed_config = await parser.parse_task(payload.raw_input)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e) or "Could not parse task input"
        )
    
    task_type = parsed_config.get("task_type", "web_monitor")
    schedule_mins = parsed_config.get("schedule_mins", 60)
    if schedule_mins < 60:
        schedule_mins = 60
        
    now = datetime.utcnow()
    next_run = now + timedelta(minutes=schedule_mins)
    
    # Extract config details
    config_dict = {
        "url": parsed_config.get("url"),
        "condition": parsed_config.get("condition"),
        "notification_channel": payload.notification_channel
    }
    
    # For date_reminder tasks, parse context or config info if parsed
    if task_type == "date_reminder":
        # Check if parser returned reminder_date
        config_dict["reminder_date"] = parsed_config.get("reminder_date")
        
    db_task = Task(
        user_id=current_user_id,
        raw_input=payload.raw_input,
        task_type=task_type,
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
