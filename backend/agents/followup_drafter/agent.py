import logging
import time

from groq import APIStatusError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.func import entrypoint, task

from agent_usage.schemas import AgentUsageInfo
from core.config import get_settings

from .schemas import FollowupDraftContext, FollowupDraftOutput

logger = logging.getLogger(__name__)

_MAX_FALLBACK_ATTEMPTS = 4

# grounding="full" — a Platform row: the original email body is on file in this platform's own DB,
# so this can be a real, specific follow-up, same quality bar as the Email Drafter (A2).
_FULL_SYSTEM_PROMPT = """You are helping a job seeker write a brief follow-up email to a recruiter \
or hiring contact they already emailed once, with no reply yet.

You are given the candidate's original email (subject + body) and the job context it was about. \
Ground the follow-up only in those details — never invent new facts, skills, or claims that \
weren't already in the original email. This is a nudge, not a second pitch.

Guidelines:
- Reference the original email briefly (e.g. "I wanted to follow up on my note about the {{job \
title}} role...") rather than restating the whole pitch.
- follow_up_number tells you how many follow-ups have already gone out on this thread (this one \
is number N). Tone should shift with N: the 1st follow-up is a light, low-pressure nudge; by the \
2nd or later, be a bit more direct (e.g. explicitly asking if the role is still open, or if there's \
someone else better to reach) without ever being pushy or impatient.
- Keep it short — 60-100 words. Shorter than the original email.
- Subject should be "Re: " followed by the original subject, unless the original subject already \
starts with "Re:".
- End with a clear, low-friction call to action.
"""

# grounding="subject_only" — an External row: the backend never read this email's body (gmail.metadata
# scope structurally cannot return one), so the draft must stay generic and shorter, and must not
# pretend to know content it was never given.
_SUBJECT_ONLY_SYSTEM_PROMPT = """You are helping a user write a brief follow-up email to someone \
they already emailed once, with no reply yet. You do NOT have the original email's body — only its \
subject line. Do not guess or invent what the original email said.

Write a short, generic-but-polite nudge that references the subject line only (e.g. "I wanted to \
follow up on my earlier email regarding '{{subject}}'..."). Do not claim to remember specific \
details, skills, or asks from the original email — you don't have them.

Guidelines:
- follow_up_number tells you how many follow-ups have already gone out on this thread. Tone should \
shift with N the same way a human's would: gentle on the 1st, a bit more direct by the 2nd or later.
- Keep it very short — 40-70 words.
- Subject should be "Re: " followed by the original subject, unless it already starts with "Re:".
- End with a simple, low-friction call to action (e.g. asking if they saw the earlier email, or if \
now's a better time to reconnect).
"""


@task
def _run_llm(context: FollowupDraftContext) -> tuple[FollowupDraftOutput, AgentUsageInfo]:
    settings = get_settings()
    subject = context.original_subject or "(no subject on file)"
    details = [
        f"Original subject: {subject}",
        f"Days since the original email was sent: {context.days_since_sent}",
        f"This is follow-up number: {context.follow_up_number}",
    ]
    if context.grounding == "full":
        details.append(f"Job title: {context.job_title or 'unknown'}")
        details.append(f"Company: {context.company or 'unknown'}")
        details.append(f"Original email body:\n{context.original_body or ''}")
        system_prompt = _FULL_SYSTEM_PROMPT
    else:
        system_prompt = _SUBJECT_ONLY_SYSTEM_PROMPT
    messages = [SystemMessage(content=system_prompt), HumanMessage(content="\n".join(details))]

    # method="json_schema", include_raw=True — same reasoning/precedent as agents/email_drafter and
    # agents/field_classifier (see their comments). Multi-model fallback, one different model per
    # attempt via settings.groq_followup_drafter_models, not a blind retry of the same model.
    # Catches groq.APIStatusError (base class of BadRequestError/RateLimitError/NotFoundError/...)
    # so a decommissioned model id, which returns 404, advances to the next model instead of
    # escaping the loop — see agents/email_drafter/agent.py for the incident this came from.
    # max_tokens and reasoning_effort likewise: gpt-oss reasoning tokens spend this same budget
    # before the JSON starts, and 600 was tight enough to risk a json_validate_failed 400.
    last_error: APIStatusError | OutputParserException | None = None
    models = settings.groq_followup_drafter_models
    for attempt in range(1, _MAX_FALLBACK_ATTEMPTS + 1):
        model = models[min(attempt - 1, len(models) - 1)]
        llm = ChatGroq(
            model=model,
            api_key=settings.groq_api_key,
            temperature=0.4,
            # qwen3.6-27b needs a far larger budget than the gpt-oss models — it reasons heavily
            # with no reasoning_effort control and 400s outright when truncated. See
            # agents/email_drafter/agent.py for the measurements behind 4096.
            max_tokens=4096 if "qwen" in model else 1200,
            reasoning_effort="low" if "gpt-oss" in model else None,
        )
        structured_llm = llm.with_structured_output(FollowupDraftOutput, include_raw=True, method="json_schema")
        try:
            start = time.monotonic()
            result = structured_llm.invoke(messages)
            latency_ms = int((time.monotonic() - start) * 1000)
            parsed = result["parsed"]
            # include_raw=True reports a schema-violating response as parsed=None +
            # parsing_error rather than raising, so the bare assert this replaces escaped the
            # retry loop as an uncaught AssertionError. See agents/resume_parser/agent.py.
            if not isinstance(parsed, FollowupDraftOutput):
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
            logger.warning("Follow-Up Drafter attempt %d failed on model %s: %s", attempt, model, exc)
            last_error = exc
    assert last_error is not None
    raise last_error


@entrypoint()
def _followup_drafter_graph(context: FollowupDraftContext) -> tuple[FollowupDraftOutput, AgentUsageInfo]:
    return _run_llm(context).result()


async def draft_followup(context: FollowupDraftContext) -> tuple[FollowupDraftOutput, AgentUsageInfo]:
    """Follow-Up Drafter agent (A6): a previously-sent email (full body for Platform rows,
    subject-only for External rows) + how many follow-ups have already gone out -> a subject/body
    follow-up draft, plus token usage."""
    return await _followup_drafter_graph.ainvoke(context)
