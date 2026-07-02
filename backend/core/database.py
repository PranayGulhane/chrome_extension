from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import ParamSpec, TypeVar

from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings

settings = get_settings()

# CockroachDB's `SELECT version()` returns "CockroachDB CCL v25.4.10 (...)", which doesn't match
# SQLAlchemy's "PostgreSQL X.Y" parsing regex and raises AssertionError on first connect. CockroachDB
# is wire/SQL compatible with PostgreSQL 13, so report that fixed version instead of the real one.
# (sqlalchemy-cockroachdb exists to solve this properly but only wraps the sync psycopg2 driver —
# there is no maintained CockroachDB-aware asyncpg dialect.)
PGDialect_asyncpg._get_server_version_info = lambda self, connection: (13, 0)  # type: ignore[method-assign]

engine = create_async_engine(settings.database_url, echo=settings.environment == "development", pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


class SerializationConflictError(Exception):
    """Raised when a transaction still can't commit after exhausting retries. Routers should map
    this to 409 — the client should retry the whole request, not just resend the same statement."""


_RETRYABLE_SQLSTATE = "40001"  # CockroachDB's "restart transaction" / serialization-conflict code
_P = ParamSpec("_P")
_T = TypeVar("_T")


def _is_serialization_conflict(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == _RETRYABLE_SQLSTATE or "restart transaction" in str(exc).lower()


async def with_serialization_retry(
    db: AsyncSession, func: Callable[_P, Awaitable[_T]], *args: _P.args, max_attempts: int = 3, **kwargs: _P.kwargs
) -> _T:
    """Run a read-modify-write service function, retrying the whole thing on a CockroachDB
    serialization conflict (SQLSTATE 40001) rather than surfacing it as a 500. This is CockroachDB's
    own documented pattern for SERIALIZABLE isolation under write contention — two transactions
    racing to update the same rows will have one aborted by the DB (correctly; it's not a bug that
    one loses), and the loser is expected to retry from scratch with a fresh read, not resubmit the
    same statement. `func` must be idempotent/retry-safe: re-running it re-reads current state, so
    every profile_service mutator (fetch-then-mutate-then-commit) already satisfies this."""
    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except DBAPIError as exc:
            await db.rollback()
            if not _is_serialization_conflict(exc):
                raise  # unrelated DB error — let it surface as a 500, don't mask it as a conflict
            if attempt == max_attempts:
                raise SerializationConflictError(
                    f"{func.__name__} did not commit after {max_attempts} attempts"
                ) from exc
    raise AssertionError("unreachable")  # loop always returns or raises
