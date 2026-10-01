"""The golden set's own machinery, checked without calling any model: a wrong ground truth or a
lenient comparator would make the real eval report numbers that mean nothing."""

import re
from datetime import timedelta

from app.services.agent.tools.extraction_schema import build_extraction_model
from tests.eval.golden import TODAY, VISIT_SCHEMA, Case, build_cases, grade, values_match


def test_the_set_is_large_and_the_same_on_every_run() -> None:
    first, second = build_cases(), build_cases()
    generated = [case for case in first if not case.id.startswith("legacy-")]

    assert len(generated) >= 50
    assert [(c.id, c.text, c.expected) for c in first] == [(c.id, c.text, c.expected) for c in second]
    assert len({case.text for case in generated}) == len(generated)  # no duplicated messages


def test_every_ground_truth_is_valid_against_its_own_schema() -> None:
    for case in build_cases():
        model = build_extraction_model(case.document_type_name, case.field_schema)
        model.model_validate(case.expected)  # raises on a value the pipeline could never produce


def test_relative_days_resolve_from_the_moment_the_message_arrived() -> None:
    checked = 0
    for case in build_cases(legacy=False):
        if case.id.startswith("visit-") and re.match(r"Ayer ", case.text):
            assert case.expected["fecha_visita"] == (TODAY - timedelta(days=1)).isoformat()
            checked += 1
        if "Vuelvo mañana" in case.text:
            assert case.expected["proxima_visita"] == (TODAY + timedelta(days=1)).isoformat()
            checked += 1
    assert checked >= 3


def test_the_set_includes_required_fields_left_unsaid() -> None:
    unsaid = [c for c in build_cases(legacy=False) if c.id.startswith("visit-") and c.expected["fecha_visita"] is None]
    assert unsaid, "without these the eval cannot catch an invented date"
    assert all(not re.search(r"\b(hoy|ayer|anteayer|de marzo)\b.*estuve", c.text, re.IGNORECASE) for c in unsaid)


def test_the_comparator_is_tolerant_of_wording_but_not_of_facts() -> None:
    assert values_match({"type": "str"}, "Ferretería García", "ferreteria garcia")
    assert values_match({"type": "str"}, "nuevo almacén", "el nuevo almacén")
    assert not values_match({"type": "str"}, "Talleres Ruiz", "Talleres Romero")
    assert values_match({"type": "phone"}, "612 345 678", "+34 612345678")
    assert not values_match({"type": "phone"}, "612 345 678", "612 345 679")
    assert values_match({"type": "float"}, 1.5, "1.5")
    assert values_match({"type": "list[str]"}, ["filtro F-200", "junta tórica"], ["Junta tórica", "filtro F-200"])
    assert not values_match({"type": "list[str]"}, ["filtro F-200"], ["filtro F-200", "junta tórica"])
    table = VISIT_SCHEMA["trabajos"]
    rows = [{"tarea": "cambiar el filtro", "horas": 0.5}, {"tarea": "revisar la caldera", "horas": 1.5}]
    assert values_match(table, rows, list(reversed(rows)))
    assert not values_match(table, rows, [{"tarea": "cambiar el filtro", "horas": 1.5}, rows[1]])
    assert not values_match({"type": "date"}, "2026-03-11", "2026-03-12")


def test_a_sentence_matches_on_its_key_terms_and_a_short_value_stays_strict() -> None:
    # Real answers from the first eval run, graded wrong by word-for-word comparison.
    assert values_match(
        {"type": "str"},
        "Se acordó revisar el contrato antes del 10 de abril.",
        "Reunión del 1 de abril con Diego y Marta, en la que se acordó revisar el contrato antes del 10 de abril.",
    )
    assert values_match({"type": "str"}, "Revisión de los KPIs del mes.", "Se revisaron los KPIs del mes.")
    assert not values_match({"type": "str"}, "Se acordó revisar el contrato antes del 10 de abril.", "Se habló del contrato.")
    assert not values_match({"type": "str"}, "la oficina de Valencia", "Valencia")
    assert not values_match({"type": "str"}, "Isabel Ortega", "Isabel Ortega (responsable de compras)")


def test_grading_tells_an_invented_value_from_a_missed_one() -> None:
    case = Case("c", "T", {"a": {"type": "str"}, "b": {"type": "date"}, "c": {"type": "str"}}, "", {"a": "x", "b": None, "c": "y"})

    verdicts = {o.field: o.verdict for o in grade(case, {"a": "x", "b": "2026-03-12", "c": None})}

    assert verdicts == {"a": "correct", "b": "invented", "c": "missed"}
