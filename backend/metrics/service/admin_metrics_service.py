from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_usage.models import AgentUsageLog
from applications.models import Application, ApplicationStatusEnum
from auth.models import User
from metrics.schemas import (
    AdminOverviewResponse,
    AdminUserRow,
    AgentBreakdown,
    DailyCount,
    DailyTokenSpend,
)

_TREND_DAYS = 14
_SENT_STATUSES = (ApplicationStatusEnum.SENT, ApplicationStatusEnum.REPLIED)


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_admin_overview(db: AsyncSession) -> AdminOverviewResponse:
    """PRD §18's admin dashboard aggregates — every query here is a count/sum/avg, never a
    profile/email/post-content column, per the "no access to content" rule."""
    now = datetime.now(timezone.utc)
    today_start = _day_start(now)
    trend_start = today_start - timedelta(days=_TREND_DAYS - 1)

    total_users = await db.scalar(select(func.count()).select_from(User))
    signups_today = await db.scalar(select(func.count()).select_from(User).where(User.created_at >= today_start))

    signup_day = func.date_trunc("day", User.created_at)
    signup_rows = await db.execute(
        select(signup_day, func.count())
        .where(User.created_at >= trend_start)
        .group_by(signup_day)
        .order_by(signup_day)
    )
    signups_last_14_days = [DailyCount(date=day.date(), count=count) for day, count in signup_rows]

    # Note: CockroachDB's SUM() over an Integer column returns a decimal, and asyncpg's prepared
    # statements reject COALESCE(decimal, <int literal>) as a type mismatch (works fine on plain
    # Postgres) — so nulls are handled in Python below, not SQL, same as metrics_service.
    spend_day = func.date_trunc("day", AgentUsageLog.created_at)
    spend_rows = await db.execute(
        select(
            spend_day,
            func.sum(AgentUsageLog.input_tokens),
            func.sum(AgentUsageLog.output_tokens),
        )
        .where(AgentUsageLog.created_at >= trend_start)
        .group_by(spend_day)
        .order_by(spend_day)
    )
    token_spend_last_14_days = [
        DailyTokenSpend(date=day.date(), input_tokens=int(input_tokens or 0), output_tokens=int(output_tokens or 0))
        for day, input_tokens, output_tokens in spend_rows
    ]

    agent_rows = await db.execute(
        select(
            AgentUsageLog.agent_name,
            func.count(),
            func.avg(AgentUsageLog.latency_ms),
            func.sum(AgentUsageLog.input_tokens),
            func.sum(AgentUsageLog.output_tokens),
        ).group_by(AgentUsageLog.agent_name)
    )
    agent_breakdown = [
        AgentBreakdown(
            agent_name=agent_name,
            call_count=call_count,
            avg_latency_ms=float(avg_latency_ms) if avg_latency_ms is not None else 0.0,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
        )
        for agent_name, call_count, avg_latency_ms, input_tokens, output_tokens in agent_rows
    ]

    return AdminOverviewResponse(
        total_users=total_users or 0,
        signups_today=signups_today or 0,
        signups_last_14_days=signups_last_14_days,
        token_spend_last_14_days=token_spend_last_14_days,
        agent_breakdown=agent_breakdown,
    )


async def list_admin_users(db: AsyncSession) -> list[AdminUserRow]:
    # Two GROUP BY user_id subqueries outer-joined once to users — each subquery already collapses
    # to one row per user_id, so this can't multiply rows the way a naive join-then-group across
    # two to-many relations (agent_usage_logs, applications) would. See docs/PROGRESS.md's Feature 8
    # log / BUILD_PLAN.md's nested-aggregate backlog note for the pattern this avoids.
    token_totals = (
        select(
            AgentUsageLog.user_id.label("user_id"),
            func.sum(AgentUsageLog.input_tokens).label("input_tokens"),
            func.sum(AgentUsageLog.output_tokens).label("output_tokens"),
        )
        .group_by(AgentUsageLog.user_id)
        .subquery()
    )
    sent_totals = (
        select(
            Application.user_id.label("user_id"),
            func.count().label("emails_sent"),
        )
        .where(Application.status.in_(_SENT_STATUSES))
        .group_by(Application.user_id)
        .subquery()
    )

    # Deliberately no SQL-level COALESCE here — see the note in get_admin_overview above for why
    # CockroachDB rejects COALESCE(decimal, <int literal>) on the summed token columns; None is
    # handled in Python for all three aggregate columns for the same reason, uniformly.
    rows = await db.execute(
        select(
            User.id,
            User.email,
            User.created_at,
            User.last_login_at,
            token_totals.c.input_tokens,
            token_totals.c.output_tokens,
            sent_totals.c.emails_sent,
            User.is_active,
            User.access_expires_at,
            User.admin_notes,
        )
        .outerjoin(token_totals, token_totals.c.user_id == User.id)
        .outerjoin(sent_totals, sent_totals.c.user_id == User.id)
        .order_by(User.created_at.desc())
    )
    return [
        AdminUserRow(
            id=user_id,
            email=email,
            created_at=created_at,
            last_login_at=last_login_at,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            emails_sent=int(emails_sent or 0),
            is_active=is_active,
            access_expires_at=access_expires_at,
            admin_notes=admin_notes,
        )
        for (
            user_id,
            email,
            created_at,
            last_login_at,
            input_tokens,
            output_tokens,
            emails_sent,
            is_active,
            access_expires_at,
            admin_notes,
        ) in rows
    ]
