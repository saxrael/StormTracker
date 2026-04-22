from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from openai import OpenAI

from app.config import get_settings


@lru_cache
def get_gemma_llm() -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model="gemma-4-31b-it",
        api_key=settings.GOOGLE_AI_API_KEY,
        model_kwargs={"thinking_config": {"thoughts": True}},
    )


@lru_cache
def _get_openrouter_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )


def get_image_embedding(base64_string: str) -> list[float]:
    client = _get_openrouter_client()
    response = client.embeddings.create(
        model="nvidia/llama-nemotron-embed-vl-1b-v2",
        input=[
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_string}"},
            }
        ],
    )
    return response.data[0].embedding
