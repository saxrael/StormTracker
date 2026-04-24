import json
from datetime import datetime, timedelta
from typing import Annotated

import pytz
from langchain_core.tools import InjectedToolArg, tool
from sqlalchemy import func, select

from app.agents.llm_setup import get_image_embedding
from app.config import get_settings
from app.models.models import Metric, Submission, User
from app.services import profile_service
from app.services.database import async_session, redis_client
from app.services.report_service import (
    get_defaulters_in_range,
    get_submissions_in_range,
)
from app.utils.formatters import generate_text_ledger
from app.utils.security import verify_passkey


@tool
async def query_analytics(
    timeframe_days: int,
    target_name: str = None,
    exercise_type: str = None,
    *,
    db_user_id: Annotated[str, InjectedToolArg],
    role: Annotated[str, InjectedToolArg],
) -> str:
    """Search the analytics database for historical ear-training performance
    data matching the user's natural-language query. Returns raw JSON records."""
    tz = pytz.timezone("Africa/Lagos")
    end_time = datetime.now(tz)
    start_time = (end_time - timedelta(days=timeframe_days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    async with async_session() as session:
        if target_name:
            count_stmt = select(func.count(User.id)).where(
                User.full_name.ilike(f"%{target_name}%")
            )
            result = await session.execute(count_stmt)
            count = result.scalar()
            if count == 0:
                return (
                    f"Error: No onboarded user matching the name "
                    f"'{target_name}' exists."
                )

        stmt = (
            select(
                User.full_name,
                Metric.exercise_type,
                Metric.overall_score_percentage,
                Submission.created_at,
            )
            .join(Submission, Metric.submission_id == Submission.id)
            .join(User, Submission.user_id == User.id)
            .where(Submission.created_at >= start_time)
            .where(Submission.created_at <= end_time)
        )

        if role != "admin":
            stmt = stmt.where(Submission.user_id == db_user_id)

        if role == "admin" and target_name:
            stmt = stmt.where(User.full_name.ilike(f"%{target_name}%"))

        if exercise_type:
            stmt = stmt.where(Metric.exercise_type == exercise_type)

        stmt = stmt.order_by(Submission.created_at.desc()).limit(100)

        result = await session.execute(stmt)
        rows = result.all()

    records = [
        {
            "name": row.full_name,
            "exercise": row.exercise_type,
            "score": row.overall_score_percentage,
            "date": row.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for row in rows
    ]

    if not records:
        return "User(s) exist but have no submissions in this timeframe."

    return json.dumps(records)


@tool
async def authenticate_user(
    token: str, *, db_user_id: Annotated[str, InjectedToolArg]
) -> str:
    """Validate an authentication token submitted by a user attempting to
    claim elevated privileges (e.g., root admin)."""
    settings = get_settings()

    async with async_session() as session:
        stmt = select(User).where(User.id == db_user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return "User not found in database."

        if settings.ROOT_CLAIM_TOKEN and token == settings.ROOT_CLAIM_TOKEN:
            user.role = "admin"
            await session.commit()
            return "Root admin claimed successfully."

        keys = await redis_client.keys("invite:*")
        for key in keys:
            hashed_passkey = await redis_client.get(key)
            if hashed_passkey and verify_passkey(token, hashed_passkey):
                user.role = "admin"
                await session.commit()
                await redis_client.delete(key)
                return "Admin access granted."

        return "Invalid token"


@tool
async def generate_admin_report(timeframe_days: int = 1) -> str:
    """Generate a report containing the group average score for the timeframe
    and a list of active members who have no submissions in that timeframe."""
    tz = pytz.timezone("Africa/Lagos")
    end_time = datetime.now(tz)
    start_time = (end_time - timedelta(days=timeframe_days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    async with async_session() as session:
        submissions = await get_submissions_in_range(session, start_time, end_time)
        defaulters = await get_defaulters_in_range(session, start_time, end_time)

    date_label = f"{start_time.date()} to {end_time.date()}"
    return generate_text_ledger(submissions, defaulters, date_label)


@tool
async def visual_search(*, image_base64: Annotated[str, InjectedToolArg]) -> str:
    """Perform a visual search to find the top 3 closest matching images
    in the database using pgvector cosine distance."""
    try:
        vector = await get_image_embedding(image_base64)
    except Exception as e:
        return f"Failed to generate embedding: {str(e)}"

    async with async_session() as session:
        similarity_expr = 1 - Metric.image_vector.cosine_distance(vector)
        stmt = (
            select(
                User.username,
                User.telegram_id,
                Submission.created_at,
                Metric.overall_score_percentage,
                similarity_expr.label("similarity"),
            )
            .join(Submission, Metric.submission_id == Submission.id)
            .join(User, Submission.user_id == User.id)
            .where(Metric.image_vector.isnot(None))
            .order_by(similarity_expr.desc())
            .limit(3)
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        if not rows:
            return "No matching visual records found."

        lines = []
        for row in rows:
            user_ident = row.username or str(row.telegram_id)
            date_str = row.created_at.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(
                f"User: {user_ident}, Date: {date_str}, "
                f"Score: {row.overall_score_percentage:.1f}%, "
                f"Similarity: {row.similarity:.3f}"
            )

        return "\n".join(lines)


@tool
async def update_profile(
    full_name: str,
    *,
    telegram_id: Annotated[int, InjectedToolArg],
) -> str:
    """Save a user's real full name to complete the onboarding process."""
    async with async_session() as session:
        await profile_service.update_full_name(session, telegram_id, full_name)
    return "Profile updated successfully. User is now onboarded."
