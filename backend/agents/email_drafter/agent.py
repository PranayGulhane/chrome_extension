import logging
import time

from groq import BadRequestError, RateLimitError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.func import entrypoint, task

from agent_usage.schemas import AgentUsageInfo
from core.config import get_settings

from .schemas import EmailDraftContext, EmailDraftOutput

logger = logging.getLogger(__name__)

_MAX_FALLBACK_ATTEMPTS = 4

_SYSTEM_PROMPT = """You are an expert cold-outreach email writer helping a job seeker contact the \
person who posted a hiring announcement on LinkedIn.

Write a short, professional, personalized cold email from the candidate to the poster. Ground it \
only in the details you're given below (the parsed job post and the candidate's profile/resume) — \
never invent companies, titles, skills, or achievements that aren't present in that context. If a \
detail (job title, company, etc.) is unknown, write around it naturally rather than guessing.

Guidelines:
- Address the poster by name if given.
- Reference the specific role/company from the post.
- Mention 2-3 concrete skills, experiences, or projects from the candidate's profile that are \
genuinely relevant to this role — pick the most relevant ones, don't list everything.
- Keep the body to roughly 150-200 words. Professional but warm tone, not overly formal or stiff.
- End with a clear, low-friction call to action (e.g. offering a quick call, or asking to be \
considered for the role) and a signature using the candidate's name from their profile context.
- The subject line should be short and specific to the role (not generic like "Job Application").
"""

# Feature 7: linkedin_dm outreach — the poster said "DM me" rather than sharing an email, so this
# produces a short message meant to be copy-pasted straight into a LinkedIn DM box, not an email.
# subject still goes through EmailDraftOutput unchanged (avoids a second schema for one unused
# field) but is never shown to the user for this mode — the frontend only surfaces the body.
_DM_SYSTEM_PROMPT = """You are helping a job seeker write a short LinkedIn direct message to the \
person who posted a hiring announcement, after they said to "DM me" rather than sharing an email.

Write a brief, casual-but-professional LinkedIn DM from the candidate to the poster. Ground it \
only in the details you're given below (the parsed job post and the candidate's profile/resume) — \
never invent companies, titles, skills, or achievements that aren't present in that context. If a \
detail (job title, company, etc.) is unknown, write around it naturally rather than guessing.

Guidelines:
- Address the poster by name if given.
- Reference the specific role/company from the post.
- Mention 1-2 concrete skills or experiences from the candidate's profile that are genuinely \
relevant — a DM is not the place for a full pitch.
- Keep the body to roughly 80-120 words, conversational tone (like a real LinkedIn message, not a \
formal email) — no letter-style salutation/signature block, just a natural opening and closing.
- End with a clear, low-friction ask (e.g. "would love to chat if you're open to it").
- For the "subject" field, just repeat the job title or a short internal label — it will not be \
shown to anyone, it exists only because of a shared output format with email drafts.
"""


@task
def _run_llm(context: EmailDraftContext) -> tuple[EmailDraftOutput, AgentUsageInfo]:
    settings = get_settings()
    details = [
        f"Poster's name: {context.poster_name}",
        f"Job title: {context.job_title or 'unknown'}",
        f"Company: {context.company or 'unknown'}",
        f"Seniority: {context.seniority or 'unknown'}",
        f"Location: {context.location or 'unknown'}",
        f"Required/preferred skills mentioned in the post: "
        f"{', '.join(context.skills) if context.skills else 'none listed'}",
        f"Original post excerpt:\n{context.post_snippet}",
        f"\nCandidate profile:\n{context.profile_context}",
    ]
    if context.resume_context:
        details.append(f"\nCandidate resume excerpt:\n{context.resume_context}")
    system_prompt = _DM_SYSTEM_PROMPT if context.is_dm else _SYSTEM_PROMPT
    messages = [SystemMessage(content=system_prompt), HumanMessage(content="\n".join(details))]
    max_tokens = 400 if context.is_dm else 1024

    # method="json_schema" for every fallback model, not the default "function_calling" — see
    # agents/resume_parser/agent.py for the root-caused reason (a Groq structured-output model can
    # hallucinate a wrong tool name under function_calling; json_schema mode sidesteps tool-name
    # selection entirely). Confirmed compatible with include_raw=True (usage_metadata still
    # populates correctly). Only openai/gpt-oss-20b/120b are confirmed *strict* json_schema — the
    # 3rd/4th fallback models in settings.groq_email_drafter_models are best-effort only, a known
    # accepted risk (see docs/PROGRESS.md's "Groq multi-model fallback" log).
    #
    # Multi-model fallback: each attempt uses a different model (index 0 = today's original single
    # default) rather than a blind retry of the same model — this is what actually works around a
    # per-model daily quota exhaustion (Groq's rate limits are per model).
    last_error: BadRequestError | RateLimitError | OutputParserException | None = None
    models = settings.groq_email_drafter_models
    for attempt in range(1, _MAX_FALLBACK_ATTEMPTS + 1):
        model = models[min(attempt - 1, len(models) - 1)]
        llm = ChatGroq(model=model, api_key=settings.groq_api_key, temperature=0.4, max_tokens=max_tokens)
        structured_llm = llm.with_structured_output(EmailDraftOutput, include_raw=True, method="json_schema")
        try:
            start = time.monotonic()
            result = structured_llm.invoke(messages)
            latency_ms = int((time.monotonic() - start) * 1000)
            parsed = result["parsed"]
            assert isinstance(parsed, EmailDraftOutput)
            raw = result["raw"]
            usage = raw.usage_metadata or {}
            usage_info = AgentUsageInfo(
                model_used=model,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                latency_ms=latency_ms,
            )
            return parsed, usage_info
        except (BadRequestError, RateLimitError, OutputParserException) as exc:
            logger.warning("Email Drafter attempt %d failed on model %s: %s", attempt, model, exc)
            last_error = exc
    assert last_error is not None
    raise last_error


@entrypoint()
def _email_drafter_graph(context: EmailDraftContext) -> tuple[EmailDraftOutput, AgentUsageInfo]:
    return _run_llm(context).result()


async def draft_email(context: EmailDraftContext) -> tuple[EmailDraftOutput, AgentUsageInfo]:
    """Email Drafter agent (A2): parsed JD + profile/resume context -> a subject/body draft."""
    return await _email_drafter_graph.ainvoke(context)
