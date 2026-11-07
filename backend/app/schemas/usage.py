from pydantic import BaseModel


class DailyCostPoint(BaseModel):
    date: str
    cost_usd: float


class UsageSummaryResponse(BaseModel):
    total_cost_usd: float
    total_reports: int
    reports_by_status: dict[str, int]
    avg_latency_ms: float | None
    total_input_tokens: int
    total_output_tokens: int
    total_audio_minutes: float
    daily_cost: list[DailyCostPoint]
