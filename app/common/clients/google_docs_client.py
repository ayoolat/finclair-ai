import json
import logging
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.core.config import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_CACHE_TTL_SECONDS = 300
_MAX_CONTENT_CHARS = 60000  # ~15k tokens — well under gpt-4o-mini's context, with headroom as the doc grows

_drive_service = None
_cache_content: str = ""
_cache_fetched_at: float = 0.0


def _get_drive_service():
    global _drive_service
    if _drive_service is None:
        info = json.loads(settings.google_service_account_json)
        credentials = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
        _drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return _drive_service


def get_app_help_content() -> str:
    """
    Fetch the Clara app-help Google Doc as plain text, cached for a few minutes.
    Returns "" if the integration isn't configured, and falls back to the last
    known-good cached content (rather than raising) if a refresh fails — a
    transient Google API error shouldn't break Clara's whole reply.
    """
    global _cache_content, _cache_fetched_at

    if not settings.google_service_account_json or not settings.clara_help_doc_id:
        return ""

    if _cache_content and (time.monotonic() - _cache_fetched_at) < _CACHE_TTL_SECONDS:
        return _cache_content

    try:
        service = _get_drive_service()
        raw = service.files().export(fileId=settings.clara_help_doc_id, mimeType="text/plain").execute()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        _cache_content = text.strip()[:_MAX_CONTENT_CHARS]
        _cache_fetched_at = time.monotonic()
    except Exception:
        logger.exception("Failed to fetch Clara help doc %s", settings.clara_help_doc_id)

    return _cache_content
