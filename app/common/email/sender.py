"""
Synchronous Brevo API sender — runs inside RQ worker processes.
Do not call directly from FastAPI routes; enqueue via email_service instead.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from jinja2 import Environment, FileSystemLoader
from rq import get_current_job

from app.common.enums.email import EmailStatus
from app.core.config import settings
from app.database.session import AsyncSessionLocal, engine
from app.module.email.schema.email_log import EmailLog

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

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

    payload = {
        "sender": {"name": settings.smtp_from_name, "email": settings.smtp_from},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html_body,
    }
    headers = {
        "api-key": settings.brevo_api_key,
        "content-type": "application/json",
        "accept": "application/json",
    }

    try:
        response = httpx.post(BREVO_ENDPOINT, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        job = get_current_job()
        final_attempt = job is None or not job.retries_left
        asyncio.run(_record_attempt(log_id, success=False, error=str(exc), final=final_attempt))
        raise
    else:
        asyncio.run(_record_attempt(log_id, success=True))
