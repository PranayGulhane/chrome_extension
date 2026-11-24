import base64
import hashlib
import html
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.crypto import decrypt_token, encrypt_token
from gmail.models import GmailCredential, GmailOAuthState
from gmail.schemas import GmailStatusResponse

logger = logging.getLogger(__name__)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
# Gmail API's own users.getProfile endpoint requires a broader scope than gmail.send alone grants
# (confirmed live: 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT with gmail.send-only). userinfo.email is a
# separate, minimal, non-Gmail identity scope — just discloses the authenticated account's email
# address, nothing mail-related — so adding it doesn't violate the PRD's Gmail-scope minimalism
# requirement (that's about *Gmail* scopes specifically).
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_GMAIL_SEND_URL = f"{_GMAIL_API_BASE}/messages/send"
# Feature 13 (Gmail Follow-Up Manager) added gmail.metadata on top of the original gmail.send-only
# scope — headers/labels only (format=METADATA), Google enforces server-side that no message body
# can ever be returned under this scope, even for a broad mailbox-wide list/page. Never widen to
# gmail.readonly or broader — see docs/prd.html §11's callout for the full reasoning. Already-
# connected users must reconnect once to pick up the wider scope (existing tokens keep working for
# plain sending in the meantime; handle_oauth_callback's upsert just overwrites in place).
_SCOPE = (
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.metadata "
    "https://www.googleapis.com/auth/userinfo.email"
)

_STATE_MAX_AGE = timedelta(minutes=10)
_TOKEN_REFRESH_SKEW = timedelta(seconds=60)


class InvalidOAuthStateError(Exception):
    pass


class GmailNotConnectedError(Exception):
    pass


class GmailApiError(Exception):
    pass


def _generate_pkce_pair() -> tuple[str, str]:
    """S256 PKCE verifier/challenge pair per RFC 7636."""
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


async def start_oauth(db: AsyncSession, user_id: uuid.UUID) -> str:
    settings = get_settings()
    verifier, challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    db.add(GmailOAuthState(user_id=user_id, state=state, code_verifier=verifier))
    await db.commit()

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        # Both required to reliably get a refresh_token back — without prompt=consent, a user
        # who already granted this app once may not get a refresh_token on a later grant.
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


async def handle_oauth_callback(db: AsyncSession, code: str, state: str) -> None:
    oauth_state = await db.scalar(select(GmailOAuthState).where(GmailOAuthState.state == state))
    if oauth_state is None:
        raise InvalidOAuthStateError("Unknown or already-used OAuth state.")
    if datetime.now(timezone.utc) - oauth_state.created_at.replace(tzinfo=timezone.utc) > _STATE_MAX_AGE:
        await db.execute(delete(GmailOAuthState).where(GmailOAuthState.id == oauth_state.id))
        await db.commit()
        raise InvalidOAuthStateError("This authorization link expired — please try connecting again.")

    user_id = oauth_state.user_id
    code_verifier = oauth_state.code_verifier
    settings = get_settings()

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            },
        )
        if token_response.status_code != 200:
            logger.error("Gmail OAuth token exchange failed: %s", token_response.text)
            raise GmailApiError("Google rejected the authorization code.")
        token_data = token_response.json()

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        if refresh_token is None:
            # Happens if the user had already granted this exact app access and Google decided
            # not to re-issue one despite prompt=consent — rare, but without a refresh_token we
            # can't auto-renew later, so treat this as a hard failure and ask them to retry
            # (revoking prior access from Google's side first would guarantee a fresh one).
            raise GmailApiError(
                "Google did not return a refresh token — try disconnecting any prior access to "
                "this app in your Google Account settings, then connect again."
            )
        expires_in = token_data.get("expires_in", 3600)

        profile_response = await client.get(
            _USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if profile_response.status_code != 200:
            logger.error("Gmail address fetch failed: %s", profile_response.text)
            raise GmailApiError("Could not fetch the Gmail address for this account.")
        gmail_address = profile_response.json()["email"]

    existing = await db.scalar(select(GmailCredential).where(GmailCredential.user_id == user_id))
    token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    if existing is None:
        db.add(
            GmailCredential(
                user_id=user_id,
                gmail_address=gmail_address,
                access_token_enc=encrypt_token(access_token),
                refresh_token_enc=encrypt_token(refresh_token),
                token_expiry=token_expiry,
            )
        )
    else:
        existing.gmail_address = gmail_address
        existing.access_token_enc = encrypt_token(access_token)
        existing.refresh_token_enc = encrypt_token(refresh_token)
        existing.token_expiry = token_expiry

    await db.execute(delete(GmailOAuthState).where(GmailOAuthState.id == oauth_state.id))
    await db.commit()


async def get_status(db: AsyncSession, user_id: uuid.UUID) -> GmailStatusResponse:
    credential = await db.scalar(select(GmailCredential).where(GmailCredential.user_id == user_id))
    if credential is None:
        return GmailStatusResponse(connected=False)
    try:
        # Reuses the same refresh-if-near-expiry path every other Gmail call goes through, so this
        # only actually hits Google's token endpoint when the cached access token is stale — not on
        # every status check. Catching the failure here (rather than just checking row existence)
        # is what lets a dead/revoked refresh token (e.g. Google's 7-day testing-mode expiry) show
        # up as "not connected" instead of silently staying "connected" until the next send fails.
        await get_valid_access_token(db, user_id)
    except GmailApiError:
        return GmailStatusResponse(connected=False)
    return GmailStatusResponse(connected=True, gmail_address=credential.gmail_address)


async def disconnect(db: AsyncSession, user_id: uuid.UUID) -> None:
    credential = await db.scalar(select(GmailCredential).where(GmailCredential.user_id == user_id))
    if credential is None:
        return

    # Best-effort revoke at Google's end — the local row is deleted regardless, since the whole
    # point of "Disconnect" is that this app can no longer act on the user's behalf even if the
    # revoke call itself fails (network blip, token already invalid, etc).
    try:
        refresh_token = decrypt_token(credential.refresh_token_enc)
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(_GOOGLE_REVOKE_URL, data={"token": refresh_token})
    except Exception:
        logger.exception("Gmail token revoke call failed for user %s (local disconnect proceeds anyway)", user_id)

    await db.delete(credential)
    await db.commit()


async def get_valid_access_token(db: AsyncSession, user_id: uuid.UUID) -> str:
    credential = await db.scalar(select(GmailCredential).where(GmailCredential.user_id == user_id))
    if credential is None:
        raise GmailNotConnectedError("Gmail is not connected for this account.")

    if credential.token_expiry.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc) > _TOKEN_REFRESH_SKEW:
        return decrypt_token(credential.access_token_enc)

    settings = get_settings()
    refresh_token = decrypt_token(credential.refresh_token_enc)
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code != 200:
        logger.error("Gmail token refresh failed for user %s: %s", user_id, response.text)
        raise GmailApiError("Could not refresh the Gmail access token.")
    token_data = response.json()
    new_access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)

    credential.access_token_enc = encrypt_token(new_access_token)
    credential.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    await db.commit()
    return new_access_token


def _build_mime_message(
    *, to: str, subject: str, body_text: str, attachment_bytes: bytes, attachment_filename: str
) -> MIMEMultipart:
    body_html = html.escape(body_text).replace("\n", "<br>\n")

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(body_text, "plain"))
    alternative.attach(MIMEText(body_html, "html"))

    message = MIMEMultipart("mixed")
    message["To"] = to
    message["Subject"] = subject
    message.attach(alternative)

    attachment = MIMEApplication(attachment_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename=attachment_filename)
    message.attach(attachment)
    return message


async def send_message(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    to: str,
    subject: str,
    body_text: str,
    attachment_bytes: bytes,
    attachment_filename: str,
) -> tuple[str, str]:
    """Sends via the Gmail API, returns (message_id, thread_id). Raises GmailNotConnectedError /
    GmailApiError — callers map these to HTTP responses. Both ids are already present in the send
    response — Feature 13 needs thread_id to later flag/relate this send in the mailbox view, so
    it's returned now instead of being discarded like before."""
    access_token = await get_valid_access_token(db, user_id)
    message = _build_mime_message(
        to=to,
        subject=subject,
        body_text=body_text,
        attachment_bytes=attachment_bytes,
        attachment_filename=attachment_filename,
    )
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _GMAIL_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
        )
    if response.status_code != 200:
        logger.error("Gmail send failed for user %s: %s", user_id, response.text)
        raise GmailApiError("Gmail API rejected the send request.")
    body = response.json()
    return body["id"], body["threadId"]


def _build_reply_mime_message(
    *, to: str, subject: str, body_text: str, in_reply_to_message_id: str
) -> MIMEText:
    message = MIMEText(body_text, "plain")
    message["To"] = to
    message["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    # RFC 2822 threading headers — Gmail primarily groups by threadId (set alongside "raw" in the
    # send call below), but setting these too keeps the message properly threaded for any other
    # RFC-compliant client the recipient might use. References is kept to just the one id being
    # replied to rather than the full chain — Gmail tolerates this fine, and it avoids fetching
    # every prior message in the thread just to build a header most clients don't inspect deeply.
    message["In-Reply-To"] = in_reply_to_message_id
    message["References"] = in_reply_to_message_id
    return message


async def send_reply(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    to: str,
    subject: str,
    body_text: str,
    thread_id: str,
    in_reply_to_message_id: str,
) -> tuple[str, str]:
    """Sends a plain-text follow-up into an existing Gmail thread (Feature 13) — no attachment,
    unlike send_message. Returns (message_id, thread_id). Raises GmailNotConnectedError /
    GmailApiError, same as send_message."""
    access_token = await get_valid_access_token(db, user_id)
    message = _build_reply_mime_message(
        to=to, subject=subject, body_text=body_text, in_reply_to_message_id=in_reply_to_message_id
    )
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _GMAIL_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw, "threadId": thread_id},
        )
    if response.status_code != 200:
        logger.error("Gmail reply send failed for user %s: %s", user_id, response.text)
        raise GmailApiError("Gmail API rejected the follow-up send request.")
    body = response.json()
    return body["id"], body["threadId"]


async def list_sent_messages_page(
    access_token: str,
    *,
    page_size: int,
    page_token: str | None,
) -> tuple[list[str], str | None, int | None]:
    """One page of Sent message ids, newest-first (Gmail's default order for this query — there is
    no explicit sort parameter in the API). Returns (message_ids, next_page_token,
    result_size_estimate). Single page only — no automatic pagination-loop here, the caller decides
    whether/when to fetch another page (Feature 13's UI paginates on user action).

    Uses labelIds=SENT rather than a q= search. Confirmed live: the gmail.metadata scope this app
    requests (see _SCOPE) rejects the q parameter outright ("Metadata scope does not support 'q'
    parameter", 403) — q requires a broader scope like gmail.readonly, which this app deliberately
    avoids (see docs/prd.html §11). Date-range filtering therefore can't happen server-side anymore;
    mailbox_service.get_sent_mail_page applies it client-side instead, over each page's fetched
    metadata."""
    params = {"labelIds": "SENT", "maxResults": str(page_size)}
    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_GMAIL_API_BASE}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    if response.status_code != 200:
        logger.error("Gmail messages.list failed: %s", response.text)
        raise GmailApiError("Gmail API rejected the mailbox list request.")
    body = response.json()
    ids = [m["id"] for m in body.get("messages", [])]
    return ids, body.get("nextPageToken"), body.get("resultSizeEstimate")


def _headers_to_dict(payload: dict) -> dict[str, str]:
    return {h["name"]: h["value"] for h in payload.get("headers", [])}


async def get_message_metadata(access_token: str, message_id: str) -> dict:
    """Headers-only fetch (format=metadata — gmail.metadata scope cannot return more even if
    asked). Returns {subject, recipient, sent_at, thread_id, message_id_header}."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_GMAIL_API_BASE}/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "format": "metadata",
                "metadataHeaders": ["Subject", "To", "Date", "Message-Id"],
            },
        )
    if response.status_code != 200:
        logger.error("Gmail messages.get (metadata) failed for %s: %s", message_id, response.text)
        raise GmailApiError("Gmail API rejected the message metadata request.")
    body = response.json()
    headers = _headers_to_dict(body.get("payload", {}))
    sent_at = None
    if "internalDate" in body:
        sent_at = datetime.fromtimestamp(int(body["internalDate"]) / 1000, tz=timezone.utc)
    return {
        "subject": headers.get("Subject"),
        "recipient": headers.get("To"),
        "sent_at": sent_at,
        "thread_id": body["threadId"],
        "message_id_header": headers.get("Message-Id") or headers.get("Message-ID"),
    }


async def get_thread_reply_status(
    access_token: str, thread_id: str, own_gmail_address: str
) -> tuple[bool, str | None]:
    """Headers-only thread inspection (format=metadata). Returns (reply_detected,
    latest_message_id_header) — reply_detected is True if any message in the thread was sent by
    someone other than own_gmail_address; latest_message_id_header is the RFC Message-Id of the
    thread's most recent message, used as the In-Reply-To target for the next follow-up."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_GMAIL_API_BASE}/threads/{thread_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "format": "metadata",
                "metadataHeaders": ["From", "Date", "Message-Id"],
            },
        )
    if response.status_code != 200:
        logger.error("Gmail threads.get (metadata) failed for %s: %s", thread_id, response.text)
        raise GmailApiError("Gmail API rejected the thread metadata request.")
    body = response.json()
    own_address = own_gmail_address.lower()
    reply_detected = False
    latest_message_id_header: str | None = None
    for message in body.get("messages", []):
        headers = _headers_to_dict(message.get("payload", {}))
        _, from_address = parseaddr(headers.get("From", ""))
        if from_address and from_address.lower() != own_address:
            reply_detected = True
        message_id_header = headers.get("Message-Id") or headers.get("Message-ID")
        if message_id_header:
            latest_message_id_header = message_id_header
    return reply_detected, latest_message_id_header
