import json
import logging
from typing import Optional

import firebase_admin
from firebase_admin import auth, credentials, messaging

from app.core.config import settings

logger = logging.getLogger(__name__)

_app: firebase_admin.App | None = None


def _get_app() -> firebase_admin.App:
    global _app
    if _app is None:
        cred_dict = json.loads(settings.firebase_credentials_json)
        cred = credentials.Certificate(cred_dict)
        _app = firebase_admin.initialize_app(cred)
    return _app


def verify_firebase_token(id_token: str) -> dict:
    """Verify a Firebase ID token and return its decoded claims."""
    _get_app()
    return auth.verify_id_token(id_token)


def send_push(
    tokens: list[str],
    title: str,
    body: str,
    data: Optional[dict[str, str]] = None,
) -> Optional[messaging.BatchResponse]:
    """
    Send a push notification to one or more FCM device tokens.
    No-ops (logs a warning) if Firebase isn't configured, rather than raising —
    a missing push credential should never break the caller's business logic.
    """
    if not tokens:
        return None
    if not settings.firebase_credentials_json:
        logger.warning("Push notification skipped — FIREBASE_CREDENTIALS_JSON not configured.")
        return None

    _get_app()
    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        tokens=tokens,
    )
    return messaging.send_each_for_multicast(message)
