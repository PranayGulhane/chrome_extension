from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth.routers.auth_router import router as auth_router
from core.config import get_settings
from profiles.routers.profile_router import router as profile_router

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


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
