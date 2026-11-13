from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.domains.sports.gear_schemas import GearItemOut, GearListIn
from app.domains.sports import gear_service

# No router prefix: /gear-list is a top-level per-user resource, so the catalog
# spells its full path and the gear-list endpoints match the brief verbatim.
router = APIRouter(tags=["gear"])


@router.get("/gear/catalog")
async def catalog(session: AsyncSession = Depends(get_session)) -> dict:
    return await gear_service.get_catalog(session)


@router.get("/gear-list", response_model=list[GearItemOut])
async def get_gear_list(current: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[GearItemOut]:
    return await gear_service.get_gear_list(session, current.id)


@router.put("/gear-list", response_model=list[GearItemOut])
async def put_gear_list(data: GearListIn, current: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[GearItemOut]:
    try:
        return await gear_service.replace_gear_list(session, current.id, data.items)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
