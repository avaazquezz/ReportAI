from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:  # noqa: BLE001 — a health probe reports status, it never propagates
        database_status = "degraded"

    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "database": database_status,
    }
