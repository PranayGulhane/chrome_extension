from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import CurrentUser
from gmail.schemas import GmailAuthorizeResponse, GmailStatusResponse
from gmail.service import gmail_service
from gmail.service.gmail_service import InvalidOAuthStateError

router = APIRouter(prefix="/gmail", tags=["gmail"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

_SUCCESS_HTML = """<!doctype html><html><body style="font-family:sans-serif;text-align:center;padding:60px">
<h2>Gmail connected</h2><p>You can close this tab and go back to the extension.</p></body></html>"""


def _error_html(message: str) -> str:
    return (
        '<!doctype html><html><body style="font-family:sans-serif;text-align:center;padding:60px">'
        f"<h2>Couldn't connect Gmail</h2><p>{message}</p>"
        "<p>Close this tab and try again from the extension.</p></body></html>"
    )


@router.post("/oauth/start", response_model=GmailAuthorizeResponse)
async def start_oauth(user: CurrentUser, db: DbSession) -> GmailAuthorizeResponse:
    authorize_url = await gmail_service.start_oauth(db, user.id)
    return GmailAuthorizeResponse(authorize_url=authorize_url)


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str, state: str, db: DbSession) -> HTMLResponse:
    # Deliberately no auth dependency here — this is a top-level browser redirect from Google,
    # not a fetch from our own code, so it carries no JWT/cookie. `state` is what ties this back
    # to a user (see gmail_service.start_oauth/handle_oauth_callback).
    try:
        await gmail_service.handle_oauth_callback(db, code, state)
    except InvalidOAuthStateError as exc:
        return HTMLResponse(_error_html(str(exc)), status_code=status.HTTP_400_BAD_REQUEST)
    except gmail_service.GmailApiError as exc:
        return HTMLResponse(_error_html(str(exc)), status_code=status.HTTP_502_BAD_GATEWAY)
    return HTMLResponse(_SUCCESS_HTML)


@router.get("/status", response_model=GmailStatusResponse)
async def get_status(user: CurrentUser, db: DbSession) -> GmailStatusResponse:
    return await gmail_service.get_status(db, user.id)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: CurrentUser, db: DbSession) -> None:
    await gmail_service.disconnect(db, user.id)
