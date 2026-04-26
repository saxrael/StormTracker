from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse.openai import AsyncOpenAI

from app.config import get_settings


@lru_cache
def get_gemma_llm() -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model="gemma-4-31b-it",
        temperature=0.25,
        api_key=settings.GOOGLE_AI_API_KEY,
        model_kwargs={"thinking_config": {"thoughts": True}},
    )


@lru_cache
def _get_openrouter_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )


async def get_image_embedding(base64_string: str) -> list[float]:
    client = _get_openrouter_client()
    response = await client.embeddings.create(
        model="nvidia/llama-nemotron-embed-vl-1b-v2:free",
        input=[
            {
                "content": [
                    {"type": "text", "text": "Analyze this image."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_string}"},
                    },
                ]
            }
        ],
        encoding_format="float",
    )
    return response.data[0].embedding


async def get_text_embedding(text: str) -> list[float]:
    client = _get_openrouter_client()
    response = await client.embeddings.create(
        model="nvidia/llama-nemotron-embed-vl-1b-v2:free",
        input=text,
        encoding_format="float",
    )
    return response.data[0].embedding
