from unittest.mock import AsyncMock

import pytest

from app.services.agent.tools import intent
from app.services.llm import LLMResult


@pytest.mark.parametrize(
    "reply",
    ["Sí.", "sí", "ok!", "OK", "  Confirmo  ", "Vale, perfecto", "¡Adelante!", "👍", "✅", "todo bien", "Yes"],
)
def test_obvious_confirmations_are_settled_without_the_model(reply: str) -> None:
    assert intent.quick_intent(reply) == "confirm"


@pytest.mark.parametrize("reply", ["cancelar", "Cancela.", "descartar", "❌", "anular"])
def test_obvious_cancellations_are_settled_without_the_model(reply: str) -> None:
    assert intent.quick_intent(reply) == "cancel"


@pytest.mark.parametrize("reply", ["No", "no.", "incorrecto", "No está bien"])
def test_a_bare_no_means_not_right_so_ask_what_to_change(reply: str) -> None:
    assert intent.quick_intent(reply) == "ask"


@pytest.mark.parametrize("reply", ["la fecha era el martes", "no, era el martes", "Vale, pero cambia el cliente"])
def test_anything_with_content_is_left_to_the_model(reply: str) -> None:
    assert intent.quick_intent(reply) is None


async def test_the_model_decides_what_rules_cannot(monkeypatch: pytest.MonkeyPatch) -> None:
    ask = AsyncMock(return_value=LLMResult({"intent": "correct"}, 50, 5, "claude-sonnet-5"))
    monkeypatch.setattr(intent, "structured_completion", ask)

    result, usage = await intent.classify_reply("la fecha era el martes")

    assert result == "correct" and usage is not None and usage.input_tokens == 50
    ask.assert_awaited_once()


async def test_a_quick_answer_costs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    ask = AsyncMock()
    monkeypatch.setattr(intent, "structured_completion", ask)

    assert await intent.classify_reply("Sí.") == ("confirm", None)
    ask.assert_not_awaited()


async def test_a_model_failure_is_treated_as_a_correction_not_a_lost_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intent, "structured_completion", AsyncMock(side_effect=TimeoutError()))

    assert await intent.classify_reply("cambia la fecha") == ("correct", None)
