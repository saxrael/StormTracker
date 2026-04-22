import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.routers import cron, webhook
from app.services.database import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("Application startup complete")
    yield
    await application.state.http_client.aclose()
    await engine.dispose()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="StormTracker",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(webhook.router, prefix="/api/v1")
app.include_router(cron.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
