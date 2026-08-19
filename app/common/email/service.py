"""
Async-friendly email service used by FastAPI route handlers.
Every send is first persisted as a pending EmailLog row, then enqueued into
the Redis email queue with automatic retries; the RQ worker handles the
actual SMTP delivery via sender.send_email and updates the log's status.
"""

import logging

from rq import Retry
from rq.job import Job
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.email import EmailStatus
from app.common.queue.connection import email_queue
from app.common.email.sender import send_email
from app.core.config import settings
from app.module.email.schema.email_log import EmailLog

logger = logging.getLogger(__name__)

# Total attempts = 1 initial try + MAX_RETRIES retries, before the log is marked failed.
MAX_RETRIES = 2
RETRY_INTERVALS = [30, 120]  # seconds between attempts


async def enqueue_email(*, db: AsyncSession, to: str, subject: str, template: str, context: dict) -> str | None:
    """Persist an EmailLog row, then enqueue the send. Returns the RQ job ID, or None on failure."""
    log = EmailLog(to_email=to, from_email=settings.smtp_from, subject=subject, template=template)
    db.add(log)
    await db.commit()
    await db.refresh(log)

    try:
        job = email_queue.enqueue(
            send_email,
            kwargs={
                "log_id": str(log.id),
                "to": to,
                "subject": subject,
                "template": template,
                "context": context,
            },
            retry=Retry(max=MAX_RETRIES, interval=RETRY_INTERVALS),
        )
        return job.id
    except Exception as exc:
        logger.error("Failed to enqueue email to %s: %s", to, exc)
        log.status = EmailStatus.FAILED.value
        log.last_error = f"enqueue failed: {exc}"
        await db.commit()
        return None


async def enqueue_otp_email(*, db: AsyncSession, to: str, username: str, code: str) -> str | None:
    """Enqueue an OTP verification email."""
    return await enqueue_email(
        db=db,
        to=to,
        subject="Your Finclair AI verification code",
        template="otp_verification.html",
        context={"username": username, "code": code},
    )


async def enqueue_passcode_reset_email(*, db: AsyncSession, to: str, username: str, code: str) -> str | None:
    """Enqueue a passcode reset OTP email."""
    return await enqueue_email(
        db=db,
        to=to,
        subject="Reset your Finclair AI passcode",
        template="passcode_reset.html",
        context={"username": username, "code": code},
    )


def get_job_status(job_id: str) -> dict:
    """Return status of a queued email job."""
    try:
        job = Job.fetch(job_id, connection=email_queue.connection)
        return {"job_id": job_id, "status": job.get_status().value}
    except Exception:
        return {"job_id": job_id, "status": "not_found"}
