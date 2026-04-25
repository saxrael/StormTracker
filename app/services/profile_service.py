from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User


async def get_or_create_profile(
    session: AsyncSession, telegram_id: int, username: str | None
) -> dict:
    stmt = (
        insert(User)
        .values(telegram_id=telegram_id, username=username, role="member")
        .on_conflict_do_update(
            index_elements=["telegram_id"],
            set_=dict(username=username),
        )
        .returning(User)
    )
    result = await session.execute(stmt)
    user = result.scalar_one()
    await session.commit()

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
