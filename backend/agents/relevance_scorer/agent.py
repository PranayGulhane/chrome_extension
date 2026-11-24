import logging
import time

from groq import APIStatusError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.func import entrypoint, task

from agent_usage.schemas import AgentUsageInfo
from core.config import get_settings

from .schemas import RelevanceScorerContext, RelevanceScorerOutput

logger = logging.getLogger(__name__)

_MAX_FALLBACK_ATTEMPTS = 4

_SYSTEM_PROMPT = """You are an expert technical recruiter helping a job seeker decide whether a \
LinkedIn hiring post is worth applying to.

Score how well the parsed job post matches the candidate's profile, from 0 (no fit at all) to 100 \
(excellent fit). Ground the score only in the details you're given below — never invent skills, \
experience, or requirements that aren't present in that context.

Guidelines:
- Weigh overlap between the post's required/preferred skills and the candidate's actual skills \
and experience most heavily.
- Consider seniority fit (e.g. a senior-level post against a junior candidate should score lower) \
and location fit if both are known.
- If the post is missing a lot of detail (e.g. no skills listed), score conservatively around the \
middle rather than guessing high or low.
- Write a short (1-2 sentence) reasoning explaining the score in plain language the candidate can \
act on (what matches well, what doesn't).
"""


@task
def _run_llm(context: RelevanceScorerContext) -> tuple[RelevanceScorerOutput, AgentUsageInfo]:
    settings = get_settings()
    details = [
        f"Job title: {context.job_title or 'unknown'}",
        f"Company: {context.company or 'unknown'}",
        f"Seniority: {context.seniority or 'unknown'}",
        f"Location: {context.location or 'unknown'}",
        f"Required/preferred skills mentioned in the post: "
        f"{', '.join(context.skills) if context.skills else 'none listed'}",
        f"\nCandidate profile:\n{context.profile_context}",
    ]
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content="\n".join(details))]

    # Same multi-model fallback + method="json_schema" pattern as every other agent in this
    # codebase — see agents/resume_parser/agent.py / docs/PROGRESS.md's "Groq multi-model
    # fallback" log for why json_schema is the proven-safe default over function_calling.
    # Catches groq.APIStatusError (base class of BadRequestError/RateLimitError/NotFoundError/...)
    # so a decommissioned model id, which returns 404, advances to the next model instead of
    # escaping the loop — see agents/email_drafter/agent.py for the incident this came from.
    # 400 was the tightest max_tokens of any agent here and this output is short, but gpt-oss burns
    # reasoning tokens out of the same budget before emitting any JSON, so it was the likeliest of
    # all of them to hit json_validate_failed. reasoning_effort="low" + a bigger cap covers both.
    last_error: APIStatusError | OutputParserException | None = None
    models = settings.groq_relevance_scorer_models
    for attempt in range(1, _MAX_FALLBACK_ATTEMPTS + 1):
        model = models[min(attempt - 1, len(models) - 1)]
        llm = ChatGroq(
            model=model,
            api_key=settings.groq_api_key,
            temperature=0.2,
            # qwen3.6-27b needs a far larger budget than the gpt-oss models — it reasons heavily
            # with no reasoning_effort control and 400s outright when truncated (measured: 1263
            # output tokens even for this agent's tiny score+reason schema, failing at 1024).
            max_tokens=4096 if "qwen" in model else 1024,
            reasoning_effort="low" if "gpt-oss" in model else None,
        )
        structured_llm = llm.with_structured_output(RelevanceScorerOutput, include_raw=True, method="json_schema")
        try:
            start = time.monotonic()
            result = structured_llm.invoke(messages)
            latency_ms = int((time.monotonic() - start) * 1000)
            parsed = result["parsed"]
            # include_raw=True reports a schema-violating response as parsed=None +
            # parsing_error rather than raising, so the bare assert this replaces escaped the
            # retry loop as an uncaught AssertionError. See agents/resume_parser/agent.py.
            if not isinstance(parsed, RelevanceScorerOutput):
                err = result["parsing_error"]
                if isinstance(err, OutputParserException):
                    raise err
                raise OutputParserException(f"no schema-valid output (parsing_error={err!r})")
            raw = result["raw"]
            usage = raw.usage_metadata or {}
            usage_info = AgentUsageInfo(
                model_used=model,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                latency_ms=latency_ms,
            )
            return parsed, usage_info
        except (APIStatusError, OutputParserException) as exc:
            logger.warning("Relevance Scorer attempt %d failed on model %s: %s", attempt, model, exc)
            last_error = exc
    assert last_error is not None
    raise last_error


@entrypoint()
def _relevance_scorer_graph(context: RelevanceScorerContext) -> tuple[RelevanceScorerOutput, AgentUsageInfo]:
    return _run_llm(context).result()


async def score_post(context: RelevanceScorerContext) -> tuple[RelevanceScorerOutput, AgentUsageInfo]:
    """Post Relevance Scorer agent (A4): parsed JD + profile context -> a 0-100 match score with
    reasoning. Callers should treat any exception as non-fatal (score is a best-effort signal, not
    a blocker on extraction succeeding) — see application_service.create_from_extraction."""
    return await _relevance_scorer_graph.ainvoke(context)
