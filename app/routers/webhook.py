import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from langchain_core.messages import HumanMessage

from app.agents.graph import execute_graph
from app.agents.llm_setup import get_text_embedding
from app.config import get_settings
from app.schemas.telegram_schemas import TelegramUpdate
from app.services import cognitive_service, conversation_service, profile_service
from app.services.database import async_session as async_session_maker
from app.services.database import redis_client
from app.services.telegram_service import telegram_service
from app.state.state import AgentState
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
    update: TelegramUpdate,
    background_tasks: BackgroundTasks,
) -> dict:
    if not update.message:
        return {"status": "ok"}

    chat_id = update.message.chat.id
    telegram_id = update.message.from_.id
    username = update.message.from_.username

    if not await check_rate_limit(chat_id):
        return {"status": "rate_limited"}

    user_text = update.message.text or update.message.caption or "Uploaded an image."

    image_base64 = None
    if update.message.photo:
        photo = update.message.photo[-1]
        try:
            file_path = await telegram_service.get_file_path(photo.file_id)
            image_base64 = await telegram_service.download_image_as_base64(file_path)
        except Exception:
            logger.exception("Image download failed for chat_id=%d", chat_id)
            return {"status": "ok"}

    async with async_session_maker() as session:
        profile = await profile_service.get_or_create_profile(
            session, telegram_id, username
        )
        db_user_id = profile["user_id"]
        role = profile["role"]
        is_onboarded = profile["is_onboarded"]
        full_name = profile["full_name"]

    history = await conversation_service.get_history(
        telegram_id, async_session_maker, redis_client
    )
    summary = await cognitive_service.get_summary(telegram_id, redis_client)

    facts = []
    if len(user_text.split()) >= 4:
        query_emb = await get_text_embedding(user_text)
        async with async_session_maker() as session:
            facts = await cognitive_service.retrieve_relevant_facts(
                session, db_user_id, query_emb
            )

    msg_content = [{"type": "text", "text": user_text}]
    if image_base64:
        msg_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
            }
        )
    human_msg = HumanMessage(content=msg_content)
    history.append(human_msg)

    agent_state: AgentState = {
        "messages": history,
        "chat_id": chat_id,
        "user_id": telegram_id,
        "username": username,
        "role": role,
        "db_user_id": str(db_user_id),
        "image_base64": image_base64,
        "extracted_metrics": None,
        "image_vector": None,
        "full_name": full_name,
        "is_onboarded": is_onboarded,
        "conversation_summary": summary,
        "relevant_facts": facts,
        "task_status": "pending",
        "retry_count": 0,
        "critique": None,
    }

    background_tasks.add_task(
        execute_graph,
        state=agent_state,
        session_id=str(telegram_id),
        raw_user_text=user_text,
    )

    return {"status": "ok"}
