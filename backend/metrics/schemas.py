import uuid
from datetime import date, datetime

from pydantic import BaseModel


class AgentTokenBreakdown(BaseModel):
    agent_name: str
    input_tokens: int
    output_tokens: int


class UserMetricsResponse(BaseModel):
    """PRD §18's "Per-User Metrics" — computed on the fly from applications/agent_usage_logs,
    never a separate stored aggregate. Everything here is a count/sum, never profile/email/post
    content itself."""

    total_applications: int
    total_applications_this_month: int
    emails_sent: int
    drafted_not_sent: int
    applications_by_status: dict[str, int]
    most_used_profile: str | None
    tokens_today: list[AgentTokenBreakdown]
    tokens_this_month: list[AgentTokenBreakdown]


class DailyCount(BaseModel):
    date: date
    count: int


class DailyTokenSpend(BaseModel):
    date: date
    input_tokens: int
    output_tokens: int


class AgentBreakdown(BaseModel):
    agent_name: str
    call_count: int
    avg_latency_ms: float
    input_tokens: int
    output_tokens: int


class AdminOverviewResponse(BaseModel):
    total_users: int
    signups_today: int
    signups_last_14_days: list[DailyCount]
    token_spend_last_14_days: list[DailyTokenSpend]
    agent_breakdown: list[AgentBreakdown]


class AdminUserRow(BaseModel):
    """Deliberately excludes anything content-bearing (PRD §18: admin has "no access to profile
    content, email body, application details, resume text") — only identity + aggregate counts."""

    id: uuid.UUID
    email: str
    created_at: datetime
    last_login_at: datetime | None
    input_tokens: int
    output_tokens: int
    emails_sent: int
    # Feature 10 — admin user-management fields.
    is_active: bool
    access_expires_at: datetime | None
    admin_notes: str | None


class AdminUserAccessUpdateRequest(BaseModel):
    """Both fields are always required (never a partial patch) — see docs/PROGRESS.md's Feature 10
    log for why: a generic PATCH would leave "clear the expiry to make it unlimited" ambiguous with
    "field omitted, leave unchanged"."""

    access_expires_at: datetime | None
    admin_notes: str | None
