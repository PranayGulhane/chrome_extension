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
    # before release — Groq model availability changes. Each agent gets its own ordered fallback
    # list (index 0 = today's previous single-model default) rather than one shared list, since
    # jd_parser (function_calling) and resume_parser/email_drafter (json_schema) have different
    # proven-safe structured-output methods — a model that's fine for one isn't necessarily safe
    # for the other. Per-attempt logic lives in each agent's agent.py (see docs/PROGRESS.md's
    # "Groq multi-model fallback" log for the full story, including which models are confirmed to
    # support strict json_schema vs. best-effort only).
    groq_api_key: str
    groq_jd_parser_models: list[str] = [
        "openai/gpt-oss-20b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen/qwen3-32b",
        "llama-3.3-70b-versatile",  # deprecated 2026-08-16 — replace before then
    ]
    groq_resume_parser_models: list[str] = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        # Best-effort json_schema only (not strict) below — kept as a last resort over a hard
        # failure, but can silently produce schema-noncompliant output. See docs/PROGRESS.md.
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.3-70b-versatile",  # deprecated 2026-08-16 — replace before then
    ]
    groq_email_drafter_models: list[str] = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "meta-llama/llama-4-scout-17b-16e-instruct",  # best-effort json_schema only, see above
        "llama-3.3-70b-versatile",  # deprecated 2026-08-16 — replace before then
    ]
    groq_relevance_scorer_models: list[str] = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "meta-llama/llama-4-scout-17b-16e-instruct",  # best-effort json_schema only, see above
        "llama-3.3-70b-versatile",  # deprecated 2026-08-16 — replace before then
    ]

    # Cloudflare R2 (S3-compatible object storage, resume PDFs)
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    # Google OAuth2 (PKCE) — gmail.send scope only. redirect_uri must exactly match what's
    # registered on the Google Cloud OAuth client (Web application type). Matches the extension's
    # existing API_BASE_URL (127.0.0.1, not localhost — no cookie/SameSite concern here, this is a
    # top-level browser navigation, not a fetch).
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://127.0.0.1:8123/gmail/oauth/callback"

    # AES-256-GCM key for encrypting Gmail tokens at rest (core/crypto.py). 32 random bytes,
    # base64-encoded. Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    gmail_token_encryption_key: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
