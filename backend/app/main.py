from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title="ReportAI API", version="0.1.0")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "reportai-api", "environment": settings.ENVIRONMENT}
