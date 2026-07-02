from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "LinkedIn Job Outreach Assistant API"
    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Database
    database_url: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # LLM provider (agents). Re-check these against console.groq.com/docs/deprecations
    # before release — Groq model availability changes.
    groq_api_key: str
    groq_parsing_model: str = "openai/gpt-oss-20b"
    groq_drafting_model: str = "openai/gpt-oss-120b"

    # Cloudflare R2 (S3-compatible object storage, resume PDFs)
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
