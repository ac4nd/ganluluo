from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.services.gear_service import get_catalog

router = APIRouter(prefix="/gear", tags=["gear"])


@router.get("/catalog")
async def catalog(session: AsyncSession = Depends(get_session)) -> dict:
    return await get_catalog(session)
