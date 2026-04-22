from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Metric, Submission


async def check_visual_duplicate(
    session: AsyncSession,
    user_submission_ids: list[UUID],
    new_vector: list[float],
) -> float:
    if not user_submission_ids:
        return 0.0

    similarity_expr = 1 - Metric.image_vector.cosine_distance(new_vector)

    stmt = (
        select(func.max(similarity_expr))
        .where(Metric.submission_id.in_(user_submission_ids))
        .where(Metric.image_vector.isnot(None))
    )

    result = await session.execute(stmt)
    max_similarity = result.scalar_one_or_none()

    return float(max_similarity) if max_similarity is not None else 0.0


async def check_metadata_duplicate(
    session: AsyncSession,
    user_submission_ids: list[UUID],
    new_metadata: str,
) -> bool:
    if not user_submission_ids:
        return False

    cutoff = datetime.now(UTC) - timedelta(hours=24)

    stmt = (
        select(Metric.id)
        .join(Metric.submission)
        .where(Metric.submission_id.in_(user_submission_ids))
        .where(Metric.device_metadata == new_metadata)
        .where(Submission.created_at >= cutoff)
        .limit(1)
    )

    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
