import logging
import time

from groq import BadRequestError, RateLimitError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.func import entrypoint, task

from agent_usage.schemas import AgentUsageInfo
from core.config import get_settings

from .schemas import ResumeParserLLMOutput, ResumeParserOutput, normalize_llm_output

logger = logging.getLogger(__name__)

_MAX_FALLBACK_ATTEMPTS = 4

_SYSTEM_PROMPT = """You are a precise resume-to-profile parser for a job outreach platform.

Extract only information that is explicitly present in the resume text. If a field is missing,
ambiguous, or you are not confident about it, leave it unset (null / empty list) rather than
guessing or inventing a value — a human will review and fill in gaps afterward. Never invent job
titles, companies, dates, or skills. Preserve the resume's own wording for the professional
summary and bullet points rather than rephrasing it. Group technical skills into sensible
categories (e.g. "Cloud", "Languages", "Frameworks") based on how they appear in the resume.

For every *_date field, copy the date exactly as written in the resume (e.g. "Jan 2021", "2019",
"03/2020") — do not reformat or convert it yourself. If an end date says "Present"/"Current",
leave that end_date field empty and set currently_working_here to true instead."""


@task
def _run_llm(resume_text: str) -> tuple[ResumeParserLLMOutput, AgentUsageInfo]:
    settings = get_settings()
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=resume_text)]

    # method="json_schema" (Groq's dedicated Structured Output API) for every fallback model, not
    # the default "function_calling". Root-caused during Feature 5: with function_calling,
    # openai/gpt-oss-20b reliably (100% reproducible, not a flake) hallucinated a tool call to a
    # made-up name ("parse_resume" — plausibly guessing a verb-shaped name instead of using the
    # actual bound tool name "ResumeParserLLMOutput") whenever given this agent's real, long system
    # prompt, failing with "Tool call validation failed: ... which was not in request.tools".
    # json_schema mode sidesteps tool-name selection entirely — verified 5/5 successful runs
    # against the exact prompt that failed 100% of the time under function_calling. Only
    # openai/gpt-oss-20b and openai/gpt-oss-120b are confirmed to support *strict* json_schema
    # (guaranteed schema compliance) per Groq's docs — the 3rd/4th fallback models in
    # settings.groq_resume_parser_models are best-effort only, a real known risk (see
    # docs/PROGRESS.md's "Groq multi-model fallback" log), accepted as better than a hard failure.
    #
    # Multi-model fallback: each attempt uses a different model (index 0 = today's original single
    # default) rather than a blind retry of the same model — this is what actually works around a
    # per-model daily quota exhaustion (Groq's rate limits are per model).
    last_error: BadRequestError | RateLimitError | OutputParserException | None = None
    best_result: ResumeParserLLMOutput | None = None
    best_usage: AgentUsageInfo | None = None
    models = settings.groq_resume_parser_models
    for attempt in range(1, _MAX_FALLBACK_ATTEMPTS + 1):
        model = models[min(attempt - 1, len(models) - 1)]
        # max_tokens must cover the whole structured JSON output, not just prose — a resume with
        # many experience/project entries can need several thousand output tokens. Leaving it
        # unset let Groq silently truncate mid-string, which fails JSON parsing. But this account's
        # tokens-per-minute limit for openai/gpt-oss-20b is only 8000 (on_demand tier), and Groq
        # counts prompt + max_tokens against that limit up front — 8192 alone triggered a 413 even
        # for a single request. 4096 leaves headroom for a multi-page resume's prompt tokens while
        # still comfortably covering typical structured output. If this still 413s for a
        # particularly long resume, the account needs a paid Groq tier.
        # reasoning_effort="low" only for gpt-oss models (the only reasoning models in this list —
        # passing it to Llama/Qwen is untested and could error). Doesn't fix the incomplete-
        # extraction issue below (confirmed by direct testing — reasoning tokens dropped to ~11
        # with output still well under the 4096 cap, and the incompleteness still reproduced), but
        # cuts reasoning-token spend and latency for free, which matters given this account's tight
        # daily token budget.
        llm = ChatGroq(
            model=model,
            api_key=settings.groq_api_key,
            temperature=0,
            max_tokens=4096,
            reasoning_effort="low" if "gpt-oss" in model else None,
        )
        structured_llm = llm.with_structured_output(ResumeParserLLMOutput, include_raw=True, method="json_schema")
        try:
            start = time.monotonic()
            result = structured_llm.invoke(messages)
            latency_ms = int((time.monotonic() - start) * 1000)
            parsed = result["parsed"]
            assert isinstance(parsed, ResumeParserLLMOutput)
            raw = result["raw"]
            usage = raw.usage_metadata or {}
            usage_info = AgentUsageInfo(
                model_used=model,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                latency_ms=latency_ms,
            )
            # Confirmed NOT a max_tokens/reasoning-token budget issue (tested above): this model
            # can also return a *successfully parsed but incomplete* result under json_schema mode
            # (e.g. capturing 1 of 3 real work experiences, or every list empty) with no exception
            # at all. Only the fully-empty case is cheaply/reliably detectable here (a resume with
            # literally nothing extracted is almost certainly a bad run, not a genuinely blank
            # resume) — a partial miss (some but not all entries) can't be distinguished from a
            # real short resume and isn't caught by this check. Advancing to the next *model* on
            # this signal (not just retrying the same one) is strictly better odds than before.
            # The Web SPA's "review and correct any misparse" step (per the PRD) is the backstop
            # for whatever slips through. See docs/PROGRESS.md's Feature 5 / fallback logs.
            if not _looks_empty(parsed):
                return parsed, usage_info
            best_result = parsed  # keep in case every attempt comes back this way
            best_usage = usage_info
        except (BadRequestError, RateLimitError, OutputParserException) as exc:
            logger.warning("Resume Parser attempt %d failed on model %s: %s", attempt, model, exc)
            last_error = exc
    if best_result is not None:
        assert best_usage is not None
        return best_result, best_usage
    assert last_error is not None
    raise last_error


def _looks_empty(result: ResumeParserLLMOutput) -> bool:
    return not (
        result.professional_summary
        or result.experiences
        or result.skills
        or result.education
        or result.certifications
        or result.achievements
    )


@entrypoint()
def _resume_parser_graph(resume_text: str) -> tuple[ResumeParserOutput, AgentUsageInfo]:
    result, usage_info = _run_llm(resume_text).result()
    return normalize_llm_output(result), usage_info


async def parse_resume(resume_text: str) -> tuple[ResumeParserOutput, AgentUsageInfo]:
    """Resume Parser agent (A3): raw resume text -> partial UserProfile object + token usage."""
    return await _resume_parser_graph.ainvoke(resume_text)
