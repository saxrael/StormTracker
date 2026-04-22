from fastapi import FastAPI

from app.config import get_settings
from app.routers import webhook

settings = get_settings()

app = FastAPI(
    title="StormTracker",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

app.include_router(webhook.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
