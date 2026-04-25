import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services import conversation_service
from app.services.database import async_session, redis_client
from app.services.pdf_service import generate_pdf_report
from app.services.report_service import (
    get_admin_ids,
    get_daily_submissions,
    get_defaulters,
)
from app.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)

LAGOS_TZ = pytz.timezone("Africa/Lagos")

MORNING_NUDGE_TEXT = (
    "☀️ Good morning! Friendly reminder to submit your "
    "ear-training assignment for today."
)
EVENING_NUDGE_TEXT = (
    "🌙 Evening reminder! You haven't submitted today's "
    "ear-training yet. Please submit before midnight!"
)


async def run_with_lock(task_name: str, task_coro):
    lock = await redis_client.set(f"cron_lock:{task_name}", "locked", nx=True, ex=60)
    if lock:
        try:
            await task_coro()
        finally:
            await redis_client.delete(f"cron_lock:{task_name}")
    else:
        logger.info("Skipping %s — another instance holds the lock", task_name)


async def _task_morning_nudge():
    target_date = datetime.now(LAGOS_TZ).date()
    async with async_session() as session:
        defaulters = await get_defaulters(session, target_date)
    for user in defaulters:
        try:
            await telegram_service.send_message(
                user["telegram_id"],
                MORNING_NUDGE_TEXT,
            )
            await conversation_service.persist_turn(
                telegram_id=user["telegram_id"],
                user_text=None,
                ai_text=MORNING_NUDGE_TEXT,
                session_factory=async_session,
                redis_client=redis_client,
            )
        except Exception:
            logger.exception("Failed to nudge user %s", user["telegram_id"])


async def _task_evening_nudge():
    target_date = datetime.now(LAGOS_TZ).date()
    async with async_session() as session:
        defaulters = await get_defaulters(session, target_date)
    for user in defaulters:
        try:
            await telegram_service.send_message(
                user["telegram_id"],
                EVENING_NUDGE_TEXT,
            )
            await conversation_service.persist_turn(
                telegram_id=user["telegram_id"],
                user_text=None,
                ai_text=EVENING_NUDGE_TEXT,
                session_factory=async_session,
                redis_client=redis_client,
            )
        except Exception:
            logger.exception("Failed to nudge user %s", user["telegram_id"])


async def _task_midnight_report():
    target_date = datetime.now(LAGOS_TZ).date()
    async with async_session() as session:
        submissions = await get_daily_submissions(session, target_date)
        defaulters = await get_defaulters(session, target_date)
        admin_ids = await get_admin_ids(session)

    pdf_path = await asyncio.to_thread(
        generate_pdf_report, submissions, defaulters, target_date
    )

    for admin_id in admin_ids:
        try:
            await telegram_service.send_document(
                admin_id, pdf_path, caption="📊 StormTracker Daily Analytics"
            )
        except Exception:
            logger.exception("Failed to send report to admin %s", admin_id)

    with suppress(OSError):
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)


def start_scheduler():
    scheduler = AsyncIOScheduler(timezone=LAGOS_TZ)

    scheduler.add_job(
        run_with_lock,
        trigger="cron",
        hour=9,
        minute=0,
        args=["morning", _task_morning_nudge],
        id="morning_nudge",
    )
    scheduler.add_job(
        run_with_lock,
        trigger="cron",
        hour=20,
        minute=0,
        args=["evening", _task_evening_nudge],
        id="evening_nudge",
    )
    scheduler.add_job(
        run_with_lock,
        trigger="cron",
        hour=23,
        minute=59,
        args=["midnight", _task_midnight_report],
        id="midnight_report",
    )

    scheduler.start()
    logger.info("APScheduler started with 3 cron jobs (Africa/Lagos)")
