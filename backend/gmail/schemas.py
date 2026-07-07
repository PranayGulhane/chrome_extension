from pydantic import BaseModel


class GmailStatusResponse(BaseModel):
    connected: bool
    gmail_address: str | None = None


class GmailAuthorizeResponse(BaseModel):
    authorize_url: str
