import asyncio
import json
import logging

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select

from app.models.models import ChatMessage, User
from app.services.cognitive_service import process_cognitive_memory

logger = logging.getLogger(__name__)

HISTORY_KEY_TEMPLATE = "chat:history:{}"
HISTORY_TTL = 172800
MAX_HISTORY_LENGTH = 20
DB_FALLBACK_LIMIT = 20


async def get_history(telegram_id: int, session_factory, redis_client) -> list:
    key = HISTORY_KEY_TEMPLATE.format(telegram_id)

    cached = await redis_client.lrange(key, 0, -1)
    if cached:
        messages = []
        for raw in cached:
            entry = json.loads(raw)
            if entry["role"] == "human":
                messages.append(HumanMessage(content=entry["content"]))
            else:
                messages.append(AIMessage(content=entry["content"]))
        return messages

    async with session_factory() as session:
        result = await session.execute(
            select(User.id).where(User.telegram_id == telegram_id)
        )
        user_id = result.scalar_one_or_none()
        if user_id is None:
            return []

        rows = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(DB_FALLBACK_LIMIT)
        )
        db_messages = rows.scalars().all()

    if not db_messages:
        return []

    lc_messages = []
    pipe = redis_client.pipeline(transaction=False)
    for msg in db_messages:
        entry = json.dumps({"role": msg.role, "content": msg.content})
        pipe.rpush(key, entry)
        if msg.role == "human":
            lc_messages.append(HumanMessage(content=msg.content))
        else:
            lc_messages.append(AIMessage(content=msg.content))
    pipe.expire(key, HISTORY_TTL)
    await pipe.execute()

    return lc_messages


async def persist_turn(
    telegram_id: int,
    user_text: str | None,
    ai_text: str,
    session_factory,
    redis_client,
) -> None:
    async with session_factory() as session:
        result = await session.execute(
            select(User.id).where(User.telegram_id == telegram_id)
        )
        user_id = result.scalar_one()

        if user_text:
            session.add(ChatMessage(user_id=user_id, role="human", content=user_text))
        session.add(ChatMessage(user_id=user_id, role="ai", content=ai_text))
        await session.commit()

    key = HISTORY_KEY_TEMPLATE.format(telegram_id)
    ai_entry = json.dumps({"role": "ai", "content": ai_text})

    if user_text:
        user_entry = json.dumps({"role": "human", "content": user_text})
        await redis_client.rpush(key, user_entry, ai_entry)
    else:
        await redis_client.rpush(key, ai_entry)
    await redis_client.expire(key, HISTORY_TTL)

    llen = await redis_client.llen(key)
    if llen > MAX_HISTORY_LENGTH:
        evict_count = llen - MAX_HISTORY_LENGTH
        evicted_raw = await redis_client.lrange(key, 0, evict_count - 1)
        await redis_client.ltrim(key, evict_count, -1)

        evicted_msgs = [json.loads(m)["content"] for m in evicted_raw]

        overflow_key = f"chat:overflow:{telegram_id}"
        await redis_client.rpush(overflow_key, *evicted_msgs)
        overflow_len = await redis_client.llen(overflow_key)

        if overflow_len >= 20:
            batch = await redis_client.lrange(overflow_key, 0, -1)
            await redis_client.delete(overflow_key)
            asyncio.create_task(
                process_cognitive_memory(
                    telegram_id, batch, session_factory, redis_client
                )
            )
