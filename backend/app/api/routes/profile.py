from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.schemas.profile import ProfileIn, ProfileOut
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
async def get_profile(current: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> ProfileOut:
    row = await profile_service.get_or_create(session, current.id)
    return ProfileOut(sports=row.sports, exp_level=row.exp_level, fitness=row.fitness)


@router.put("", response_model=ProfileOut)
async def put_profile(data: ProfileIn, current: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> ProfileOut:
    row = await profile_service.update(session, current.id, data)
    return ProfileOut(sports=row.sports, exp_level=row.exp_level, fitness=row.fitness)
