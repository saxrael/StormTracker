import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.config import get_settings
from app.schemas.telegram_schemas import TelegramUpdate
from app.services.database import redis_client
from app.utils.security import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_telegram_token(
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/webhook", dependencies=[Depends(verify_telegram_token)])
async def telegram_webhook(
    request: Request,
    update: TelegramUpdate,
) -> dict:
    if not update.message and not update.callback_query:
        return {"status": "ignored"}

    is_callback = update.callback_query is not None
    chat_id = (
        update.callback_query.message.chat.id if is_callback else update.message.chat.id
    )
    telegram_id = (
        update.callback_query.from_.id if is_callback else update.message.from_.id
    )

    role_bytes = await redis_client.get(f"user_role:{telegram_id}")
    role = role_bytes.decode("utf-8") if role_bytes else "new"

    if not await check_rate_limit(chat_id, role):
        return {"status": "rate_limited"}

    await request.app.state.arq_pool.enqueue_job("process_update", update.model_dump())

    return {"status": "ok"}
