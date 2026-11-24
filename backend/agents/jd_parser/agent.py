import logging
import re
import time

from groq import APIStatusError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.func import entrypoint, task

from agent_usage.schemas import AgentUsageInfo
from core.config import get_settings

from .schemas import JDParserOutput

logger = logging.getLogger(__name__)

_MAX_FALLBACK_ATTEMPTS = 4

# Deliberately permissive — this only needs to surface *candidates* for the LLM to confirm/reject,
# not to be the final validator (that happens again below on the LLM's chosen answer).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_SYSTEM_PROMPT = """You are a precise job-post analyzer for a job outreach platform. You are given \
the raw text of a single LinkedIn post.

First decide if this post is actually about hiring for a role (is_hiring). If it is not a hiring \
post, set is_hiring to false and leave the other fields unset — do not invent job data for a post \
that isn't about a job opening.

If it is a hiring post, extract only what's explicitly stated or very strongly implied by the \
text: job_title, company, seniority (e.g. "Senior", "Entry-level", "Staff" — as implied by the \
post, not guessed from the job title alone), location, and a list of required/preferred skills. \
Leave any field you're not confident about unset rather than guessing.

For the email field: candidate email addresses found in the text via regex are listed below, if \
any. Pick the one that is actually the contact/application email for this posting (not, say, an \
email that's part of an unrelated quoted signature or a company's generic support address \
mentioned in passing). If none of the candidates are a genuine contact email, or there are no \
candidates, leave email unset. Never invent an email that isn't one of the listed candidates."""


@task
def _run_llm(post_text: str, email_candidates: list[str]) -> tuple[JDParserOutput, AgentUsageInfo]:
    settings = get_settings()
    candidates_note = (
        f"Candidate emails found by regex: {', '.join(email_candidates)}"
        if email_candidates
        else "Candidate emails found by regex: none"
    )
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"{candidates_note}\n\nPost text:\n{post_text}"),
    ]

    # Deliberately stays on method="function_calling" (the default) for every fallback model,
    # unlike resume_parser/email_drafter's method="json_schema". Tried json_schema here during
    # Feature 5 as a preemptive fix for the same tool-name-hallucination class of bug found in
    # resume_parser — but A/B tested side by side and found json_schema mode silently corrupts
    # THIS schema's output instead (is_hiring/job_title/company/skills/etc. all come back
    # false/empty/null for a post that's unambiguously a hiring post, with no error raised at all
    # — worse than a loud failure). function_calling has never exhibited the hallucination bug for
    # this agent's schema/prompt across every test run this session. Don't "fix" this again
    # without re-running that same A/B comparison — see docs/PROGRESS.md's Feature 5 log.
    #
    # Multi-model fallback: each attempt uses a different model from
    # settings.groq_jd_parser_models (index 0 = today's original single default), not a blind
    # retry of the same model — this is what actually works around a per-model daily quota
    # exhaustion (Groq's rate limits are per model), unlike retrying the same one repeatedly.
    # Catches groq.APIStatusError/OutputParserException broadly (no longer gated to the one
    # specific "did not call a tool" message) since every attempt is already a fresh model — there's
    # no reason to give up early just because this particular failure text doesn't match a known
    # string. APIStatusError is the base class of every HTTP-status error the SDK raises
    # (BadRequestError, RateLimitError, NotFoundError, ...); naming only BadRequest/RateLimit let a
    # decommissioned model id's 404 escape the loop and crash the request before the remaining
    # healthy models were tried. A genuine non-transient bug (bad API key, malformed request) will
    # fail identically across all 4 models and still surface as the final raised error.
    #
    # reasoning_effort="low" for the gpt-oss models only (the sole reasoning models in this list —
    # passing it to Llama/Qwen errors): their reasoning tokens are spent from the same max_tokens
    # budget as the answer, so the old 1024 could be exhausted before the tool call was emitted.
    last_error: APIStatusError | OutputParserException | None = None
    models = settings.groq_jd_parser_models
    for attempt in range(1, _MAX_FALLBACK_ATTEMPTS + 1):
        model = models[min(attempt - 1, len(models) - 1)]
        llm = ChatGroq(
            model=model,
            api_key=settings.groq_api_key,
            temperature=0,
            max_tokens=2048,
            reasoning_effort="low" if "gpt-oss" in model else None,
        )
        structured_llm = llm.with_structured_output(JDParserOutput, include_raw=True)
        try:
            start = time.monotonic()
            result = structured_llm.invoke(messages)
            latency_ms = int((time.monotonic() - start) * 1000)
            parsed = result["parsed"]
            # include_raw=True reports a schema-violating response as parsed=None +
            # parsing_error rather than raising, so the bare assert this replaces escaped the
            # retry loop as an uncaught AssertionError. Especially relevant here, the one agent
            # still on function_calling: "model didn't call the tool" lands in exactly this
            # branch. See agents/resume_parser/agent.py.
            if not isinstance(parsed, JDParserOutput):
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
            logger.warning("JD Parser attempt %d failed on model %s: %s", attempt, model, exc)
            last_error = exc
    assert last_error is not None
    raise last_error


@entrypoint()
def _jd_parser_graph(post_text: str) -> tuple[JDParserOutput, AgentUsageInfo]:
    email_candidates = _EMAIL_RE.findall(post_text)
    result, usage_info = _run_llm(post_text, email_candidates).result()
    # Re-validate the LLM's chosen email against the same regex shape — nulls out anything
    # hallucinated that isn't actually email-shaped, regardless of what the LLM claims.
    if result.email and not _EMAIL_RE.fullmatch(result.email):
        result.email = None
    return result, usage_info


async def parse_job_post(post_text: str) -> tuple[JDParserOutput, AgentUsageInfo]:
    """JD Parser agent (A1): raw LinkedIn post text -> structured job data + token usage."""
    return await _jd_parser_graph.ainvoke(post_text)
