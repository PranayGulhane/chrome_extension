from pydantic import BaseModel


class AgentUsageInfo(BaseModel):
    """Returned by an agent alongside its real output. Not a DB-facing schema — callers turn this
    into an AgentUsageLog row themselves (they're the ones who know user_id/agent_name)."""

    model_used: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
