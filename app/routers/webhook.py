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
    if not update.message and not update.callback_query:
        return {"status": "ignored"}

    is_callback = update.callback_query is not None
    chat_id = (
        update.callback_query.message.chat.id if is_callback else update.message.chat.id
    )
    telegram_id = (
        update.callback_query.from_.id if is_callback else update.message.from_.id
    )
    username = (
        update.callback_query.from_.username
        if is_callback
        else update.message.from_.username
    )
    message_id = (
        update.callback_query.message.message_id
        if is_callback
        else update.message.message_id
    )

    async with async_session_maker() as session:
        profile = await profile_service.get_or_create_profile(
            session, telegram_id, username
        )
        db_user_id = profile["user_id"]
        role = profile["role"]
        is_onboarded = profile["is_onboarded"]
        full_name = profile["full_name"]
        has_consented = profile.get("has_consented", False)

    if not has_consented:
        if is_callback:
            query_id = update.callback_query.id
            data = update.callback_query.data

            if data == "consent_agree":
                async with async_session_maker() as session:
                    await profile_service.update_consent(session, telegram_id, True)

                await telegram_service.answer_callback_query(query_id)
                await telegram_service.edit_message_text(
                    chat_id,
                    message_id,
                    "**Thank you!** You have accepted the Privacy Policy and "
                    "Terms of Use.\n\nWelcome to StormTracker! Say 'Hello' to "
                    "begin your onboarding.",
                )
                return {"status": "consented"}

            elif data == "consent_disagree":
                await telegram_service.answer_callback_query(query_id)
                await telegram_service.edit_message_text(
                    chat_id,
                    message_id,
                    "**Access Denied.**\n\nYou must agree to the Privacy Policy "
                    "and Terms of Use to use this system. If you change your mind, "
                    "send any message to review the terms again.",
                )
                return {"status": "denied"}

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "📄 Privacy Policy",
                        "url": f"https://{get_settings().DOMAIN_NAME}/legal/Privacy_Policy.pdf",
                    },
                    {
                        "text": "📄 Terms of Use",
                        "url": f"https://{get_settings().DOMAIN_NAME}/legal/Terms_of_Use.pdf",
                    },
                ],
                [
                    {"text": "I Agree", "callback_data": "consent_agree"},
                    {"text": "I Disagree", "callback_data": "consent_disagree"},
                ],
            ]
        }

        contract_text = (
            "⚖️ **Legal Agreement Required**\n\n"
            "To use StormTracker, we must process your personal data (name, "
            "Telegram ID, and submitted screenshots) "
            "to track your performance and generate group analytics.\n\n"
            "Please review our complete Privacy Policy and Terms of Use below. "
            "You must explicitly agree to these terms to continue."
        )

        background_tasks.add_task(
            telegram_service.send_message, chat_id, contract_text, keyboard
        )
        return {"status": "awaiting_consent"}

    if is_callback:
        await telegram_service.answer_callback_query(update.callback_query.id)
        return {"status": "ignored_callback"}

    message = update.message
    if not await check_rate_limit(chat_id, role):
        await telegram_service.send_message(
            chat_id=chat_id,
            text=(
                "You have exceeded the allowed number of requests. "
                "Please wait a moment before trying again."
            ),
        )
        return {"status": "rate_limited"}

    user_text = message.text or message.caption or "Uploaded an image."

    image_base64 = None
    file_id = None
    file_size = 0
    rejection_reason = None

    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_size = photo.file_size or 0
    elif message.document:
        doc = message.document
        if doc.mime_type and doc.mime_type.startswith("image/"):
            file_id = doc.file_id
            file_size = doc.file_size or 0
        else:
            rejection_reason = "non_image"

    if file_id and file_size > 5_242_880:
        file_id = None
        rejection_reason = "too_large"

    if rejection_reason == "non_image":
        user_text += (
            "\n\n[SYSTEM ALERT: The user uploaded a non-image document. "
            "Explicitly inform them that you can only process "
            "ear-training screenshots.]"
        )
    elif rejection_reason == "too_large":
        user_text += (
            "\n\n[SYSTEM ALERT: The user uploaded an image exceeding the "
            "5MB limit. Explicitly ask them to compress it or send it "
            "as a standard Telegram Photo.]"
        )
    elif file_id:
        try:
            file_path = await telegram_service.get_file_path(file_id)
            image_base64 = await telegram_service.download_image_as_base64(file_path)
        except Exception:
            logger.exception("Image download failed for chat_id=%d", chat_id)
            user_text += (
                "\n\n[SYSTEM ALERT: Failed to download the image "
                "from Telegram servers. Explicitly inform them to try "
                "sending it again or compressing it.]"
            )

    history = await conversation_service.get_history(
        telegram_id, async_session_maker, redis_client
    )
    summary = profile.get("conversation_summary")

    facts = []
    filler_words = {
        "ok",
        "yes",
        "no",
        "thanks",
        "thank you",
        "hello",
        "hi",
        "hey",
        "cool",
        "done",
    }
    if user_text and user_text.strip().lower() not in filler_words:
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
