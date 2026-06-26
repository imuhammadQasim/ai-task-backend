# app/services/notifier.py
import httpx
import resend
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime

from app.config import settings
from app.models.user import User
from app.models.notification import Notification
from app.models.messenger_account import MessengerAccount

# Configure resend API key
resend.api_key = settings.RESEND_API_KEY

async def send_notification(user_id: str, task, summary: str, channel: str, db: AsyncSession) -> bool:
    success = False
    now = datetime.utcnow()
    payload = {"summary": summary, "condition": task.config.get("condition")}
    
    # 1. Fetch user to verify email/details
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        # Create failed notification log
        notif = Notification(
            user_id=user_id,
            task_id=task.id,
            channel=channel,
            status="failed",
            payload=payload,
            sent_at=now
        )
        db.add(notif)
        await db.commit()
        return False

    if channel == "email":
        if not settings.RESEND_API_KEY or not user.email:
            # Cannot send without API key or email
            status_str = "failed"
        else:
            try:
                # Prepare subject and body
                subject = f"Task Alert: {task.config.get('condition')}"
                params = {
                    "from": "onboarding@resend.dev", # Default Resend sending email
                    "to": user.email,
                    "subject": subject,
                    "html": f"<p>{summary}</p>"
                }
                resend.Emails.send(params)
                success = True
                status_str = "sent"
            except Exception as e:
                payload["error"] = str(e)
                status_str = "failed"
                
    elif channel == "messenger":
        # Fetch PSID from MessengerAccount
        m_query = select(MessengerAccount).where(MessengerAccount.user_id == user_id)
        m_result = await db.execute(m_query)
        msg_acc = m_result.scalar_one_or_none()
        
        if not msg_acc or not msg_acc.psid or not settings.META_PAGE_TOKEN:
            status_str = "failed"
            payload["error"] = "Messenger account not linked or Meta Token missing"
        else:
            try:
                # Meta Graph API send message
                # POST to https://graph.facebook.com/v19.0/me/messages
                url = f"https://graph.facebook.com/v19.0/me/messages?access_token={settings.META_PAGE_TOKEN}"
                post_data = {
                    "recipient": {"id": msg_acc.psid},
                    "message": {"text": summary},
                    "messaging_type": "MESSAGE_TAG",
                    "tag": "CONFIRMED_EVENT_UPDATE"
                }
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=post_data, timeout=10.0)
                    if resp.status_code == 200:
                        success = True
                        status_str = "sent"
                    else:
                        payload["error"] = resp.text
                        status_str = "failed"
            except Exception as e:
                payload["error"] = str(e)
                status_str = "failed"
    else:
        status_str = "failed"
        payload["error"] = f"Unknown notification channel: {channel}"
        
    # Write Notification row to DB
    notif = Notification(
        user_id=user_id,
        task_id=task.id,
        channel=channel,
        status=status_str,
        payload=payload,
        sent_at=now
    )
    db.add(notif)
    await db.commit()
    return success
