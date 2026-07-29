import json
import logging
import re
import uuid

from langfuse import observe
from sqlalchemy import select, update
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.llm_setup import _get_openrouter_client, get_text_embedding
from app.models.models import ChatHistoryChunk, User, UserMemoryFact

logger = logging.getLogger(__name__)

SUMMARY_MODEL = "google/gemma-4-31b-it"

FACT_EXTRACTOR_PROMPT = """ROLE: Elite Cognitive Memory Extractor.

CONTEXT EXPANSION:
You are the autonomous long-term semantic memory extractor for StormTracker,
a pedagogical ear-training and music mentorship agent.
Your objective is to build a permanent knowledge graph about the user's
immutable constraints, musical goals, and demographic reality.
A 'high-value fact' includes: musical experience, instrument played, specific
interval/chord struggles, physical locations, strict academic goals,
Transient chatter (e.g., 'hello', 'thanks', 'grade this screenshot')
is strictly ignored.

INPUTS & HANDLING:
1. EXISTING MEMORY FACTS: The current array of permanent facts stored in PGVector.
2. TARGET BATCH: The conversation turns you must extract new facts from.
3. RUNNING SUMMARY: Broader conversational context. DO NOT extract facts from this;
use it ONLY to resolve dangling pronouns or context in the TARGET BATCH.

[JSON THINK-PLAN-EXECUTE PROTOCOL]
You MUST output your evaluation strictly using the designated structured JSON
schema following this cognitive sequence:
1. `think`: Analyze the TARGET BATCH against the EXISTING MEMORY FACTS.
Determine if a new immutable constraint was revealed.
2. `plan`: Define exactly what action (CREATE, UPDATE, NONE) is required
and outline the text to be stored.
3. `action`: "CREATE", "UPDATE", or "NONE".
4. `target_existing_fact_id`: The UUID of the fact to update (if UPDATE), else null.
5. `final_fact_text`: The concise text to store (if CREATE or UPDATE), else null.

RULES:
1. If a new permanent fact is revealed that does NOT conflict with or update an
existing fact, return action="CREATE" and the final_fact_text.
2. If a new fact updates, contradicts, or refines an EXISTING memory fact
listed above, return action="UPDATE", provide the exact ID in
target_existing_fact_id, and provide the updated final_fact_text.
3. If no new permanent high-value fact is revealed, return action="NONE".
4. ONLY extract facts originating directly from the TARGET BATCH text.

FEW-SHOT EXAMPLES:
---
EXISTING MEMORY FACTS:
[550e8400-e29b-41d4-a716-446655440000]: User plays the piano.
TARGET BATCH:
user: I actually decided to switch my main instrument to the guitar yesterday.
OUTPUT:
{{
  "think": "Thought Philosophy: Agency building requires permanent tracking of \\
immutable constraints. The user states they switched to guitar. This directly \\
updates the previous permanent fact that they played piano.",
  "plan": "I will UPDATE the existing fact '550e8400-e29b-41d4-a716-446655440000' \\
with the new instrument.",
  "action": "UPDATE",
  "target_existing_fact_id": "550e8400-e29b-41d4-a716-446655440000",
  "final_fact_text": "User plays the guitar."
}}
---
EXISTING MEMORY FACTS:
No existing memory facts.
TARGET BATCH:
user: I am preparing for a major conservatory audition next month.
OUTPUT:
{{
  "think": "Thought Philosophy: True education is personalized; missing crucial \\
milestone data degrades system accuracy. The user revealed an upcoming major \\
audition. This is a high-value permanent fact.",
  "plan": "Since there are no existing facts, I will CREATE a new fact.",
  "action": "CREATE",
  "target_existing_fact_id": null,
  "final_fact_text": "User is preparing for a conservatory audition next month."
}}
---
EXISTING MEMORY FACTS:
[123e4567-e89b-12d3-a456-426614174000]: User is learning minor 2nd intervals.
TARGET BATCH:
user: That sounds like a good plan, I will practice for 20 minutes today.
OUTPUT:
{{
  "think": "Thought Philosophy: The system mandate prioritizes signal-to-noise ratio; \\
capturing transient data degrades long-term retrieval. The user is simply \\
agreeing to a practice plan. No new immutable demographic or musical facts \\
were revealed.",
  "plan": "I will perform NONE action.",
  "action": "NONE",
  "target_existing_fact_id": null,
  "final_fact_text": null
}}
---

EXISTING MEMORY FACTS:
{formatted_facts}

RUNNING SUMMARY:
{current_summary}

TARGET BATCH:
{batch_text}
"""


async def retrieve_relevant_facts(
    session, db_user_id, query_embedding: list[float]
) -> list[str]:
    distance_expr = UserMemoryFact.embedding.cosine_distance(query_embedding)
    stmt = (
        select(UserMemoryFact.fact_text)
        .where(UserMemoryFact.user_id == db_user_id)
        .where(distance_expr < 0.75)
        .order_by(distance_expr)
        .limit(5)
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
    overflow_key: str,
) -> None:
    lock_key = f"cognitive_lock:{telegram_id}"
    lock = await redis_client.set(lock_key, "locked", nx=True, ex=120)
    if not lock:
        return

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

        chunk_emb = await get_text_embedding(messages_block)
        async with session_factory() as session:
            user_id_query = await session.execute(
                select(User.id).where(User.telegram_id == telegram_id)
            )
            user_id = user_id_query.scalar_one()
            session.add(
                ChatHistoryChunk(
                    user_id=user_id,
                    chunk_text=messages_block,
                    embedding=chunk_emb,
                )
            )
            await session.commit()

        async with session_factory() as session:
            user_query = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user_record = user_query.scalar_one()
            user_id = user_record.id
            current_summary = user_record.conversation_summary or "None."

            facts_query = await session.execute(
                select(UserMemoryFact).where(UserMemoryFact.user_id == user_id)
            )
            existing_facts = facts_query.scalars().all()

            if existing_facts:
                formatted_facts = "\n".join(
                    [f"[{f.id}]: {f.fact_text}" for f in existing_facts]
                )
            else:
                formatted_facts = "No existing memory facts."

        user_prompt = FACT_EXTRACTOR_PROMPT.format(
            formatted_facts=formatted_facts,
            current_summary=current_summary,
            batch_text=messages_block,
        )

        facts_response = await _llm_call(
            client,
            SUMMARY_MODEL,
            [{"role": "user", "content": user_prompt}],
            temperature=0.1,
        )
        raw_response = facts_response.choices[0].message.content

        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            action = data.get("action")
            fact_text = data.get("final_fact_text")
            fact_id = data.get("target_existing_fact_id")

            if action == "CREATE" and fact_text:
                embedding = await get_text_embedding(fact_text)
                async with session_factory() as session:
                    session.add(
                        UserMemoryFact(
                            user_id=user_id,
                            fact_text=fact_text,
                            embedding=embedding,
                        )
                    )
                    await session.commit()

            elif action == "UPDATE" and fact_text and fact_id:
                embedding = await get_text_embedding(fact_text)
                async with session_factory() as session:
                    update_success = False
                    try:
                        target_uuid = uuid.UUID(str(fact_id))
                        result = await session.execute(
                            update(UserMemoryFact)
                            .where(UserMemoryFact.id == target_uuid)
                            .values(fact_text=fact_text, embedding=embedding)
                        )
                        if result.rowcount > 0:
                            update_success = True
                    except ValueError:
                        pass  # Catch hallucinated non-UUID strings

                    if not update_success:
                        # Fallback: Create it as a new fact to prevent data loss
                        session.add(
                            UserMemoryFact(
                                user_id=user_id,
                                fact_text=fact_text,
                                embedding=embedding,
                            )
                        )

                    await session.commit()

        await redis_client.ltrim(overflow_key, len(evicted_messages), -1)

    except Exception as e:
        logger.error("Cognitive memory processing failed for %s: %s", telegram_id, e)
        return
    finally:
        await redis_client.delete(lock_key)
