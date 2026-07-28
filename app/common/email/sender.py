"""
Synchronous SMTP sender — runs inside RQ worker processes.
Do not call directly from FastAPI routes; enqueue via email_service instead.
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.core.config import settings

_template_dir = Path(__file__).parent / "templates"
_jinja = Environment(loader=FileSystemLoader(str(_template_dir)), autoescape=True)


def _render(template_name: str, context: dict) -> str:
    return _jinja.get_template(template_name).render(**context)


def send_email(*, to: str, subject: str, template: str, context: dict) -> None:
    html_body = _render(template, context)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=settings.smtp_from.split("@")[-1])
    msg.attach(MIMEText(html_body, "html"))

    ctx = ssl.create_default_context()
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
