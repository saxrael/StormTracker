import json
import logging
import re

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from sqlalchemy.dialects.postgresql import insert

from app.agents.llm_setup import get_gemma_llm, get_image_embedding
from app.agents.prompts import get_formatted_system_prompt
from app.agents.tools import (
    authenticate_user,
    generate_admin_report,
    query_analytics,
    update_profile,
    visual_search,
)
from app.config import get_settings
from app.models.models import Metric, Submission, User
from app.schemas.schemas import MetricExtractionSchema
from app.services import conversation_service, fraud_service
from app.services.database import async_session, redis_client
from app.services.telegram_service import TelegramService
from app.state.state import AgentState

logger = logging.getLogger(__name__)


def _normalize_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and "text" in block:
                texts.append(block["text"])
        return " ".join(texts)
    if content is None:
        return ""
    return str(content)


_TOOL_REGISTRY = {
    "query_analytics": query_analytics,
    "authenticate_user": authenticate_user,
    "generate_admin_report": generate_admin_report,
    "visual_search": visual_search,
    "update_profile": update_profile,
}


def reasoning_core(state: AgentState) -> dict:
    llm = get_gemma_llm()
    llm_with_tools = llm.bind_tools(
        [
            MetricExtractionSchema,
            query_analytics,
            authenticate_user,
            generate_admin_report,
            visual_search,
            update_profile,
        ]
    )
    system_prompt = get_formatted_system_prompt(
        user_role=state["role"],
        full_name=state.get("full_name"),
        is_onboarded=state.get("is_onboarded", False),
        summary=state.get("conversation_summary"),
        facts=state.get("relevant_facts"),
        task_status=state["task_status"],
        retry_count=state["retry_count"],
        critique_block=state.get("critique"),
    )
    response = llm_with_tools.invoke(
        [SystemMessage(content=system_prompt)] + list(state["messages"])
    )

    thinking = (
        response.additional_kwargs.get("thinking")
        or response.response_metadata.get("thinking")
        or response.additional_kwargs.get("reasoning_details")
        or response.response_metadata.get("reasoning_details")
        or response.additional_kwargs.get("thoughts")
        or response.response_metadata.get("thoughts")
    )

    if thinking:
        safe_content = _normalize_content(response.content)
        safe_content = f"<thought>\n{thinking}\n</thought>\n\n" + safe_content
        response.content = safe_content

    return {"messages": [response]}


def action_router(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool_executor"
    return END


async def tool_executor(state: AgentState) -> dict:
    last_message: AIMessage = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    extracted_metrics = None
    image_vector = None

    for call in last_message.tool_calls:
        name = call["name"]
        args = call["args"]
        call_id = call["id"]

        if name == "MetricExtractionSchema":
            try:
                validated = MetricExtractionSchema(**args)
                extracted_metrics = validated.model_dump(mode="json")
                extracted_metrics["granular_details"] = [
                    d.model_dump() for d in validated.details
                ]
                image_b64 = state.get("image_base64")
                db_user_id = state["db_user_id"]
                username = state.get("username")
                user_id_tg = state.get("user_id")

                if image_b64:
                    image_vector = await get_image_embedding(image_b64)

                async with async_session() as session:
                    try:
                        device_metadata = extracted_metrics.get("device_metadata")
                        if device_metadata:
                            meta_dup = await fraud_service.check_metadata_duplicate(
                                session, db_user_id, device_metadata
                            )
                            if meta_dup:
                                msg = (
                                    "Fraud detected: Duplicate device metadata "
                                    "within 24h."
                                )
                                tool_messages.append(
                                    ToolMessage(
                                        content=msg,
                                        tool_call_id=call_id,
                                    )
                                )
                                continue

                        if image_vector:
                            sim = await fraud_service.check_visual_duplicate(
                                session, db_user_id, image_vector
                            )
                            settings = get_settings()
                            if sim > settings.IMAGE_SIMILARITY_THRESHOLD:
                                msg = "Fraud detected: Image is a visual duplicate."
                                tool_messages.append(
                                    ToolMessage(
                                        content=msg,
                                        tool_call_id=call_id,
                                    )
                                )
                                continue

                        stmt_user = (
                            insert(User)
                            .values(
                                telegram_id=user_id_tg,
                                username=username,
                                role=state.get("role", "member"),
                            )
                            .on_conflict_do_update(
                                index_elements=["telegram_id"],
                                set_=dict(username=username),
                            )
                            .returning(User.id)
                        )

                        result_user = await session.execute(stmt_user)
                        resolved_user_id = result_user.scalar_one()

                        stmt_sub_insert = (
                            insert(Submission)
                            .values(user_id=resolved_user_id, status="processed")
                            .returning(Submission.id)
                        )
                        result_sub = await session.execute(stmt_sub_insert)
                        db_sub_id = result_sub.scalar_one()

                        stmt_metric_insert = insert(Metric).values(
                            submission_id=db_sub_id,
                            exercise_type=extracted_metrics.get(
                                "exercise_type", "unknown"
                            ),
                            total_questions=extracted_metrics.get("total_questions", 0),
                            total_correct=extracted_metrics.get("total_correct", 0),
                            overall_score_percentage=extracted_metrics.get(
                                "overall_score_percentage", 0.0
                            ),
                            granular_details=extracted_metrics.get(
                                "granular_details", {}
                            ),
                            device_metadata=device_metadata,
                            image_vector=image_vector,
                        )
                        await session.execute(stmt_metric_insert)
                        await session.commit()

                        tool_messages.append(
                            ToolMessage(
                                content=json.dumps(extracted_metrics),
                                tool_call_id=call_id,
                            )
                        )
                    except Exception as exc:
                        await session.rollback()
                        logger.error("DB Error during MetricExtraction: %s", exc)
                        tool_messages.append(
                            ToolMessage(
                                content=f"Database commit failed: {exc}",
                                tool_call_id=call_id,
                            )
                        )

            except Exception as exc:
                logger.warning("Metric extraction failed: %s", exc)
                tool_messages.append(
                    ToolMessage(
                        content=f"Schema validation failed: {exc}",
                        tool_call_id=call_id,
                    )
                )
        elif name in _TOOL_REGISTRY:
            try:
                tool_args = args.copy()
                if name in ["query_analytics", "authenticate_user"]:
                    tool_args["db_user_id"] = state["db_user_id"]
                if name == "query_analytics":
                    tool_args["role"] = state["role"]
                if name == "visual_search":
                    tool_args["image_base64"] = state.get("image_base64")
                if name == "update_profile":
                    tool_args["telegram_id"] = state["user_id"]
                result = await _TOOL_REGISTRY[name].ainvoke(tool_args)
                tool_messages.append(
                    ToolMessage(content=str(result), tool_call_id=call_id)
                )
            except Exception as exc:
                logger.error("Tool %s failed: %s", name, exc)
                tool_messages.append(
                    ToolMessage(
                        content=f"Tool execution failed: {exc}",
                        tool_call_id=call_id,
                    )
                )
        else:
            tool_messages.append(
                ToolMessage(
                    content=f"Error: unknown tool '{name}'",
                    tool_call_id=call_id,
                )
            )

    updates: dict = {"messages": tool_messages}
    if extracted_metrics is not None:
        updates["extracted_metrics"] = extracted_metrics
    if image_vector is not None:
        updates["image_vector"] = image_vector
    return updates


def internal_reviewer(state: AgentState) -> dict:
    critiques = []
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            break
        if isinstance(msg, ToolMessage):
            content_lower = msg.content.lower()
            if (
                "failed" in content_lower
                or "error" in content_lower
                or "fraud" in content_lower
                or "invalid" in content_lower
            ):
                critiques.append(msg.content)

    if critiques:
        return {
            "task_status": "review",
            "retry_count": state.get("retry_count", 0) + 1,
            "critique": "\n".join(critiques),
        }
    return {"task_status": "approved", "critique": None}


def _review_router(state: AgentState) -> str:
    if state.get("retry_count", 0) >= 3:
        return END
    return "reasoning_core"


builder = StateGraph(AgentState)
builder.add_node("reasoning_core", reasoning_core)
builder.add_node("tool_executor", tool_executor)
builder.add_node("internal_reviewer", internal_reviewer)

builder.set_entry_point("reasoning_core")
builder.add_conditional_edges(
    "reasoning_core",
    action_router,
    {"tool_executor": "tool_executor", END: END},
)
builder.add_edge("tool_executor", "internal_reviewer")
builder.add_conditional_edges(
    "internal_reviewer",
    _review_router,
    {"reasoning_core": "reasoning_core", END: END},
)

stormtracker_app = builder.compile()


async def execute_graph(
    state: AgentState, session_id: str, raw_user_text: str = ""
) -> dict:
    from langfuse.langchain import CallbackHandler

    langfuse_handler = CallbackHandler()
    result_state = await stormtracker_app.ainvoke(
        state,
        config={
            "callbacks": [langfuse_handler],
            "metadata": {"langfuse_session_id": session_id},
        },
    )

    final_message = _normalize_content(result_state["messages"][-1].content)
    clean_message = re.sub(
        r"<thought>.*?</thought>", "", final_message, flags=re.DOTALL
    ).strip()
    if not clean_message:
        clean_message = "Processed successfully."

    telegram_client = TelegramService()
    await telegram_client.send_message(chat_id=int(session_id), text=clean_message)

    await conversation_service.persist_turn(
        int(session_id), raw_user_text, clean_message, async_session, redis_client
    )

    return result_state
