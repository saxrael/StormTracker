import json
import logging

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph

from app.agents.llm_setup import get_gemma_llm, get_image_embedding
from app.agents.prompts import get_formatted_system_prompt
from app.agents.tools import authenticate_user, query_analytics
from app.config import get_settings
from app.schemas.schemas import MetricExtractionSchema
from app.state.state import AgentState

logger = logging.getLogger(__name__)

_TOOL_REGISTRY = {
    "query_analytics": query_analytics,
    "authenticate_user": authenticate_user,
}


def reasoning_core(state: AgentState) -> dict:
    llm = get_gemma_llm()
    llm_with_tools = llm.bind_tools(
        [MetricExtractionSchema, query_analytics, authenticate_user]
    )
    system_prompt = get_formatted_system_prompt(
        user_role=state["role"],
        task_status=state["task_status"],
        retry_count=state["retry_count"],
        critique_block=state.get("critique"),
    )
    response = llm_with_tools.invoke(
        [SystemMessage(content=system_prompt)] + list(state["messages"])
    )
    return {"messages": [response]}


def action_router(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool_executor"
    return END


def tool_executor(state: AgentState) -> dict:
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
                image_b64 = state.get("image_base64")
                if image_b64:
                    image_vector = get_image_embedding(image_b64)
                tool_messages.append(
                    ToolMessage(
                        content=json.dumps(extracted_metrics),
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
            result = _TOOL_REGISTRY[name].invoke(args)
            tool_messages.append(
                ToolMessage(content=str(result), tool_call_id=call_id)
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
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            break
        if isinstance(msg, ToolMessage):
            content_lower = msg.content.lower()
            if "failed" in content_lower or "error" in content_lower:
                return {
                    "task_status": "review",
                    "retry_count": state["retry_count"] + 1,
                    "critique": msg.content,
                }
    return {"task_status": "approved", "critique": None}


def _review_router(state: AgentState) -> str:
    if state["task_status"] == "review":
        return "reasoning_core"
    return END


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


async def execute_graph(state: AgentState, session_id: str) -> dict:
    from langfuse.langchain import CallbackHandler

    settings = get_settings()
    langfuse_handler = CallbackHandler(
        session_id=session_id,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
    )
    return await stormtracker_app.ainvoke(
        state, config={"callbacks": [langfuse_handler]}
    )
