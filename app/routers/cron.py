import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.models.models import Submission, User
from app.services.database import async_session
from app.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def _generate_daily_report() -> None:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    async with async_session() as session:
        result = await session.execute(
            select(Submission)
            .where(Submission.created_at >= cutoff)
            .order_by(Submission.created_at.desc())
        )
        submissions = result.scalars().all()

        all_users_result = await session.execute(select(User))
        all_users = all_users_result.scalars().all()

    active_user_ids = {s.user_id for s in submissions}
    missing_users = [
        u for u in all_users if u.id not in active_user_ids
    ]

    lines = [
        f"📊 Daily Report — {datetime.now(UTC).strftime('%Y-%m-%d')}",
        f"Submissions (24h): {len(submissions)}",
        f"Active users: {len(active_user_ids)}",
        f"Missing users: {len(missing_users)}",
    ]

    if missing_users:
        lines.append("\nMissing:")
        for user in missing_users:
            label = user.username or str(user.telegram_id)
            lines.append(f"  • {label}")

    report_text = "\n".join(lines)

    try:
        await telegram_service.send_message(settings.ADMIN_CHAT_ID, report_text)
    except Exception:
        logger.exception("Failed to dispatch daily report")


@router.post("/cron/daily-report")
async def daily_report(
    background_tasks: BackgroundTasks,
    x_cron_secret: str = Header(...),
) -> dict:
    settings = get_settings()
    if x_cron_secret != settings.CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    background_tasks.add_task(_generate_daily_report)
    return {"status": "report_initiated"}
