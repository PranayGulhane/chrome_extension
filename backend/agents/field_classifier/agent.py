import logging
import time

from groq import APIStatusError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.func import entrypoint, task

from agent_usage.schemas import AgentUsageInfo
from core.config import get_settings

from .schemas import FieldClassifierContext, FieldClassifierOutput

logger = logging.getLogger(__name__)

_MAX_FALLBACK_ATTEMPTS = 4

_SYSTEM_PROMPT = """You are classifying fields on a job-application form for an autofill tool. \
Each field below is identified by an index and comes with its visible text (label, and/or the \
input's name/id/placeholder attributes if no visible label exists), its input type, and — for \
selects/radio groups — its option labels.

For each field, decide which single key from this fixed list it is asking the candidate to fill \
in, or that none of them apply:

first_name, last_name, full_name, email, phone_number, current_city, state_province, country, \
linkedin_url, github_url, portfolio_website, personal_website, work_authorization, \
willing_to_relocate, nationality, current_employer, current_job_title

Only choose a key when you're reasonably confident. Job-application forms often contain fields \
that look similar to a candidate field but mean something else — e.g. "Company" on a referral \
question can mean a *third party's* employer, not the candidate's; "Location"/"City" can mean the \
job's location, not the candidate's; "How did you hear about us" is not current_employer. When \
genuinely ambiguous, or the field is clearly asking for something outside this list entirely \
(salary expectations, EEO/demographic questions, essay/open-ended questions, dates unrelated to \
identity, resume/file uploads), return a null key for that field rather than guessing.

Never invent a key outside the given list. Return exactly one result per field index given, even \
if the key is null."""


@task
def _run_llm(context: FieldClassifierContext) -> tuple[FieldClassifierOutput, AgentUsageInfo]:
    settings = get_settings()
    lines = [
        f'{f.index}. text="{f.text}" type={f.field_type}'
        + (f' options={f.options}' if f.options else "")
        for f in context.fields
    ]
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content="\n".join(lines)),
    ]

    # method="json_schema" (not the default "function_calling") — same reasoning as
    # agents/email_drafter and agents/resume_parser: this schema's `key` field is a strict Literal
    # enum, and json_schema mode is what actually enforces that enum at the API level rather than
    # relying on the model's tool-call arguments to happen to stay in range. Only
    # openai/gpt-oss-20b/120b are confirmed *strict* json_schema (see docs/PROGRESS.md's "Groq
    # multi-model fallback" log) — the fallback models below are best-effort.
    # Catches groq.APIStatusError (base class of BadRequestError/RateLimitError/NotFoundError/...)
    # so a decommissioned model id, which returns 404, advances to the next model instead of
    # escaping the loop — see agents/email_drafter/agent.py for the incident this came from.
    # max_tokens is the largest of any agent here bar the resume parser because output length grows
    # with the number of unmatched form fields in the batch, and gpt-oss's reasoning tokens come
    # out of this same budget before the JSON begins.
    last_error: APIStatusError | OutputParserException | None = None
    models = settings.groq_field_classifier_models
    for attempt in range(1, _MAX_FALLBACK_ATTEMPTS + 1):
        model = models[min(attempt - 1, len(models) - 1)]
        llm = ChatGroq(
            model=model,
            api_key=settings.groq_api_key,
            temperature=0,
            # qwen3.6-27b needs a far larger budget than the gpt-oss models — it reasons heavily
            # with no reasoning_effort control and 400s outright when truncated. See
            # agents/email_drafter/agent.py for the measurements behind 4096.
            max_tokens=4096 if "qwen" in model else 2048,
            reasoning_effort="low" if "gpt-oss" in model else None,
        )
        structured_llm = llm.with_structured_output(FieldClassifierOutput, include_raw=True, method="json_schema")
        try:
            start = time.monotonic()
            result = structured_llm.invoke(messages)
            latency_ms = int((time.monotonic() - start) * 1000)
            parsed = result["parsed"]
            # include_raw=True reports a schema-violating response as parsed=None +
            # parsing_error rather than raising, so the bare assert this replaces escaped the
            # retry loop as an uncaught AssertionError. See agents/resume_parser/agent.py.
            if not isinstance(parsed, FieldClassifierOutput):
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
            logger.warning("Field Classifier attempt %d failed on model %s: %s", attempt, model, exc)
            last_error = exc
    assert last_error is not None
    raise last_error


@entrypoint()
def _field_classifier_graph(context: FieldClassifierContext) -> tuple[FieldClassifierOutput, AgentUsageInfo]:
    return _run_llm(context).result()


async def classify_fields(context: FieldClassifierContext) -> tuple[FieldClassifierOutput, AgentUsageInfo]:
    """Field Classifier agent: a batch of form-autofill's heuristically-unmatched fields -> a
    best-effort key (or null) per field, plus token usage. Step 1's LLM-fallback slice described in
    docs/FORM_AUTOFILL_EXTENSION.md §2.2 step 3 — only ever called for what autocomplete-attribute
    and label-synonym matching in content/formFiller.ts already left unresolved, and never for
    fields the heuristics deliberately leave alone (subjective/essay questions — that's Step 2).
    Callers should skip calling this at all for an empty field list rather than relying on it to
    short-circuit, since there's no real model invocation (and thus no usage) to log in that case."""
    return await _field_classifier_graph.ainvoke(context)
