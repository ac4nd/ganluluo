from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.auth import RegisterIn, UserOut
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: RegisterIn, session: AsyncSession = Depends(get_session)) -> UserOut:
    try:
        user = await user_service.create_user(session, data)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="邮箱或手机号已注册") from None
    return UserOut.model_validate(user)
