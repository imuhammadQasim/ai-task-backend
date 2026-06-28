import asyncio
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings


SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def _send_email_sync(
    to_email: str,
    subject: str,
    html: str,
):
    msg = MIMEMultipart("alternative")

    msg["Subject"] = subject
    msg["From"] = settings.GMAIL_EMAIL
    msg["To"] = to_email

    msg.attach(MIMEText(html, "html"))

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)

    server.starttls()

    server.login(
        settings.GMAIL_EMAIL,
        settings.GMAIL_APP_PASSWORD,
    )

    server.sendmail(
        settings.GMAIL_EMAIL,
        to_email,
        msg.as_string(),
    )

    server.quit()


async def send_email(
    to_email: str,
    subject: str,
    html: str,
):
    await asyncio.to_thread(
        _send_email_sync,
        to_email,
        subject,
        html,
    )