import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from langchain_core.messages import HumanMessage

from app.agents.graph import execute_graph
from app.config import get_settings
from app.schemas.telegram_schemas import TelegramUpdate
from app.services.memory_service import check_rate_limit
from app.services.telegram_service import telegram_service
from app.state.state import AgentState

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
    update: TelegramUpdate,
    background_tasks: BackgroundTasks,
) -> dict:
    if not update.message:
        return {"status": "ok"}

    chat_id = update.message.chat.id
    user_id = update.message.from_.id
    username = update.message.from_.username

    if not await check_rate_limit(chat_id):
        return {"status": "rate_limited"}

    image_base64 = None
    text_content = update.message.text or ""

    if update.message.photo:
        photo = update.message.photo[-1]
        try:
            file_path = await telegram_service.get_file_path(photo.file_id)
            image_base64 = await telegram_service.download_image_as_base64(file_path)
        except Exception:
            logger.exception("Image download failed for chat_id=%d", chat_id)
            return {"status": "ok"}

    messages = []
    if text_content:
        messages.append(HumanMessage(content=text_content))
    elif image_base64:
        messages.append(HumanMessage(content="[Image submitted for grading]"))

    if not messages:
        return {"status": "ok"}

    agent_state: AgentState = {
        "messages": messages,
        "chat_id": chat_id,
        "user_id": user_id,
        "username": username,
        "role": "member",
        "image_base64": image_base64,
        "extracted_metrics": None,
        "image_vector": None,
        "task_status": "pending",
        "retry_count": 0,
        "critique": None,
    }

    background_tasks.add_task(
        execute_graph, state=agent_state, session_id=str(chat_id)
    )

    return {"status": "ok"}
