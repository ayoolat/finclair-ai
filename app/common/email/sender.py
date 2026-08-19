"""
Synchronous SMTP sender — runs inside RQ worker processes.
Do not call directly from FastAPI routes; enqueue via email_service instead.
"""

import asyncio
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from rq import get_current_job

from app.common.enums.email import EmailStatus
from app.core.config import settings
from app.database.session import AsyncSessionLocal, engine
from app.module.email.schema.email_log import EmailLog

_template_dir = Path(__file__).parent / "templates"
_jinja = Environment(loader=FileSystemLoader(str(_template_dir)), autoescape=True)


def _render(template_name: str, context: dict) -> str:
    return _jinja.get_template(template_name).render(**context)


async def _record_attempt(log_id: str, *, success: bool, error: str | None = None, final: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        log = await db.get(EmailLog, uuid.UUID(log_id))
        if log is None:
            return
        log.attempts += 1
        if success:
            log.status = EmailStatus.SENT.value
            log.sent_at = datetime.now(timezone.utc)
            log.last_error = None
        else:
            log.last_error = error
            log.status = EmailStatus.FAILED.value if final else EmailStatus.PENDING.value
        await db.commit()
    # Each RQ job execution gets its own asyncio.run() loop; drop pooled
    # connections so the next call doesn't reuse them from a closed loop.
    await engine.dispose()


def send_email(*, log_id: str, to: str, subject: str, template: str, context: dict) -> None:
    html_body = _render(template, context)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=settings.smtp_from.split("@")[-1])
    msg.attach(MIMEText(html_body, "html"))

    ctx = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.smtp_from, to, msg.as_string())
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.smtp_from, to, msg.as_string())
    except Exception as exc:
        job = get_current_job()
        final_attempt = job is None or not job.retries_left
        asyncio.run(_record_attempt(log_id, success=False, error=str(exc), final=final_attempt))
        raise
    else:
        asyncio.run(_record_attempt(log_id, success=True))
