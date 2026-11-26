"""Validates the interrupt/resume mechanics the whole human-approval checkpoint depends
on, against the real AsyncPostgresSaver checkpointer (not a mock) — this is the single
highest-risk piece of Phase 1's design. A minimal two-node graph is used deliberately
instead of the full 18-node pipeline: exercising the real interrupt()/Command(resume=...)
round trip doesn't need Claude/Groq/Gotenberg/SMTP in the loop, and mocking all four just
to reach this same assertion would make the test brittle without testing anything more.
Individual pipeline nodes are covered by their own unit tests; the manual curl walkthrough
in docs/local-development.md exercises the full pipeline end to end.
"""

from typing import TypedDict

import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from tests.conftest import TEST_DATABASE_URL


class _MiniState(TypedDict):
    value: str
    reply: str


def _step_one(state: _MiniState) -> _MiniState:
    return {"value": "waiting", "reply": ""}


def _step_two(state: _MiniState) -> _MiniState:
    reply = interrupt({"kind": "test_pause"})
    return {"value": state["value"], "reply": reply}


def _step_three(state: _MiniState) -> _MiniState:
    return {"value": "done", "reply": state["reply"]}


@pytest_asyncio.fixture
async def test_checkpointer():
    dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    pool = AsyncConnectionPool(dsn, max_size=5, kwargs={"autocommit": True, "row_factory": dict_row}, open=False)
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    yield checkpointer
    await pool.close()


def _build_mini_graph(checkpointer: AsyncPostgresSaver):
    graph = StateGraph(_MiniState)
    graph.add_node("one", _step_one)
    graph.add_node("two", _step_two)
    graph.add_node("three", _step_three)
    graph.add_edge(START, "one")
    graph.add_edge("one", "two")
    graph.add_edge("two", "three")
    graph.add_edge("three", END)
    return graph.compile(checkpointer=checkpointer)


async def test_graph_pauses_at_interrupt_and_persists_checkpoint(test_checkpointer) -> None:
    graph = _build_mini_graph(test_checkpointer)
    config = {"configurable": {"thread_id": "test-thread-1"}}

    result = await graph.ainvoke({"value": "", "reply": ""}, config=config)

    assert "__interrupt__" in result
    state = await graph.aget_state(config)
    assert state.next == ("two",)  # paused before step three ran


async def test_graph_resumes_and_completes_after_command(test_checkpointer) -> None:
    graph = _build_mini_graph(test_checkpointer)
    config = {"configurable": {"thread_id": "test-thread-2"}}

    await graph.ainvoke({"value": "", "reply": ""}, config=config)
    result = await graph.ainvoke(Command(resume="CONFIRM"), config=config)

    assert result["value"] == "done"
    assert result["reply"] == "CONFIRM"
    state = await graph.aget_state(config)
    assert state.next == ()  # finished, no more pending nodes


async def test_checkpoint_survives_a_fresh_checkpointer_instance() -> None:
    """The actual durability proof: a *new* AsyncPostgresSaver/pool (simulating a process
    restart) can still read and resume a checkpoint written by a previous instance —
    proving state lives in Postgres, not in-process memory."""
    dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    pool_a = AsyncConnectionPool(dsn, max_size=5, kwargs={"autocommit": True, "row_factory": dict_row}, open=False)
    await pool_a.open()
    checkpointer_a = AsyncPostgresSaver(pool_a)
    await checkpointer_a.setup()
    graph_a = _build_mini_graph(checkpointer_a)
    config = {"configurable": {"thread_id": "test-thread-durability"}}
    await graph_a.ainvoke({"value": "", "reply": ""}, config=config)
    await pool_a.close()

    pool_b = AsyncConnectionPool(dsn, max_size=5, kwargs={"autocommit": True, "row_factory": dict_row}, open=False)
    await pool_b.open()
    checkpointer_b = AsyncPostgresSaver(pool_b)
    graph_b = _build_mini_graph(checkpointer_b)
    result = await graph_b.ainvoke(Command(resume="CONFIRM"), config=config)
    await pool_b.close()

    assert result["value"] == "done"


def _build_failing_graph(checkpointer: AsyncPostgresSaver, fails: str):
    """One pause; after the answer, `fails` ("two": the answered step, "three": the one after)
    raises, as a provider or Gotenberg might."""

    def _answered(state: _MiniState) -> _MiniState:
        reply = interrupt({"kind": "test_pause"})
        if fails == "two":
            raise RuntimeError("the answered step failed")
        return {"value": state["value"], "reply": reply}

    def _after(state: _MiniState) -> _MiniState:
        if fails == "three":
            raise RuntimeError("a later step failed")
        return {"value": "done", "reply": state["reply"]}

    graph = StateGraph(_MiniState)
    graph.add_node("one", _step_one)
    graph.add_node("two", _answered)
    graph.add_node("three", _after)
    graph.add_edge(START, "one")
    graph.add_edge("one", "two")
    graph.add_edge("two", "three")
    graph.add_edge("three", END)
    return graph.compile(checkpointer=checkpointer)


@pytest.mark.parametrize("fails", ["two", "three"])
async def test_the_checkpoint_moves_on_only_once_the_answered_step_completes(test_checkpointer, fails: str) -> None:
    # What the worker's resume retries rely on (runner._resume): the same checkpoint means the
    # answer never got in; another one, with steps left and no question, that it did.
    graph = _build_failing_graph(test_checkpointer, fails)
    config = {"configurable": {"thread_id": f"test-thread-fails-{fails}"}}
    await graph.ainvoke({"value": "", "reply": ""}, config=config)
    paused_at = (await graph.aget_state(config)).config["configurable"]["checkpoint_id"]

    with pytest.raises(RuntimeError):
        await graph.ainvoke(Command(resume="CONFIRM"), config=config)

    state = await graph.aget_state(config)
    if fails == "two":
        assert state.config["configurable"]["checkpoint_id"] == paused_at
        assert [i.value for i in state.interrupts] == [{"kind": "test_pause"}]
    else:
        assert state.config["configurable"]["checkpoint_id"] != paused_at
        assert (state.next, state.interrupts) == (("three",), ())
