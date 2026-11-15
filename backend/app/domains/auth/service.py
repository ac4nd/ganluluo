from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.domains.admin.quota_service import seed_tiers
from app.domains.auth.schemas import RegisterIn
from app.models.profile import UserProfile
from app.models.user import User


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
    # 注册时确保配额档位存在（M5-admin Task 2）：seed_tiers 幂等，quota_tiers 空库首注册
    # 补 trial/vip 两行。users.quota_tier 由列默认 'trial' 承载，无需按用户建行。
    await seed_tiers(session)
    await session.refresh(user)
    return user


async def get_by_identity(session: AsyncSession, email: str | None, phone: str | None) -> User | None:
    stmt = select(User).where(User.deleted_at.is_(None))
    if email:
        stmt = stmt.where(User.email == email)
    else:
        stmt = stmt.where(User.phone == phone)
    return (await session.execute(stmt)).scalar_one_or_none()
