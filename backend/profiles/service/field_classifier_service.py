import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from agent_usage.models import AgentUsageLog
from agents.field_classifier.agent import classify_fields as run_classifier
from agents.field_classifier.schemas import FieldClassifierContext, UnmatchedField
from profiles.schemas import ClassifyFieldsField, ClassifyFieldsMatch

logger = logging.getLogger(__name__)


class FieldClassificationError(Exception):
    pass


async def classify_fields(
    db: AsyncSession, user_id: uuid.UUID, fields: list[ClassifyFieldsField]
) -> list[ClassifyFieldsMatch]:
    if not fields:
        return []

    context = FieldClassifierContext(
        fields=[UnmatchedField(index=f.index, text=f.text, field_type=f.field_type, options=f.options) for f in fields]
    )
    try:
        output, usage = await run_classifier(context)
    except Exception as exc:
        logger.exception("Field Classifier agent failed for user %s (%d fields)", user_id, len(fields))
        raise FieldClassificationError("Field Classifier agent failed to classify these fields.") from exc

    db.add(
        AgentUsageLog(
            user_id=user_id,
            agent_name="field_classifier",
            model_used=usage.model_used,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=usage.latency_ms,
        )
    )
    await db.commit()

    return [ClassifyFieldsMatch(index=m.index, key=m.key) for m in output.matches]
