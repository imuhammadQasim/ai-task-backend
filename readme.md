You are a senior Python backend engineer. Build a production-ready FastAPI backend for an AI Task Agent SaaS. All dependencies are already installed. The folder structure already exists. Do not explain anything — only write code.

PROJECT CONTEXT:
- AI Task Agent that monitors websites and sends notifications when conditions are met
- Users create tasks in natural language (e.g. "notify me when flight prices drop")
- Backend parses NL input into structured tasks, scrapes URLs on a schedule, calls LLM only when content changes, then sends email or Facebook Messenger notifications

TECH STACK (all already installed):
- FastAPI + Uvicorn (async)
- SQLAlchemy 2.0 async + asyncpg + Alembic
- PostgreSQL (running on localhost:5432, db=taskagent, user=postgres, pass=postgres)
- Redis (running on localhost:6379)
- Celery + Celery Beat (task queue and scheduler)
- httpx + BeautifulSoup4 + Playwright (scraping)
- OpenAI SDK (GPT-4o-mini for NL parsing, one-time per task creation)
- Google Generativeai (Gemini 1.5 Flash for change detection, recurring)
- Resend (email notifications)
- Stripe SDK (subscription webhooks)
- Svix (Clerk webhook verification)

EXISTING FOLDER STRUCTURE:
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   ├── __init__.py        # all models imported here
│   │   ├── user.py            # ALREADY BUILT - do not touch
│   │   ├── task.py            # ALREADY BUILT - do not touch
│   │   ├── task_run.py        # ALREADY BUILT - do not touch
│   │   ├── notification.py    # ALREADY BUILT - do not touch
│   │   └── messenger_account.py  # ALREADY BUILT - do not touch
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py            # Clerk webhook: sync user to DB on signup
│   │   ├── tasks.py           # CRUD: create, list, get, delete, pause task
│   │   ├── notifications.py   # list notifications for current user
│   │   └── webhooks.py        # Stripe webhook: activate/downgrade plan
│   ├── services/
│   │   ├── __init__.py
│   │   ├── parser.py          # GPT-4o-mini: NL string → structured task JSON
│   │   ├── scraper.py         # httpx (static) + Playwright pool (JS pages)
│   │   ├── llm.py             # Gemini Flash: does scraped content match condition?
│   │   └── notifier.py        # send email via Resend OR Messenger via Meta Graph API
│   └── worker/
│       ├── __init__.py
│       ├── celery_app.py      # Celery app instance + Redis broker config
│       ├── beat.py            # Celery Beat: query due tasks every 5 min, enqueue them
│       └── tasks.py           # run_task: fetch → hash check → LLM → notify → log
├── alembic/                   # ALREADY CONFIGURED - do not touch
├── docker-compose.yml         # ALREADY BUILT - do not touch
├── requirements.txt           # ALREADY BUILT - do not touch
└── .env                       # ALREADY EXISTS

EXISTING .env KEYS (use exactly these variable names):
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/taskagent
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=changethislater
OPENAI_API_KEY=
GEMINI_API_KEY=
RESEND_API_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
CLERK_WEBHOOK_SECRET=
META_PAGE_TOKEN=

EXISTING MODELS SUMMARY (read-only, do not redefine):
- User: id(String/ClerkID), clerk_id, email, plan_tier(free/paid), stripe_id, created_at
- Task: id(int), user_id(FK), raw_input, task_type(web_monitor|date_reminder), config(JSON), schedule_mins, status(active|paused|done), last_hash, last_run, next_run, created_at
- TaskRun: id, task_id(FK), ran_at, change_detected(bool), notif_sent(bool), result_summary
- Notification: id, user_id(FK), task_id(FK), channel(email|messenger), status(pending|sent|failed), payload, sent_at
- MessengerAccount: id, user_id(FK), psid, page_token, linked_at

NOW BUILD EVERY FILE BELOW. Write complete, working code for each:

─────────────────────────────
FILE 1: app/config.py
─────────────────────────────
Pydantic BaseSettings. Load all .env keys. Single `settings` instance exported.

─────────────────────────────
FILE 2: app/database.py
─────────────────────────────
Async SQLAlchemy engine using DATABASE_URL. AsyncSessionLocal. Base = DeclarativeBase. get_db() async generator as FastAPI dependency.

─────────────────────────────
FILE 3: app/main.py
─────────────────────────────
FastAPI app instance. Include all 4 routers with prefixes: /auth, /tasks, /notifications, /webhooks. CORS enabled for all origins (dev). Startup event: log "Server started". Health check route GET / returns {"status": "ok"}.

─────────────────────────────
FILE 4: app/routers/auth.py
─────────────────────────────
POST /auth/clerk-webhook
- Verify Svix signature using CLERK_WEBHOOK_SECRET
- On event type "user.created": upsert User row (id=clerk user_id, clerk_id, email from first email address, plan_tier="free")
- On event type "user.deleted": delete User row by clerk_id
- Return {"status": "ok"}
Also export: get_current_user dependency — extracts Bearer token from Authorization header, calls Clerk JWKS endpoint to verify, returns user_id string. Use httpx to call https://api.clerk.com/v1/tokens/verify with the token as Bearer. Extract user_id from response JSON field "sub". Raise 401 if invalid.

─────────────────────────────
FILE 5: app/routers/tasks.py
─────────────────────────────
All routes require get_current_user dependency.
- POST /tasks — accept {"raw_input": string, "notification_channel": "email"|"messenger"}. Call parser.parse_task(). Create Task row. Set next_run = now + schedule_mins. Return task.
- GET /tasks — return all tasks for current user
- GET /tasks/{task_id} — return single task (must belong to current user)
- DELETE /tasks/{task_id} — hard delete
- PATCH /tasks/{task_id}/pause — set status="paused"
- PATCH /tasks/{task_id}/resume — set status="active", recalculate next_run

─────────────────────────────
FILE 6: app/routers/notifications.py
─────────────────────────────
All routes require get_current_user.
- GET /notifications — return all notifications for current user ordered by sent_at desc
- GET /notifications/task/{task_id} — notifications for a specific task

─────────────────────────────
FILE 7: app/routers/webhooks.py
─────────────────────────────
POST /webhooks/stripe
- Raw body + stripe-signature header
- stripe.Webhook.construct_event() using STRIPE_WEBHOOK_SECRET
- "customer.subscription.created" or "customer.subscription.updated" → set user plan_tier="paid" by matching stripe customer ID
- "customer.subscription.deleted" → set plan_tier="free"
- "invoice.payment_failed" → set plan_tier="free"
- Always return {"status": "ok"}

─────────────────────────────
FILE 8: app/services/parser.py
─────────────────────────────
async def parse_task(raw_input: str) -> dict
- Call GPT-4o-mini with response_format=json_object
- System prompt instructs model to return ONLY this JSON schema:
  {
    "task_type": "web_monitor" | "date_reminder",
    "url": "string or null",
    "condition": "what to watch for",
    "schedule_mins": integer minimum 60,
    "notification_channel": "email" | "messenger"
  }
- Parse and return the dict
- On any error raise HTTPException 422 with detail "Could not parse task input"

─────────────────────────────
FILE 9: app/services/scraper.py
─────────────────────────────
Two functions:
1. async def fetch_static(url: str) -> str — httpx GET, return response.text, timeout=15s, fake User-Agent header
2. async def fetch_dynamic(url: str) -> str — Playwright async, launch chromium headless, goto url wait_until=networkidle, return page.content(), always close browser
Also: async def fetch_page(url: str, requires_js: bool = False) -> str — routes to correct function based on flag

─────────────────────────────
FILE 10: app/services/llm.py
─────────────────────────────
async def check_condition(html_content: str, condition: str) -> tuple[bool, str]
- Truncate html_content to first 8000 chars
- Call Gemini 1.5 Flash (model="gemini-1.5-flash")
- Prompt: "Given this webpage content, does the following condition appear to be met? Condition: {condition}. Answer with JSON only: {"matched": true|false, "summary": "one sentence explanation"}"
- Return (matched: bool, summary: str)
- On error return (False, "Could not analyze content")

─────────────────────────────
FILE 11: app/services/notifier.py
─────────────────────────────
async def send_notification(user_id: str, task: Task, summary: str, channel: str, db: AsyncSession)
- If channel == "email": fetch user email from DB, send via Resend SDK. Subject: "Task Alert: {task condition}". Body: summary.
- If channel == "messenger": fetch MessengerAccount by user_id, POST to https://graph.facebook.com/v19.0/me/messages with META_PAGE_TOKEN, messaging_type=MESSAGE_TAG, tag=CONFIRMED_EVENT_UPDATE
- Write Notification row to DB with status="sent" or "failed"
- Return bool success

─────────────────────────────
FILE 12: app/worker/celery_app.py
─────────────────────────────
Create Celery app with broker=REDIS_URL and backend=REDIS_URL. Import from app.config. Configure: task_serializer=json, result_serializer=json, timezone=UTC. Export as `celery_app`.

─────────────────────────────
FILE 13: app/worker/beat.py
─────────────────────────────
Celery Beat periodic task. Every 5 minutes, run dispatch_due_tasks():
- Open a sync DB session (use sqlalchemy create_engine, not async — Celery workers are sync)
- Query: SELECT tasks WHERE status="active" AND next_run <= NOW()
- For each task: call run_task.delay(task.id)
- Close session

─────────────────────────────
FILE 14: app/worker/tasks.py
─────────────────────────────
@celery_app.task(bind=True, max_retries=3)
def run_task(self, task_id: int):
  1. Open sync DB session, fetch task by id. If not found or status != active, return.
  2. If task_type == "date_reminder": check if today matches config["reminder_date"], if yes notify and set status="done", return.
  3. If task_type == "web_monitor":
     a. Call fetch_page(url, requires_js=config.get("requires_js", False)) — use asyncio.run()
     b. Hash content with hashlib.md5
     c. If hash == task.last_hash: update last_run, write TaskRun(change_detected=False), return
     d. Call check_condition(html, condition) — use asyncio.run()
     e. Write TaskRun(change_detected=True, notif_sent=matched, result_summary=summary)
     f. If matched: call send_notification() — use asyncio.run()
     g. Update task: last_hash=new_hash, last_run=now, next_run=now+schedule_mins
  4. On any exception: self.retry(exc=exc, countdown=60)

─────────────────────────────
ADDITIONAL RULES:
─────────────────────────────
- Every file must be complete and immediately runnable — no "TODO" or placeholder comments
- Use async/await everywhere in FastAPI routes and services
- Celery worker files (beat.py, tasks.py) use synchronous SQLAlchemy (create_engine, not async) because Celery does not support async natively
- All DB queries in routers use the get_db() dependency with AsyncSession
- Never hardcode any key — always use settings.KEY_NAME
- Import Task, User, Notification, MessengerAccount, TaskRun from app.models
- After writing all files, output the exact terminal commands to start the full system:
  1. Start FastAPI dev server
  2. Start Celery worker
  3. Start Celery Beat scheduler