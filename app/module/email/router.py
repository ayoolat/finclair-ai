from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.common.email.service import get_job_status
from app.common.email.sender import send_email
from app.common.queue.connection import email_queue
from app.common.response import ApiResponse
from app.core.config import settings
from app.module.email.dto.email import EnqueueEmailDto, JobStatusDto

router = APIRouter(prefix="/email", tags=["email"])


def _require_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != settings.email_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key.")


@router.post("/enqueue", response_model=ApiResponse[dict], dependencies=[])
async def enqueue_email(
    dto: EnqueueEmailDto,
    x_api_key: str = Header(...),
) -> JSONResponse:
    """
    Enqueue an arbitrary email job. Protected by X-Api-Key header.
    Any server that knows the EMAIL_API_KEY can add to the queue.
    """
    _require_api_key(x_api_key)

    job = email_queue.enqueue(
        send_email,
        kwargs={
            "to": dto.to,
            "subject": dto.subject,
            "template": dto.template,
            "context": dto.context,
        },
    )
    return JSONResponse(
        status_code=202,
        content=ApiResponse.ok(data={"job_id": job.id}, message="Email queued.").model_dump(),
    )


@router.get("/jobs/{job_id}", response_model=ApiResponse[JobStatusDto])
async def job_status(job_id: str, x_api_key: str = Header(...)) -> JSONResponse:
    """Check the delivery status of a queued email job."""
    _require_api_key(x_api_key)
    status = get_job_status(job_id)
    return JSONResponse(
        status_code=200,
        content=ApiResponse.ok(data=status).model_dump(),
    )
