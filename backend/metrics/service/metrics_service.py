import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_usage.models import AgentUsageLog
from applications.models import Application, ApplicationStatusEnum
from metrics.schemas import AgentTokenBreakdown, UserMetricsResponse
from profiles.models import UserProfile

_SENT_STATUSES = (ApplicationStatusEnum.SENT, ApplicationStatusEnum.REPLIED)


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def _agent_token_breakdown(db: AsyncSession, user_id: uuid.UUID, since: datetime) -> list[AgentTokenBreakdown]:
    # Note: CockroachDB's SUM() over an Integer column returns a decimal, and asyncpg's prepared
    # statements reject COALESCE(decimal, <int literal>) as a type mismatch (works fine on plain
    # Postgres) — so nulls (an agent with zero rows in range) are handled in Python, not SQL.
    rows = await db.execute(
        select(
            AgentUsageLog.agent_name,
            func.sum(AgentUsageLog.input_tokens),
            func.sum(AgentUsageLog.output_tokens),
        )
        .where(AgentUsageLog.user_id == user_id, AgentUsageLog.created_at >= since)
        .group_by(AgentUsageLog.agent_name)
    )
    return [
        AgentTokenBreakdown(agent_name=agent_name, input_tokens=int(input_tokens or 0), output_tokens=int(output_tokens or 0))
        for agent_name, input_tokens, output_tokens in rows
    ]


async def get_user_metrics(db: AsyncSession, user_id: uuid.UUID) -> UserMetricsResponse:
    now = datetime.now(timezone.utc)
    today_start = _day_start(now)
    month_start = _month_start(now)

    total_applications = await db.scalar(
        select(func.count()).select_from(Application).where(Application.user_id == user_id)
    )
    total_applications_this_month = await db.scalar(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user_id, Application.created_at >= month_start)
    )
    emails_sent = await db.scalar(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user_id, Application.status.in_(_SENT_STATUSES))
    )
    drafted_not_sent = await db.scalar(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user_id, Application.status == ApplicationStatusEnum.DRAFT_READY)
    )

    status_rows = await db.execute(
        select(Application.status, func.count())
        .where(Application.user_id == user_id)
        .group_by(Application.status)
    )
    applications_by_status = {status.value: count for status, count in status_rows}

    most_used_profile_row = await db.execute(
        select(UserProfile.target_job_title, func.count())
        .join(Application, Application.profile_id == UserProfile.id)
        .where(Application.user_id == user_id)
        .group_by(UserProfile.target_job_title)
        .order_by(func.count().desc())
        .limit(1)
    )
    most_used_profile = most_used_profile_row.first()

    return UserMetricsResponse(
        total_applications=total_applications or 0,
        total_applications_this_month=total_applications_this_month or 0,
        emails_sent=emails_sent or 0,
        drafted_not_sent=drafted_not_sent or 0,
        applications_by_status=applications_by_status,
        most_used_profile=most_used_profile[0] if most_used_profile else None,
        tokens_today=await _agent_token_breakdown(db, user_id, today_start),
        tokens_this_month=await _agent_token_breakdown(db, user_id, month_start),
    )
