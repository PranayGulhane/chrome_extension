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
# address, nothing mail-related — so adding it doesn't violate the PRD's "gmail.send only, not
# gmail.readonly or broader" requirement (that's about *Gmail* scopes specifically).
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
_SCOPE = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/userinfo.email"

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


async def _get_valid_access_token(db: AsyncSession, user_id: uuid.UUID) -> str:
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
) -> str:
    """Sends via the Gmail API, returns the Gmail message id. Raises GmailNotConnectedError /
    GmailApiError — callers map these to HTTP responses."""
    access_token = await _get_valid_access_token(db, user_id)
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
    return response.json()["id"]
