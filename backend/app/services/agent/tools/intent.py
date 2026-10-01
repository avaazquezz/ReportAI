"""What does a reply to "confirm or correct this?" mean (IA-6)?

Exact-match confirmation words made "Sí." or "ok!" count as a correction and paid for another
extraction. Short, unambiguous replies are settled by rules here at no cost; anything longer goes
to the model, because telling "la fecha era el martes" (correct) from "vale, pero mándalo ya"
(confirm) is exactly what rules are bad at."""

import re
from typing import Literal

from pydantic import BaseModel

from app.services.llm import LLMResult, structured_completion

Intent = Literal["confirm", "correct", "cancel", "new_report", "ask"]

_CONFIRM = {
    "confirm", "confirmar", "confirmo", "confirmado", "si", "sí", "yes", "yep", "ok", "okay", "vale",
    "adelante", "perfecto", "genial", "listo", "correcto", "todo bien", "de acuerdo", "dale",
    "👍", "✅", "👌", "si correcto", "sí correcto", "ok perfecto", "vale perfecto",
}
_CANCEL = {
    "cancel", "cancelar", "cancela", "cancelado", "descartar", "descarta", "anular", "anula",
    "olvidalo", "olvídalo", "no lo quiero", "❌",
}
# A bare "no" means "that's not right", not "throw it away": ask what to change.
_ASK = {"no", "nope", "incorrecto", "mal", "error", "no es correcto", "no esta bien", "no está bien"}

_PUNCTUATION = re.compile(r"[.,;:!¡¿?\"'()\-]+")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", _PUNCTUATION.sub(" ", text.lower())).strip()


def quick_intent(text: str) -> Intent | None:
    """Settles the obvious replies without a model call."""
    cleaned = normalize(text)
    if cleaned in _CONFIRM:
        return "confirm"
    if cleaned in _CANCEL:
        return "cancel"
    if cleaned in _ASK:
        return "ask"
    return None


class _Classification(BaseModel):
    intent: Literal["confirm", "correct", "cancel", "new_report"]


_SYSTEM = (
    "A person was shown a summary of a report and asked to confirm it or say what to change. "
    "Classify their reply: 'confirm' (they approve it as it is, possibly with thanks), "
    "'correct' (they change something, add missing information, or question a value), "
    "'cancel' (they want to discard the report), or 'new_report' (the message is the start of a "
    "different, unrelated report, not a comment on this one). If unsure, answer 'correct'."
)


async def classify_reply(text: str) -> tuple[Intent, LLMResult | None]:
    """Returns the intent and, when the model was asked, its usage (so the cost is logged)."""
    quick = quick_intent(text)
    if quick is not None:
        return quick, None
    try:
        result = await structured_completion(
            system=_SYSTEM, user=text, model_cls=_Classification, tool_name="classify_reply", max_tokens=200
        )
        return _Classification.model_validate(result.data).intent, result
    except Exception:  # noqa: BLE001 — a classifier hiccup must not lose the person's message
        return "correct", None
