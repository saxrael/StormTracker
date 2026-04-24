from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Metric, Submission


async def check_visual_duplicate(
    session: AsyncSession,
    db_user_id: str,
    new_vector: list[float],
) -> float:
    sub_ids_stmt = select(Submission.id).where(Submission.user_id == db_user_id)
    sub_ids_result = await session.execute(sub_ids_stmt)
    user_submission_ids = [row[0] for row in sub_ids_result.all()]

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
    db_user_id: str,
    new_metadata: str,
) -> bool:
    sub_ids_stmt = select(Submission.id).where(Submission.user_id == db_user_id)
    sub_ids_result = await session.execute(sub_ids_stmt)
    user_submission_ids = [row[0] for row in sub_ids_result.all()]

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
