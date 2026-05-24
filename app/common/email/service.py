"""
Async-friendly email service used by FastAPI route handlers.
All methods enqueue jobs into the Redis email queue; the RQ worker
handles the actual SMTP delivery via sender.send_email.
"""

from rq.job import Job

from app.common.queue.connection import email_queue
from app.common.email.sender import send_email


def enqueue_otp_email(*, to: str, username: str, code: str) -> str:
    """Enqueue an OTP verification email. Returns the RQ job ID."""
    job = email_queue.enqueue(
        send_email,
        kwargs={
            "to": to,
            "subject": "Your Finclair verification code",
            "template": "otp_verification.html",
            "context": {"username": username, "code": code},
        },
    )
    return job.id


def enqueue_passcode_reset_email(*, to: str, username: str, code: str) -> str:
    """Enqueue a passcode reset OTP email. Returns the RQ job ID."""
    job = email_queue.enqueue(
        send_email,
        kwargs={
            "to": to,
            "subject": "Reset your Finclair passcode",
            "template": "passcode_reset.html",
            "context": {"username": username, "code": code},
        },
    )
    return job.id


def get_job_status(job_id: str) -> dict:
    """Return status of a queued email job."""
    try:
        job = Job.fetch(job_id, connection=email_queue.connection)
        return {"job_id": job_id, "status": job.get_status().value}
    except Exception:
        return {"job_id": job_id, "status": "not_found"}
