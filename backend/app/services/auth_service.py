import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.refresh_token import RefreshToken
from app.models.user import User


async def _insert_refresh(session: AsyncSession, user_id: int, jti: str, exp: datetime) -> None:
    session.add(RefreshToken(user_id=user_id, jti=jti, expires_at=exp))
    await session.commit()


async def issue_pair(session: AsyncSession, user: User) -> dict[str, str]:
    access = create_access_token(user.id)
    refresh, jti, exp = create_refresh_token(user.id)
    await _insert_refresh(session, user.id, jti, exp)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


async def _get_by_jti(session: AsyncSession, jti: str) -> RefreshToken | None:
    return (await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))).scalar_one_or_none()


async def _revoke_all(session: AsyncSession, user_id: int) -> None:
    await session.execute(update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True))
    await session.commit()


async def rotate(session: AsyncSession, refresh_token: str) -> dict[str, str]:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("wrong token type")
    row = await _get_by_jti(session, payload["jti"])
    if row is None:
        raise LookupError("unknown refresh token")
    if row.revoked:
        await _revoke_all(session, row.user_id)
        raise PermissionError("refresh token reuse detected")
    await session.execute(update(RefreshToken).where(RefreshToken.jti == payload["jti"]).values(revoked=True))
    user = (await session.execute(select(User).where(User.id == row.user_id))).scalar_one()
    await session.commit()
    return await issue_pair(session, user)


async def revoke(session: AsyncSession, refresh_token: str) -> None:
    payload = decode_token(refresh_token)
    await session.execute(update(RefreshToken).where(RefreshToken.jti == payload["jti"]).values(revoked=True))
    await session.commit()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_jti() -> str:
    return uuid.uuid4().hex
