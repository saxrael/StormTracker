from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import get_settings
from app.schemas.telegram_schemas import TelegramUpdate
from app.services.telegram_service import telegram_service

router = APIRouter()

def verify_telegram_token(x_telegram_bot_api_secret_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.post("/webhook", dependencies=[Depends(verify_telegram_token)])
async def telegram_webhook(update: TelegramUpdate) -> dict:
    if update.message and update.message.photo:
        photo = update.message.photo[-1]
        try:
            file_path = await telegram_service.get_file_path(photo.file_id)
            _ = await telegram_service.download_image_as_base64(file_path)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to process image")
            
    return {"status": "ok"}
