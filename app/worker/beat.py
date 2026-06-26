# app/worker/beat.py
from datetime import datetime
from celery import Celery
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.task import Task
from app.worker.celery_app import celery_app
from app.worker.tasks import run_task

# Create synchronous engine for Celery Beat since it runs in a synchronous loop context
sync_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
engine = create_engine(sync_db_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Register dispatch_due_tasks to run every 5 minutes (300 seconds)
    sender.add_periodic_task(300.0, dispatch_due_tasks.s(), name="dispatch-due-tasks-every-5-min")

@celery_app.task
def dispatch_due_tasks():
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        # Query active tasks whose next run time has arrived or passed
        stmt = select(Task).where(
            Task.status == "active",
            Task.next_run <= now
        )
        result = session.execute(stmt)
        due_tasks = result.scalars().all()
        
        for task in due_tasks:
            run_task.delay(task.id)
            
    except Exception as e:
        # Log error in beat task
        print(f"Error querying/dispatching due tasks: {str(e)}")
    finally:
        session.close()
