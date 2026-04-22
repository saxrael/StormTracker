from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PhotoSize(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: Optional[int] = None


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None


class Chat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    message_id: int
    chat: Chat
    from_: User = Field(alias="from")
    text: Optional[str] = None
    photo: Optional[List[PhotoSize]] = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    update_id: int
    message: Optional[Message] = None
