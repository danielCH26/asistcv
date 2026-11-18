"""
Clerk webhook handler.

Receives Svix-signed webhook events from Clerk and keeps local user rows
in sync with Clerk as the source of truth.

Events handled:
- user.created / user.updated: upserts local user fields from Clerk payload.
- user.deleted: logs the event (local row is preserved for FK integrity).
- Any other event type: 200 + debug log.

Authentication: None required (signature verification is the auth mechanism).
Svix signatures are verified using stdlib only (hmac + base64).
"""
import base64
import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.deps import _map_clerk_user_to_local
from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_session_context

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("app.api.webhooks.clerk")

# Svix timestamp tolerance: ±5 minutes in seconds.
_SVIX_TIMESTAMP_TOLERANCE = 5 * 60

# Clerk webhook event types.
_EVENT_USER_CREATED = "user.created"
_EVENT_USER_UPDATED = "user.updated"
_EVENT_USER_DELETED = "user.deleted"


def _svix_verify(raw_body: bytes, headers: dict[str, str], signing_secret: bytes) -> bool:
    """Verify a Svix webhook signature.

    Svix signature header format (v1):
        svix-id: <unique event ID>
        svix-timestamp: <unix timestamp>
        svix-signature: v1,<base64 HMAC-SHA256>

    The signed content is: "{id}.{timestamp}.{raw_body}"
    """
    svix_id = headers.get("svix-id", "")
    svix_ts_str = headers.get("svix-timestamp", "")
    svix_sig = headers.get("svix-signature", "")

    if not svix_id or not svix_ts_str or not svix_sig:
        return False

    try:
        svix_ts = int(svix_ts_str)
    except ValueError:
        return False

    # Reject stale / future timestamps.
    now = int(time.time())
    if abs(now - svix_ts) > _SVIX_TIMESTAMP_TOLERANCE:
        return False

    # Build signed content.
    signed_content = f"{svix_id}.{svix_ts}.{raw_body.decode()}".encode()

    # Compute expected HMAC-SHA256.
    expected_mac = hmac.new(signing_secret, signed_content, hashlib.sha256).digest()

    # svix-signature may be comma-separated: "v1,<b64>,v1,<b64>,..."
    # Parts are like ['v1', '<b64>', 'v1', '<b64>', ...]
    # A valid entry is 'v1,<b64>', which spans two comma-separated items.
    parts = svix_sig.split(",")
    for i, part in enumerate(parts):
        part = part.strip()
        if part == "v1" and i + 1 < len(parts):
            b64_sig = parts[i + 1].strip()
            try:
                provided_mac = base64.b64decode(b64_sig)
            except Exception:  # noqa: BLE001
                continue
            if hmac.compare_digest(provided_mac, expected_mac):
                return True

    return False


def _get_signing_secret() -> bytes | None:
    """Decode CLERK_WEBHOOK_SIGNING_SECRET (strip whsec_ prefix, base64-decode).

    Returns None if the secret is unset, empty, or cannot be decoded.
    """
    settings = get_settings()
    raw = settings.clerk_webhook_signing_secret
    if not raw:
        return None
    # Strip "whsec_" prefix.
    if raw.startswith("whsec_"):
        raw = raw[6:]
    try:
        decoded = base64.b64decode(raw, validate=True)
        return decoded
    except Exception:  # noqa: BLE001
        return None


async def _sync_user(clerk_user: dict, db, *, is_create: bool = False) -> None:
    """Upsert a local user from a Clerk user payload.

    Finds the local row by clerk_id and updates mutable fields:
    email, full_name, avatar_url, email_verified_at, locale.

    Args:
        clerk_user: The Clerk user object from the webhook payload.
        db: AsyncSession to use.
        is_create: If True, INSERT a new row when no local row exists.
                   If False (default), treat unknown clerk_id as best-effort sync
                   and return without creating a row.
    """
    clerk_id = clerk_user["id"]
    fields = _map_clerk_user_to_local(clerk_user)

    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()

    if user is None:
        if not is_create:
            # Unknown clerk_id on updated event: log + 200 (best-effort sync).
            # The API path handles auto-provisioning on next Clerk-session login.
            logger.debug(f"clerk_webhook_unknown_clerk_id clerk_id={clerk_id}")
            return

        # No existing row + is_create: INSERT a new one (user.created).
        user = User(
            email=fields["email"],
            password_hash=fields["password_hash"],
            role=fields["role"],
            full_name=fields["full_name"],
            locale=fields["locale"],
            avatar_url=fields["avatar_url"],
            email_verified_at=fields["email_verified_at"],
            clerk_id=clerk_id,
        )
        db.add(user)
        await db.commit()
        return

    # Update mutable fields.
    user.email = fields["email"]
    user.full_name = fields["full_name"]
    user.avatar_url = fields["avatar_url"]
    user.email_verified_at = fields["email_verified_at"]
    user.locale = fields["locale"]
    user.updated_at = datetime.now(UTC)

    await db.commit()


@router.post("/clerk")
async def clerk_webhook(request: Request):
    """Clerk webhook endpoint.

    Verifies Svix signature, processes user events, and syncs local rows.
    Always returns 200 for verified webhooks to avoid retry storms.
    Returns 503 if CLERK_WEBHOOK_SIGNING_SECRET is not configured.
    """
    signing_secret = _get_signing_secret()
    if signing_secret is None:
        logger.error("clerk_webhook_secret_not_configured")
        raise HTTPException(status_code=503, detail="CLERK_WEBHOOK_SECRET_NOT_CONFIGURED")

    # Read raw body BEFORE any parsing.
    raw_body = await request.body()

    # Extract Svix headers (lowercase FastAPI normalises them).
    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }

    missing = [k for k, v in headers.items() if not v]
    if missing:
        logger.warning(f"clerk_webhook_missing_headers missing={missing}")
        raise HTTPException(status_code=400, detail="MISSING_SVIX_HEADERS")

    if not _svix_verify(raw_body, headers, signing_secret):
        logger.warning(f"clerk_webhook_invalid_signature svix_id={headers['svix-id']}")
        raise HTTPException(status_code=400, detail="INVALID_SIGNATURE")

    # Parse payload.
    import json

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("clerk_webhook_invalid_json")
        raise HTTPException(status_code=400, detail="INVALID_JSON")

    event_type = payload.get("type", "")
    clerk_data = payload.get("data", {})

    if event_type in (_EVENT_USER_CREATED, _EVENT_USER_UPDATED):
        is_create = event_type == _EVENT_USER_CREATED
        async with get_session_context() as session:
            await _sync_user(clerk_data, session, is_create=is_create)

    elif event_type == _EVENT_USER_DELETED:
        clerk_id = clerk_data.get("id")
        logger.info(f"clerk_user_deleted clerk_id={clerk_id}")

    else:
        logger.debug(f"clerk_webhook_ignored_event event_type={event_type}")

    return {"status": "ok"}
