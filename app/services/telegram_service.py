import base64
import html
import re

import httpx
from fastapi import HTTPException

from app.config import get_settings

_client: httpx.AsyncClient | None = None


def startup_telegram_client():
    global _client
    _client = httpx.AsyncClient(timeout=30.0)


async def shutdown_telegram_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None


def _markdown_to_html(text: str) -> str:
    if not text:
        return ""

    text = html.escape(text)

    text = re.sub(r"```(.*?)```", r"<pre>\1</pre>", text, flags=re.DOTALL)
    text = re.sub(r"`(.*?)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', text)

    return text


class TelegramService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = (
            f"https://api.telegram.org/bot{self.settings.TELEGRAM_BOT_TOKEN}"
        )
        self.file_url = (
            f"https://api.telegram.org/file/bot{self.settings.TELEGRAM_BOT_TOKEN}"
        )
        self.client = _client or httpx.AsyncClient(timeout=30.0)

    async def send_message(self, chat_id: int, text: str) -> None:
        safe_html = _markdown_to_html(text)
        response = await self.client.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": safe_html,
                "parse_mode": "HTML",
            },
        )
        response.raise_for_status()

    async def get_file_path(self, file_id: str) -> str:
        response = await self.client.get(
            f"{self.base_url}/getFile", params={"file_id": file_id}
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise HTTPException(
                status_code=500, detail="Telegram returned error on getFile"
            )
        return data["result"]["file_path"]

    async def download_image_as_base64(self, file_path: str) -> str:
        response = await self.client.get(f"{self.file_url}/{file_path}")
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")

    async def send_document(self, chat_id: int, document_path: str, caption: str = ""):
        safe_caption = _markdown_to_html(caption)
        with open(document_path, "rb") as file_obj:
            response = await self.client.post(
                f"{self.base_url}/sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": safe_caption,
                    "parse_mode": "HTML",
                },
                files={"document": file_obj},
            )
            response.raise_for_status()


telegram_service = TelegramService()
