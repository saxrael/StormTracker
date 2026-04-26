import logging

from langfuse import observe
from sqlalchemy import select, update
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.llm_setup import _get_openrouter_client, get_text_embedding
from app.models.models import User, UserMemoryFact

logger = logging.getLogger(__name__)

SUMMARY_MODEL = "google/gemma-4-31b-it"


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


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
async def _llm_call(client, model, messages, temperature: float):
    return await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        extra_body={"reasoning": {"enabled": True}},
    )


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

        async with session_factory() as session:
            user = await session.scalar(
                select(User).where(User.telegram_id == telegram_id)
            )
            old_summary = user.conversation_summary or "No existing summary."

        summary_response = await _llm_call(
            client,
            SUMMARY_MODEL,
            [
                {
                    "role": "system",
                    "content": (
                        "You are a background memory processor. Your job is to "
                        "update an existing conversation summary with new messages. "
                        "Keep the summary concise, chronological, and strictly "
                        "under 250 words. Focus on the current narrative and "
                        "momentum (what is happening NOW and current struggles). "
                        "Do NOT include permanent milestones or hard facts (like "
                        "dates or scores) that are better suited for long-term "
                        "memory; leave those for the fact extractor."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"<old_summary>\n{old_summary}\n</old_summary>\n\n"
                        f"<new_messages>\n{messages_block}\n</new_messages>\n\n"
                        "Generate the updated summary directly with no "
                        "introductory text."
                    ),
                },
            ],
            temperature=0.2,
        )
        new_summary = summary_response.choices[0].message.content

        async with session_factory() as session:
            await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(conversation_summary=new_summary)
            )
            await session.commit()

        facts_response = await _llm_call(
            client,
            SUMMARY_MODEL,
            [
                {
                    "role": "system",
                    "content": (
                        "You are an entity extraction engine. Extract high-value "
                        "milestones (achievements, course starts) AND qualitative "
                        "mentorship insights (learning style, tone, recurring "
                        "struggles, explicit preferences). Ignore transient chatter. "
                        "If there are NO permanent facts, output the exact word: NONE"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"<messages>\n{messages_block}\n</messages>\n\n"
                        "Generate the extracted facts as a simple bulleted list."
                    ),
                },
            ],
            temperature=0.1,
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
