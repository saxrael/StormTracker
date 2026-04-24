import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.config import get_settings
from app.routers import cron, webhook
from app.scheduler import start_scheduler
from app.services.database import engine

logger = logging.getLogger(__name__)


async def _register_telegram_webhook(client: httpx.AsyncClient) -> None:
    """Register the Telegram webhook on startup so Telegram knows
    where to deliver updates. This runs once every time the app boots."""
    settings = get_settings()
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
    payload = {
        "url": settings.WEBHOOK_URL,
        "secret_token": settings.TELEGRAM_SECRET_TOKEN,
        "allowed_updates": ["message"],
    }
    try:
        response = await client.post(url, json=payload)
        data = response.json()
        if data.get("ok"):
            logger.info("Telegram webhook registered: %s", settings.WEBHOOK_URL)
        else:
            logger.error("Telegram webhook registration failed: %s", data)
    except Exception:
        logger.exception("Could not reach Telegram API to set webhook")


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.http_client = httpx.AsyncClient(timeout=30.0)
    await _register_telegram_webhook(application.state.http_client)
    start_scheduler()
    logger.info("Application startup complete")
    yield
    await application.state.http_client.aclose()
    await engine.dispose()
    logger.info("Application shutdown complete")


_settings = get_settings()

app = FastAPI(
    title="StormTracker",
    version="0.1.0",
    docs_url="/docs" if _settings.DEBUG else None,
    redoc_url="/redoc" if _settings.DEBUG else None,
    lifespan=lifespan,
)

app.include_router(webhook.router, prefix="/api/v1")
app.include_router(cron.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
