import logging
import os
from datetime import datetime

import pytz
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.config import get_settings
from app.services.database import async_session
from app.services.pdf_service import generate_pdf_report
from app.services.report_service import (
    get_admin_ids,
    get_daily_submissions,
    get_defaulters,
)
from app.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)

router = APIRouter()

LAGOS_TZ = pytz.timezone("Africa/Lagos")


def _verify_cron_secret(x_cron_secret: str) -> None:
    settings = get_settings()
    if x_cron_secret != settings.CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _nudge_defaulters(message: str) -> None:
    target_date = datetime.now(LAGOS_TZ).date()

    async with async_session() as session:
        defaulters = await get_defaulters(session, target_date)

    for user in defaulters:
        try:
            await telegram_service.send_message(user["telegram_id"], message)
        except Exception:
            logger.exception("Failed to nudge user %s", user["telegram_id"])


async def _broadcast_midnight_report() -> None:
    target_date = datetime.now(LAGOS_TZ).date()

    async with async_session() as session:
        submissions = await get_daily_submissions(session, target_date)
        defaulters = await get_defaulters(session, target_date)
        admin_ids = await get_admin_ids(session)

    pdf_path = generate_pdf_report(submissions, defaulters, target_date)

    for admin_id in admin_ids:
        try:
            await telegram_service.send_document(
                admin_id, pdf_path, caption="📊 StormTracker Daily Analytics"
            )
        except Exception:
            logger.exception("Failed to send report to admin %s", admin_id)

    os.remove(pdf_path)


@router.post("/cron/nudge-morning")
async def nudge_morning(
    background_tasks: BackgroundTasks,
    x_cron_secret: str = Header(...),
) -> dict:
    _verify_cron_secret(x_cron_secret)
    background_tasks.add_task(
        _nudge_defaulters,
        "☀️ Good morning! Friendly reminder to submit your "
        "ear-training assignment for today.",
    )
    return {"status": "ok"}


@router.post("/cron/nudge-evening")
async def nudge_evening(
    background_tasks: BackgroundTasks,
    x_cron_secret: str = Header(...),
) -> dict:
    _verify_cron_secret(x_cron_secret)
    background_tasks.add_task(
        _nudge_defaulters,
        "🌙 Evening reminder! You haven't submitted today's "
        "ear-training yet. Please submit before midnight!",
    )
    return {"status": "ok"}


@router.post("/cron/midnight-report")
async def midnight_report(
    background_tasks: BackgroundTasks,
    x_cron_secret: str = Header(...),
) -> dict:
    _verify_cron_secret(x_cron_secret)
    background_tasks.add_task(_broadcast_midnight_report)
    return {"status": "ok"}
