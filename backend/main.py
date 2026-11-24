import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from applications.routers.application_router import router as application_router
from auth.routers.auth_router import router as auth_router
from core.config import get_settings
from gmail.routers.gmail_router import router as gmail_router
from mailbox.routers.mailbox_router import router as mailbox_router
from metrics.routers.admin_router import router as admin_router
from metrics.routers.metrics_router import router as metrics_router
from profiles.routers.profile_router import router as profile_router

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(application_router)
app.include_router(gmail_router)
app.include_router(mailbox_router)
app.include_router(metrics_router)
app.include_router(admin_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
