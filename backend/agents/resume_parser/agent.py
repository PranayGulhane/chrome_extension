from groq import BadRequestError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.func import entrypoint, task

from core.config import get_settings

from .schemas import ResumeParserLLMOutput, ResumeParserOutput, normalize_llm_output

_MAX_TOOL_CALL_ATTEMPTS = 3

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
def _run_llm(resume_text: str) -> ResumeParserLLMOutput:
    settings = get_settings()
    llm = ChatGroq(model=settings.groq_parsing_model, api_key=settings.groq_api_key, temperature=0)
    structured_llm = llm.with_structured_output(ResumeParserLLMOutput)
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=resume_text)]

    # openai/gpt-oss-20b on Groq occasionally answers with plain JSON in prose instead of an
    # actual tool call even with tool_choice forced ("Tool choice is required, but model did not
    # call a tool") — observed ~1 in 3 calls in testing. It's a transient generation quirk, not a
    # schema problem, so a bounded retry (not a fallback to a different parsing path) is enough.
    last_error: BadRequestError | None = None
    for attempt in range(1, _MAX_TOOL_CALL_ATTEMPTS + 1):
        try:
            result = structured_llm.invoke(messages)
            assert isinstance(result, ResumeParserLLMOutput)
            return result
        except BadRequestError as exc:
            last_error = exc
            if "did not call a tool" not in str(exc):
                raise
    assert last_error is not None
    raise last_error


@entrypoint()
def _resume_parser_graph(resume_text: str) -> ResumeParserOutput:
    return normalize_llm_output(_run_llm(resume_text).result())


async def parse_resume(resume_text: str) -> ResumeParserOutput:
    """Resume Parser agent (A3): raw resume text -> partial UserProfile object."""
    return await _resume_parser_graph.ainvoke(resume_text)
