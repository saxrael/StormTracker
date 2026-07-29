from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Metric, Submission


async def check_visual_duplicate(
    session: AsyncSession,
    db_user_id: str,
    new_vector: list[float],
) -> float:
    similarity_expr = 1 - Metric.image_vector.cosine_distance(new_vector)

    stmt = select(func.max(similarity_expr)).where(Metric.image_vector.isnot(None))

    result = await session.execute(stmt)
    max_similarity = result.scalar_one_or_none()

    return float(max_similarity) if max_similarity is not None else 0.0


async def check_metadata_duplicate(
    session: AsyncSession,
    db_user_id: str,
    new_metadata: str,
) -> bool:
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    stmt = (
        select(Metric.id)
        .join(Metric.submission)
        .where(Metric.device_metadata == new_metadata)
        .where(Submission.created_at >= cutoff)
        .limit(1)
    )

    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
