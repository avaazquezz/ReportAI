import functools
import time
import uuid
from collections.abc import Awaitable, Callable

from langgraph.errors import GraphInterrupt

from app.core.database import AsyncSessionLocal
from app.models.execution_log import ExecutionLog
from app.services.agent.state import AgentState

# All nodes are async — including validate_node, which does no I/O but stays
# async for interface uniformity so this wrapper doesn't need a sync branch.
NodeFn = Callable[[AgentState], Awaitable[AgentState]]


async def write_execution_log(
    *,
    tenant_id: uuid.UUID,
    report_id: uuid.UUID,
    step: str,
    status: str,
    model_used: str | None = None,
    cost_usd: float | None = None,
    latency_ms: int | None = None,
    error_detail: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            ExecutionLog(
                tenant_id=tenant_id,
                report_id=report_id,
                step=step,
                status=status,
                model_used=model_used,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                error_detail=error_detail,
            )
        )
        await session.commit()


def observed_node(step: str) -> Callable[[NodeFn], Callable[[AgentState], Awaitable[AgentState]]]:
    """Wrap a node so every execution — success, interrupt, or failure — is traced.

    Applied to every node, not a single terminal "log" node, so a mid-graph
    crash is still fully traced.
    """

    def decorator(fn: NodeFn) -> Callable[[AgentState], Awaitable[AgentState]]:
        @functools.wraps(fn)
        async def wrapper(state: AgentState) -> AgentState:
            start = time.monotonic()
            try:
                new_state = await fn(state)

                usage = new_state.last_tool_usage
                await write_execution_log(
                    tenant_id=new_state.tenant_id,
                    report_id=new_state.report_id,
                    step=step,
                    status="success",
                    model_used=usage.model_used if usage else None,
                    cost_usd=usage.cost_usd if usage else None,
                    latency_ms=int((time.monotonic() - start) * 1000),
                )
                return new_state.model_copy(update={"last_tool_usage": None})
            except GraphInterrupt:
                # interrupt() raises GraphInterrupt, which propagates through this
                # node's frame before the graph runtime suppresses it at the root.
                # Must not be logged as an error — that would mislabel every pause.
                await write_execution_log(
                    tenant_id=state.tenant_id,
                    report_id=state.report_id,
                    step=step,
                    status="interrupted",
                    latency_ms=int((time.monotonic() - start) * 1000),
                )
                raise
            except Exception as exc:
                await write_execution_log(
                    tenant_id=state.tenant_id,
                    report_id=state.report_id,
                    step=step,
                    status="error",
                    latency_ms=int((time.monotonic() - start) * 1000),
                    error_detail=str(exc)[:2000],
                )
                raise

        return wrapper

    return decorator
