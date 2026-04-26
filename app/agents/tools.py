import json
from datetime import datetime, timedelta
from typing import Annotated

import pytz
from langchain_core.tools import InjectedToolArg, tool
from sqlalchemy import func, select

from app.agents.llm_setup import get_image_embedding
from app.config import get_settings
from app.models.models import Metric, Submission, User
from app.services.database import async_session, redis_client
from app.services.report_service import (
    get_defaulters_in_range,
    get_submissions_in_range,
)
from app.services.telegram_service import telegram_service
from app.utils import security
from app.utils.formatters import generate_text_ledger


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

        if role not in ["admin", "root"]:
            stmt = stmt.where(Submission.user_id == db_user_id)

        if role in ["admin", "root"] and target_name:
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
async def create_invite_token(*, role: Annotated[str, InjectedToolArg]) -> str:
    """Generate a single-use invite token to grant admin privileges
    to a new staff member."""
    if role != "root":
        return "Error: Only root admins can generate invite tokens."

    raw_token = security.generate_invite_token()
    prefix = raw_token.split("-")[0]

    hashed_token = await security.hash_passkey(raw_token)
    await redis_client.set(f"invite:{prefix}", hashed_token, ex=86400)

    return f"Invite generated successfully. Token: {raw_token} (Expires in 24 hours)."


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
            user.role = "root"
            await session.commit()
            return "Root admin claimed successfully."

        if "-" in token:
            prefix = token.split("-")[0]
            redis_key = f"invite:{prefix}"
            hashed_passkey = await redis_client.get(redis_key)

            if hashed_passkey:
                is_valid = await security.verify_passkey(token, hashed_passkey)
                if is_valid:
                    user.role = "admin"
                    await session.commit()
                    await redis_client.delete(redis_key)
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
async def submit_for_verification(
    full_name: str,
    *,
    telegram_id: Annotated[int, InjectedToolArg],
    username: Annotated[str | None, InjectedToolArg] = None,
) -> str:
    """Submit a user's name for root admin verification to join the private group."""
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user:
            user.full_name = full_name
            user.role = "pending"
            await session.commit()

        roots = await session.scalars(
            select(User.telegram_id).where(User.role == "root")
        )
        for root_id in roots:
            try:
                user_info = f"Full Name: {full_name}\n"
                if username:
                    user_info += f"Telegram Username: @{username}\n"
                user_info += f"ID: {telegram_id}"

                await telegram_service.send_message(
                    root_id,
                    f"🔔 Verification Request:\n{user_info}\n\n"
                    f"Reply with: 'Approve {telegram_id}' or 'Reject {telegram_id}'",
                )
            except Exception:
                pass
    return "Verification request sent to root admin. User status is pending."


@tool
async def resolve_verification(
    target_telegram_id: int, action: str, *, role: Annotated[str, InjectedToolArg]
) -> str:
    """Root admin tool to 'approve' or 'reject' a pending user's verification."""
    if role != "root":
        return "Error: Only root admins can resolve verifications."

    action = action.lower()
    if action not in ["approve", "reject"]:
        return "Error: Action must be 'approve' or 'reject'."

    async with async_session() as session:
        user = await session.scalar(
            select(User).where(User.telegram_id == target_telegram_id)
        )
        if not user or user.role != "pending":
            return "Error: User not found or not in pending state."

        new_role = "member" if action == "approve" else "public"
        user.role = new_role
        await session.commit()

        if action == "approve":
            msg = (
                "🎉 Your verification for Mighty Storm is approved! "
                "You can now submit assignments."
            )
        else:
            msg = (
                "ℹ️ Your membership request for Mighty Storm was not approved at "
                "this time. However, you've been onboarded as a Public User. "
                "You can still use me to track your personal ear-training "
                "progress and get analytical advice. I'm still here to help you! 🎵"
            )
        try:
            await telegram_service.send_message(target_telegram_id, msg)
        except Exception:
            pass
    return f"User {target_telegram_id} successfully resolved as {new_role}."


@tool
async def onboard_public_user(*, telegram_id: Annotated[int, InjectedToolArg]) -> str:
    """Instantly onboard a user as a public member (no admin verification needed)."""
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user:
            user.role = "public"
            await session.commit()
    return "User instantly onboarded as public."
