from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User


async def get_or_create_profile(
    session: AsyncSession, telegram_id: int, username: str | None
) -> dict:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(telegram_id=telegram_id, username=username, role="member")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    is_onboarded = bool(user.full_name)

    return {
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "role": user.role,
        "full_name": user.full_name,
        "is_onboarded": is_onboarded,
    }


async def update_full_name(
    session: AsyncSession, telegram_id: int, full_name: str
) -> bool:
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(full_name=full_name)
    )
    await session.commit()
    return True
