from pydantic import BaseModel, EmailStr


class EnqueueEmailDto(BaseModel):
    to: EmailStr
    subject: str
    template: str
    context: dict


class JobStatusDto(BaseModel):
    job_id: str
    status: str
