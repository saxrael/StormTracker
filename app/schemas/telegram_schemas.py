from pydantic import BaseModel, ConfigDict, Field


class PhotoSize(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: int | None = None


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    username: str | None = None
    first_name: str | None = None


class Chat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    username: str | None = None
    first_name: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: int
    chat: Chat
    from_: User = Field(alias="from")
    text: str | None = None
    caption: str | None = None
    photo: list[PhotoSize] | None = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: Message | None = None
