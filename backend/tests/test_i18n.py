import string
from datetime import date

import pytest

from app.services.i18n import (
    SUPPORTED_LANGUAGES,
    catalog,
    format_date,
    humanize_key,
    normalize_language,
    t,
)


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_both_languages_define_exactly_the_same_messages() -> None:
    es, en = catalog("es"), catalog("en")
    assert es.keys() == en.keys()
    for key in es:
        assert _placeholders(es[key]) == _placeholders(en[key]), key


def test_messages_are_formatted_in_the_requested_language() -> None:
    assert t("es", "delivered", doc_type="Acta") == "Tu Acta está listo."
    assert t("en", "delivered", doc_type="Minutes") == "Your Minutes is ready."


def test_unknown_or_missing_language_falls_back_to_spanish() -> None:
    assert t(None, "cancelled") == t("es", "cancelled")
    assert t("fr", "cancelled") == t("es", "cancelled")
    assert normalize_language("EN-us") == "en"
    assert set(SUPPORTED_LANGUAGES) == {"es", "en"}


def test_an_unknown_key_is_a_bug_not_a_silent_blank() -> None:
    with pytest.raises(KeyError):
        t("es", "no_such_message")


def test_dates_follow_the_reader_and_keys_become_labels() -> None:
    assert format_date("es", date(2026, 8, 18)) == "18/08/2026"
    assert format_date("en", date(2026, 8, 18)) == "2026-08-18"
    assert humanize_key("action_items") == "Action items"
