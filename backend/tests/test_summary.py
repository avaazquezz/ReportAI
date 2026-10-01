from app.services.agent.summary import build_summary, chunk_text, format_value

SCHEMA = {
    "visit_date": {"type": "date", "label": "Fecha de la visita", "required": True},
    "site_ok": {"type": "bool"},
    "contacts": {"type": "list[str]"},
    "action_items": {"type": "list[str]"},
    "findings": {
        "type": "list[object]",
        "columns": {"description": {"type": "str"}, "deadline": {"type": "date"}},
    },
    "arrival": {"type": "time"},
    "summary": {"type": "str", "required": True},
}


def test_the_recap_uses_labels_and_formats_values_for_the_reader() -> None:
    fields = {
        "visit_date": "2026-08-18", "site_ok": True, "contacts": ["Ana", "Luis"],
        "action_items": [], "findings": [], "arrival": "09:30", "summary": "Todo en orden",
    }

    es = build_summary("es", SCHEMA, fields)
    en = build_summary("en", SCHEMA, fields)

    assert "• Fecha de la visita: 18/08/2026" in es and "• Fecha de la visita: 2026-08-18" in en
    assert "• Site ok: Sí" in es and "• Site ok: Yes" in en
    assert "• Contacts: Ana, Luis" in es
    assert "action_items" not in es and "• Action items: —" in es  # no snake_case, no Python lists
    assert "['" not in es


def test_a_missing_required_field_is_flagged() -> None:
    summary = build_summary("es", SCHEMA, {"visit_date": None, "summary": "x"})
    assert "• ⚠️ Fecha de la visita: —" in summary
    assert "⚠️ Summary" not in summary  # present, so not flagged


def test_a_table_is_shown_one_row_per_line() -> None:
    value = [
        {"description": "Barandilla suelta", "deadline": "2026-10-01"},
        {"description": "Falta señalización", "deadline": None},
    ]
    text = format_value("es", SCHEMA["findings"], value)
    assert "– Description: Barandilla suelta; Deadline: 01/10/2026" in text
    assert "– Description: Falta señalización; Deadline: —" in text


def test_photos_are_counted_in_the_recap() -> None:
    schema = {"site_photos": {"type": "image", "multiple": True}}
    assert build_summary("es", schema, {}, photo_count=3) == "• Site photos: 📎 3"
    assert build_summary("es", schema, {}) == "• Site photos: —"


def test_long_recaps_are_split_on_line_breaks_never_mid_field() -> None:
    text = "\n".join(f"• Campo {i}: " + "x" * 200 for i in range(40))
    chunks = chunk_text(text, limit=1000)
    assert len(chunks) > 1 and all(len(chunk) <= 1000 for chunk in chunks)
    assert "\n".join(chunks) == text  # nothing lost, nothing reordered


def test_a_single_huge_line_is_cut_rather_than_dropped() -> None:
    chunks = chunk_text("y" * 2500, limit=1000)
    assert [len(c) for c in chunks] == [1000, 1000, 500]


def test_numbers_read_as_people_write_them() -> None:
    from app.services.agent.summary import format_value

    assert format_value("es", {"type": "float"}, 2.0) == "2"
    assert format_value("es", {"type": "float"}, 2.5) == "2,5"
    assert format_value("en", {"type": "float"}, 2.5) == "2.5"
    assert format_value("es", {"type": "int"}, 3) == "3"
