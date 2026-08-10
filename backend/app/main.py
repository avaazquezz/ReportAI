from fastapi import FastAPI

from app.api import health
from app.core.config import settings

app = FastAPI(title="ReportAI API", version="0.1.0")
app.include_router(health.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "reportai-api", "environment": settings.ENVIRONMENT}
