from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    chat_id: int
    user_id: int
    username: str | None
    role: str
    image_base64: str | None
    extracted_metrics: dict | None
    image_vector: list[float] | None
    task_status: str
    retry_count: int
    critique: str | None
