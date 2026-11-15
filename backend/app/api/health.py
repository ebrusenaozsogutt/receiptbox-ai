from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.health import HealthResponse
from app.services.health import check_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(session: Annotated[AsyncSession, Depends(get_session)]):
    result = await check_health(session)
    if result.db != "ok":
        return JSONResponse(status_code=503, content=result.model_dump())
    return result
