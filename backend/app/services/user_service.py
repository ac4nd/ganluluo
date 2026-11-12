from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.profile import UserProfile
from app.models.user import User
from app.schemas.auth import RegisterIn


async def create_user(session: AsyncSession, data: RegisterIn) -> User:
    user = User(
        email=data.email,
        phone=data.phone,
        nickname=data.nickname,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await session.commit()
    # 注册即建默认画像（sports=[] exp_level=1 fitness=2）
    session.add(UserProfile(user_id=user.id))
    await session.commit()
    await session.refresh(user)
    return user


async def get_by_identity(session: AsyncSession, email: str | None, phone: str | None) -> User | None:
    stmt = select(User).where(User.deleted_at.is_(None))
    if email:
        stmt = stmt.where(User.email == email)
    else:
        stmt = stmt.where(User.phone == phone)
    return (await session.execute(stmt)).scalar_one_or_none()
