from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — a health probe reports status, it never propagates
        # 503, not 200-with-"degraded": uptime monitors and load balancers only look at the code.
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "down"})
    return JSONResponse(content={"status": "ok", "database": "ok"})
