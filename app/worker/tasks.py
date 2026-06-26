# app/worker/tasks.py
import asyncio
import hashlib
from datetime import datetime, timedelta
from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.task import Task
from app.models.task_run import TaskRun
from app.models.notification import Notification
from app.services.scraper import fetch_page
from app.services.llm import check_condition
from app.services.notifier import send_notification
from app.worker.celery_app import celery_app

# Create synchronous engine and session maker for Celery worker operations
sync_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
engine = create_engine(sync_db_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# Helper function to run async methods within synchronous Celery task
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@celery_app.task(bind=True, max_retries=3)
def run_task(self, task_id: int):
    session = SessionLocal()
    try:
        # 1. Fetch task by id
        stmt = select(Task).where(Task.id == task_id)
        result = session.execute(stmt)
        task = result.scalar_one_or_none()
        
        if not task or task.status != "active":
            return
            
        now = datetime.utcnow()
        task_config = task.config or {}
        
        # 2. Handle date_reminder task type
        if task.task_type == "date_reminder":
            reminder_date_str = task_config.get("reminder_date")
            today_str = now.strftime("%Y-%m-%d")
            
            if reminder_date_str == today_str:
                # Build mock task run
                task_run = TaskRun(
                    task_id=task.id,
                    ran_at=now,
                    change_detected=True,
                    notif_sent=True,
                    result_summary="Reminder date matched today."
                )
                session.add(task_run)
                
                # Send notification using asyncio runner
                # We need an AsyncSession mock or real async session to write notification row inside notifier
                # So we define an async runner to execute the notifier function which uses AsyncSessionLocal
                # Wait, send_notification takes an AsyncSession. We can create an async session from AsyncSessionLocal
                # imported from app.database.
                async def notify_and_log():
                    from app.database import AsyncSessionLocal as db_async_session_maker
                    async with db_async_session_maker() as async_db:
                        # Re-load task inside async session
                        stmt_async = select(Task).where(Task.id == task.id)
                        res_async = await async_db.execute(stmt_async)
                        task_async = res_async.scalar_one_or_none()
                        
                        channel = task_config.get("notification_channel", "email")
                        await send_notification(
                            user_id=task_async.user_id,
                            task=task_async,
                            summary=f"Reminder: {task_config.get('condition')}",
                            channel=channel,
                            db=async_db
                        )
                
                run_async(notify_and_log())
                
                task.status = "done"
                task.last_run = now
                session.commit()
            return
            
        # 3. Handle web_monitor task type
        elif task.task_type == "web_monitor":
            url = task_config.get("url")
            condition = task_config.get("condition")
            requires_js = task_config.get("requires_js", False)
            channel = task_config.get("notification_channel", "email")
            
            if not url or not condition:
                # Invalid config, stop task run
                return
                
            # Fetch webpage content
            try:
                html = run_async(fetch_page(url, requires_js=requires_js))
            except Exception as scrape_err:
                # Scrape failed, retry task
                raise scrape_err
                
            # Hash fetched page content
            content_hash = hashlib.md5(html.encode("utf-8", errors="ignore")).hexdigest()
            
            # Hash check
            if content_hash == task.last_hash:
                # Update task last run
                task.last_run = now
                task.next_run = now + timedelta(minutes=task.schedule_mins or 60)
                
                # Write TaskRun log
                task_run = TaskRun(
                    task_id=task.id,
                    ran_at=now,
                    change_detected=False,
                    notif_sent=False,
                    result_summary="Page content hash unchanged."
                )
                session.add(task_run)
                session.commit()
                return
                
            # Content changed, call LLM to evaluate condition
            matched, summary = run_async(check_condition(html, condition))
            
            # Write TaskRun log
            task_run = TaskRun(
                task_id=task.id,
                ran_at=now,
                change_detected=True,
                notif_sent=matched,
                result_summary=summary
            )
            session.add(task_run)
            
            # If condition met, dispatch notification
            if matched:
                async def notify_and_log():
                    from app.database import AsyncSessionLocal as db_async_session_maker
                    async with db_async_session_maker() as async_db:
                        stmt_async = select(Task).where(Task.id == task.id)
                        res_async = await async_db.execute(stmt_async)
                        task_async = res_async.scalar_one_or_none()
                        
                        await send_notification(
                            user_id=task_async.user_id,
                            task=task_async,
                            summary=summary,
                            channel=channel,
                            db=async_db
                        )
                run_async(notify_and_log())
                
            # Update task run state and hash
            task.last_hash = content_hash
            task.last_run = now
            task.next_run = now + timedelta(minutes=task.schedule_mins or 60)
            session.commit()
            
    except Exception as exc:
        session.rollback()
        # Retry logic with Celery
        try:
            self.retry(exc=exc, countdown=60)
        except Exception:
            raise exc
    finally:
        session.close()
