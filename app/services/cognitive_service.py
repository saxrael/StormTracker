import logging

from langfuse import observe
from sqlalchemy import select

from app.agents.llm_setup import _get_openrouter_client, get_text_embedding
from app.models.models import User, UserMemoryFact

logger = logging.getLogger(__name__)

SUMMARY_MODEL = "google/gemma-4-31b-it:free"


async def get_summary(telegram_id: int, redis_client) -> str | None:
    value = await redis_client.get(f"chat:summary:{telegram_id}")
    return value


async def retrieve_relevant_facts(
    session, db_user_id, query_embedding: list[float]
) -> list[str]:
    distance_expr = UserMemoryFact.embedding.cosine_distance(query_embedding)
    stmt = (
        select(UserMemoryFact.fact_text)
        .where(UserMemoryFact.user_id == db_user_id)
        .where(distance_expr < 0.6)
        .order_by(distance_expr)
        .limit(3)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


@observe(name="Cognitive Memory Processing")
async def process_cognitive_memory(
    telegram_id: int,
    evicted_messages: list[str],
    session_factory,
    redis_client,
) -> None:
    try:
        client = _get_openrouter_client()
        messages_block = "\n".join(evicted_messages)

        existing_summary = await redis_client.get(f"chat:summary:{telegram_id}")
        old_summary = existing_summary or "No existing summary."

        summary_response = await client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are an AI assistant. Update this summary with the "
                        "following recent messages. Keep it under 200 words. "
                        f"Old Summary: {old_summary}. "
                        f"Recent Messages: {messages_block}"
                    ),
                }
            ],
            extra_body={"reasoning": {"enabled": True}},
        )
        new_summary = summary_response.choices[0].message.content
        await redis_client.set(f"chat:summary:{telegram_id}", new_summary, ex=172800)

        facts_response = await client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract ONLY permanent, high-value facts "
                        "(e.g., name, specific music goals, locations) from "
                        f"these messages: {messages_block}. "
                        "If no permanent facts exist, output exactly 'NONE'."
                    ),
                }
            ],
            extra_body={"reasoning": {"enabled": True}},
        )
        extracted_facts = facts_response.choices[0].message.content.strip()

        if extracted_facts.upper() != "NONE":
            embedding = await get_text_embedding(extracted_facts)

            async with session_factory() as session:
                result = await session.execute(
                    select(User.id).where(User.telegram_id == telegram_id)
                )
                user_id = result.scalar_one()

                session.add(
                    UserMemoryFact(
                        user_id=user_id,
                        fact_text=extracted_facts,
                        embedding=embedding,
                    )
                )
                await session.commit()

    except Exception as e:
        logger.error("Cognitive memory processing failed for %s: %s", telegram_id, e)
        return
