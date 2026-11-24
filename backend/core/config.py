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
    # Every id below was verified on 2026-08-12 against GET /openai/v1/models AND by actually
    # issuing a structured-output call per model per method — not from the docs, which were wrong
    # here twice. Groq removes models without notice (a removed id returns 404
    # groq.NotFoundError), so re-run that probe when an agent starts failing on one model.
    #
    # Removed since the last check: meta-llama/llama-4-scout-17b-16e-instruct and qwen/qwen3-32b.
    #
    # What the probe established, and why these lists are no longer interchangeable:
    #   json_schema      supported by: gpt-oss-20b, gpt-oss-120b, gpt-oss-safeguard-20b, qwen3.6-27b
    #   function_calling supported by: gpt-oss-*, llama-3.3-70b-versatile, llama-3.1-8b-instant
    # The llama models reject json_schema outright with a 400 ("This model does not support
    # response format `json_schema`"), and qwen3.6-27b reliably fails function_calling ("Failed to
    # call a function"). So llama must NEVER appear in a json_schema agent's list and qwen must
    # never appear in jd_parser's — a wrong entry here is a guaranteed failed attempt, not a
    # degraded one. This is why llama-3.3-70b-versatile is gone from the five json_schema lists it
    # used to sit at the bottom of: it could never have answered a single one of those calls.
    groq_api_key: str
    # jd_parser is the one function_calling agent (see its agent.py for why), so it gets the llama
    # tail rather than qwen. llama-3.3-70b-versatile is deprecated 2026-08-16 — when it goes,
    # llama-3.1-8b-instant is the drop-in successor for this slot (verified working, just weaker).
    groq_jd_parser_models: list[str] = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-safeguard-20b",
        "llama-3.3-70b-versatile",
    ]
    # The json_schema agents below all share the same tail: gpt-oss-safeguard-20b (nominally a
    # safety-classifier model, but verified to produce sound normal output on these agents' real
    # prompts, and cheap — ~200 output tokens for a full email draft) then qwen3.6-27b, which
    # works but is a heavy reasoner and needs a much larger token budget than the others (see the
    # per-model max_tokens in each agent.py).
    groq_resume_parser_models: list[str] = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-safeguard-20b",
        "qwen/qwen3.6-27b",
    ]
    groq_email_drafter_models: list[str] = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-safeguard-20b",
        "qwen/qwen3.6-27b",
    ]
    groq_relevance_scorer_models: list[str] = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-safeguard-20b",
        "qwen/qwen3.6-27b",
    ]
    groq_field_classifier_models: list[str] = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-safeguard-20b",
        "qwen/qwen3.6-27b",
    ]
    groq_followup_drafter_models: list[str] = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-safeguard-20b",
        "qwen/qwen3.6-27b",
    ]

    # Cloudflare R2 (S3-compatible object storage, resume PDFs)
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    # Google OAuth2 (PKCE) — gmail.send + gmail.metadata scopes (see gmail/service/gmail_service.py's
    # _SCOPE for the full string and reasoning). redirect_uri must exactly match what's
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
