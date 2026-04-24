import base64

import httpx
from fastapi import HTTPException

from app.config import get_settings


class TelegramService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = (
            f"https://api.telegram.org/bot{self.settings.TELEGRAM_BOT_TOKEN}"
        )
        self.file_url = (
            f"https://api.telegram.org/file/bot{self.settings.TELEGRAM_BOT_TOKEN}"
        )

    async def send_message(self, chat_id: int, text: str) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": text}
            )
            response.raise_for_status()

    async def get_file_path(self, file_id: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(
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
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.file_url}/{file_path}")
            response.raise_for_status()
            return base64.b64encode(response.content).decode("utf-8")

    async def send_document(self, chat_id: int, document_path: str, caption: str = ""):
        async with httpx.AsyncClient() as client:
            with open(document_path, "rb") as file_obj:
                response = await client.post(
                    f"{self.base_url}/sendDocument",
                    data={"chat_id": chat_id, "caption": caption},
                    files={"document": file_obj},
                )
                response.raise_for_status()


telegram_service = TelegramService()
