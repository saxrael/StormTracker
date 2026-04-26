import datetime

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Metric, Submission, User


async def get_daily_submissions(
    session: AsyncSession, target_date: datetime.date
) -> list[dict]:
    lagos_tz = pytz.timezone("Africa/Lagos")
    start_datetime = lagos_tz.localize(
        datetime.datetime.combine(target_date, datetime.time.min)
    )
    end_datetime = lagos_tz.localize(
        datetime.datetime.combine(target_date, datetime.time.max)
    )

    stmt = (
        select(
            User.full_name,
            User.username,
            User.telegram_id,
            Metric.exercise_type,
            Metric.overall_score_percentage,
            Metric.total_questions,
            Metric.total_correct,
            Metric.granular_details,
        )
        .join(Submission, User.id == Submission.user_id)
        .join(Metric, Submission.id == Metric.submission_id)
        .where(Submission.created_at >= start_datetime)
        .where(Submission.created_at <= end_datetime)
        .where(User.role == "member")
    )

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "full_name": row.full_name,
            "username": row.username,
            "telegram_id": row.telegram_id,
            "exercise_type": row.exercise_type,
            "overall_score_percentage": row.overall_score_percentage,
            "total_questions": row.total_questions,
            "total_correct": row.total_correct,
            "granular_details": row.granular_details,
        }
        for row in rows
    ]


async def get_defaulters(
    session: AsyncSession, target_date: datetime.date
) -> list[dict]:
    lagos_tz = pytz.timezone("Africa/Lagos")
    start_datetime = lagos_tz.localize(
        datetime.datetime.combine(target_date, datetime.time.min)
    )
    end_datetime = lagos_tz.localize(
        datetime.datetime.combine(target_date, datetime.time.max)
    )

    subq = (
        select(Submission.user_id)
        .where(Submission.created_at >= start_datetime)
        .where(Submission.created_at <= end_datetime)
    )

    stmt = (
        select(User.telegram_id, User.full_name, User.username)
        .where(User.role == "member")
        .where(User.id.notin_(subq))
    )

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "telegram_id": row.telegram_id,
            "full_name": row.full_name,
            "username": row.username,
        }
        for row in rows
    ]


async def get_submissions_in_range(
    session: AsyncSession, start_time: datetime.datetime, end_time: datetime.datetime
) -> list[dict]:
    stmt = (
        select(
            User.full_name,
            User.username,
            User.telegram_id,
            Metric.exercise_type,
            Metric.overall_score_percentage,
            Metric.total_questions,
            Metric.total_correct,
            Metric.granular_details,
        )
        .join(Submission, User.id == Submission.user_id)
        .join(Metric, Submission.id == Metric.submission_id)
        .where(Submission.created_at >= start_time)
        .where(Submission.created_at <= end_time)
        .where(User.role == "member")
    )

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "full_name": row.full_name,
            "username": row.username,
            "telegram_id": row.telegram_id,
            "exercise_type": row.exercise_type,
            "overall_score_percentage": row.overall_score_percentage,
            "total_questions": row.total_questions,
            "total_correct": row.total_correct,
            "granular_details": row.granular_details,
        }
        for row in rows
    ]


async def get_defaulters_in_range(
    session: AsyncSession, start_time: datetime.datetime, end_time: datetime.datetime
) -> list[dict]:
    subq = (
        select(Submission.user_id)
        .where(Submission.created_at >= start_time)
        .where(Submission.created_at <= end_time)
    )

    stmt = (
        select(User.telegram_id, User.full_name, User.username)
        .where(User.role == "member")
        .where(User.id.notin_(subq))
    )

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "telegram_id": row.telegram_id,
            "full_name": row.full_name,
            "username": row.username,
        }
        for row in rows
    ]


async def get_admin_ids(session: AsyncSession) -> list[int]:
    stmt = select(User.telegram_id).where(User.role.in_(["admin", "root"]))
    result = await session.execute(stmt)
    rows = result.scalars().all()

    return list(rows)
