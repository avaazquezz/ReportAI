"""The golden set, generated instead of hand-written: every message is assembled from the values it
must yield, so the ground truth is known by construction and the set can be as large as needed.

Each case also leaves fields out on purpose. A field the message never mentions must come back
null — a value there is an invented one (IA-9), which is what this set exists to catch.

Synthetic data only, never real client data (project-wide decision, see PROJECT_ROADMAP.md).
"""

import json
import random
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Every message "arrives" at this moment, so "ayer" or "tomorrow" have one right answer.
RECEIVED_AT = datetime(2026, 3, 12, 10, 15, tzinfo=ZoneInfo("Europe/Madrid"))  # a Thursday
TODAY = RECEIVED_AT.date()
SEED = 20260312

_LEGACY_DIR = Path(__file__).parent / "golden_set"


@dataclass(frozen=True)
class Case:
    id: str
    document_type_name: str
    field_schema: dict[str, Any]
    text: str
    expected: dict[str, Any]
    language: str = "es"
    prompt_instructions: str | None = None
    received_at: datetime | None = RECEIVED_AT


@dataclass
class FieldOutcome:
    case_id: str
    field: str
    type: str
    verdict: str  # correct | wrong | missed | invented
    expected: Any = None
    actual: Any = None


@dataclass
class Report:
    outcomes: list[FieldOutcome] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # case id -> why it produced nothing

    def count(self, verdict: str) -> int:
        return sum(1 for outcome in self.outcomes if outcome.verdict == verdict)

    @property
    def accuracy(self) -> float:
        return self.count("correct") / len(self.outcomes) if self.outcomes else 0.0

    def breakdown(self, key: str) -> dict[str, dict[str, int]]:
        table: dict[str, dict[str, int]] = {}
        for outcome in self.outcomes:
            row = table.setdefault(getattr(outcome, key), {"correct": 0, "wrong": 0, "missed": 0, "invented": 0})
            row[outcome.verdict] += 1
        return table

    def render(self) -> str:
        lines = [
            (
                f"Golden set: {len({o.case_id for o in self.outcomes})} cases, {len(self.outcomes)} fields, "
                f"accuracy {self.accuracy:.1%} — wrong {self.count('wrong')}, missed {self.count('missed')}, "
                f"invented {self.count('invented')}, cases that failed outright {len(self.errors)}"
            ),
        ]
        for key in ("type", "field"):
            lines.append(f"\nBy {key}:")
            for name, row in sorted(self.breakdown(key).items()):
                total = sum(row.values())
                lines.append(
                    f"  {name:<22} {row['correct'] / total:6.1%}  ({row['correct']}/{total}; "
                    f"wrong {row['wrong']}, missed {row['missed']}, invented {row['invented']})"
                )
        problems = [o for o in self.outcomes if o.verdict != "correct"]
        if problems:
            lines.append("\nMisses:")
            for o in problems:
                lines.append(f"  [{o.verdict}] {o.case_id}.{o.field}: expected {o.expected!r}, got {o.actual!r}")
        for case_id, error in self.errors.items():
            lines.append(f"  [error] {case_id}: {error}")
        return "\n".join(lines)


# ── comparing ────────────────────────────────────────────────────────────────────────────────


def _norm(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def _stems(text: str) -> set[str]:
    return {word[:5] for word in _norm(text).split() if len(word) >= 4}


def _text_matches(expected: str, actual: str) -> bool:
    """Names and short phrases: the same words, give or take an article or a typo. A sentence (a
    summary, the next steps) is said in many ways: it matches when its key terms are there."""
    a, b = _norm(expected), _norm(actual)
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    if shorter and shorter in longer and len(shorter) / len(longer) >= 0.5:
        return True
    if SequenceMatcher(None, a, b).ratio() >= 0.85:
        return True
    terms = _stems(expected)
    return len(a.split()) >= 4 and bool(terms) and len(terms & _stems(actual)) / len(terms) >= 0.75


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def values_match(spec: dict[str, Any], expected: Any, actual: Any) -> bool:
    kind = spec.get("type")
    if kind in ("int", "float"):
        try:
            return abs(float(expected) - float(actual)) <= 0.01
        except (TypeError, ValueError):
            return False
    if kind == "phone":
        want, got = re.sub(r"\D", "", str(expected)), re.sub(r"\D", "", str(actual))
        return len(got) >= 9 and (got.endswith(want) or want.endswith(got))
    if kind == "email":
        return str(actual).strip().lower() == str(expected).lower()
    if kind in ("str",):
        return isinstance(actual, str) and _text_matches(expected, actual)
    if kind in ("list[str]", "list[int]"):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return False
        item = {"type": "str" if kind == "list[str]" else "int"}
        remaining = list(actual)
        for want in expected:
            hit = next((got for got in remaining if values_match(item, want, got)), None)
            if hit is None:
                return False
            remaining.remove(hit)
        return True
    if kind == "list[object]":
        if not isinstance(actual, list) or len(actual) != len(expected):
            return False
        columns = spec.get("columns") or {}
        remaining = [row for row in actual if isinstance(row, dict)]
        for want in expected:
            hit = next(
                (
                    row
                    for row in remaining
                    if all(values_match(columns[name], cell, row.get(name)) for name, cell in want.items())
                ),
                None,
            )
            if hit is None:
                return False
            remaining.remove(hit)
        return True
    return bool(expected == actual)  # date, time, enum, bool: one right answer


def grade(case: Case, actual: dict[str, Any]) -> list[FieldOutcome]:
    outcomes = []
    for name, spec in case.field_schema.items():
        if spec.get("type") == "image":
            continue
        want, got = case.expected.get(name), actual.get(name)
        if _is_empty(want):
            verdict = "correct" if _is_empty(got) else "invented"
        elif _is_empty(got):
            verdict = "missed"
        else:
            verdict = "correct" if values_match(spec, want, got) else "wrong"
        outcomes.append(FieldOutcome(case.id, name, str(spec.get("type")), verdict, want, got))
    return outcomes


# ── generating ───────────────────────────────────────────────────────────────────────────────

_CLIENTS = [
    "Ferretería García", "Construcciones Pérez", "Talleres Ruiz", "Hotel Miramar", "Colegio San José",
    "Panadería La Espiga", "Clínica Dental Sonrisa", "Bodegas Altamira", "Gimnasio Atlas", "Restaurante El Puerto",
]
_PEOPLE = ["Ana López", "Javier Martín", "Lucía Fernández", "Pedro Sánchez", "Marta Gil", "Carlos Romero", "Elena Torres"]
_MATERIALS = ["filtro F-200", "junta tórica", "termostato digital", "válvula de tres vías", "manguito de cobre", "sellador de silicona"]
_TASKS = ["revisar la caldera", "cambiar el filtro", "purgar los radiadores", "ajustar la presión", "limpiar el quemador"]
_TOPICS = ["presupuesto de 2026", "nuevo almacén", "vacaciones de verano", "plan de formación", "renovación de la flota"]
_PLACES = ["warehouse B", "loading dock", "main office", "parking lot", "assembly line 2"]
_WITNESSES = ["John Carter", "Emily Stone", "Raj Patel", "Sofia Rossi", "Liam Walsh"]

_HOURS_WORDS = {0.5: "media hora", 1.0: "una hora", 1.5: "hora y media", 2.0: "dos horas", 2.5: "dos horas y media"}
_SPANISH_TIMES = {"09:30": "a las nueve y media", "08:00": "a las ocho", "16:45": "a las cinco menos cuarto de la tarde", "11:15": "a las once y cuarto"}
_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _spanish_day(rng: random.Random, day: date) -> str:
    """How someone says a past or present day: relative when it can be, otherwise the date."""
    delta = (TODAY - day).days
    relative = {0: "hoy", 1: "ayer", 2: "anteayer"}
    if delta in relative and rng.random() < 0.7:
        return relative[delta]
    return f"el {day.day} de {_MONTHS[day.month - 1]}"


def _join(items: list[str], conjunction: str = "y") -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {conjunction} {items[-1]}"


VISIT_SCHEMA: dict[str, Any] = {
    "cliente": {"type": "str", "description": "Nombre del cliente visitado", "required": True},
    "fecha_visita": {"type": "date", "description": "Día de la visita", "required": True},
    "tipo_visita": {"type": "enum", "options": ["inspección", "mantenimiento", "avería"], "required": True,
                    "description": "Motivo de la visita"},
    "hora_inicio": {"type": "time", "description": "Hora a la que empezó", "required": False},
    "trabajos": {"type": "list[object]", "required": False, "description": "Trabajos hechos y horas de cada uno",
                 "columns": {"tarea": {"type": "str", "description": "Tarea"}, "horas": {"type": "float", "description": "Horas"}}},
    "materiales": {"type": "list[str]", "description": "Materiales usados", "required": False},
    "urgente": {"type": "bool", "description": "Si el cliente lo marcó como urgente", "required": False},
    "telefono_contacto": {"type": "phone", "description": "Teléfono de contacto del cliente", "required": False},
    "email_contacto": {"type": "email", "description": "Email de contacto del cliente", "required": False},
    "proxima_visita": {"type": "date", "description": "Día de la próxima visita acordada", "required": False},
    "fotos": {"type": "image", "multiple": True, "required": False},
}

_VISIT_TYPE_PHRASES = {
    "inspección": ["para la inspección anual", "a hacer una inspección"],
    "mantenimiento": ["para el mantenimiento", "a hacer el mantenimiento preventivo"],
    "avería": ["por una avería", "porque tenían una avería"],
}


def _visit_case(rng: random.Random, index: int) -> Case:
    expected: dict[str, Any] = dict.fromkeys(VISIT_SCHEMA)
    expected.pop("fotos")
    client = rng.choice(_CLIENTS)
    expected["cliente"] = client
    parts = []

    # Leaving out a required field on purpose: the model must return null, not today's date.
    say_date = rng.random() > 0.12
    say_type = rng.random() > 0.12
    day = TODAY - timedelta(days=rng.choice([0, 0, 1, 1, 2, 5, 9]))
    visit_type = rng.choice(list(_VISIT_TYPE_PHRASES))
    when = _spanish_day(rng, day) if say_date else ""
    reason = rng.choice(_VISIT_TYPE_PHRASES[visit_type]) if say_type else ""
    parts.append(f"{when.capitalize() + ' e' if when else 'E'}stuve en {client} {reason}".strip() + ".")
    if say_date:
        expected["fecha_visita"] = day.isoformat()
    if say_type:
        expected["tipo_visita"] = visit_type

    if rng.random() < 0.6:
        start = rng.choice(list(_SPANISH_TIMES))
        spoken = _SPANISH_TIMES[start] if rng.random() < 0.6 else f"a las {start}"
        parts.append(f"Empecé {spoken}.")
        expected["hora_inicio"] = start
    if rng.random() < 0.7:
        tasks = rng.sample(_TASKS, rng.choice([1, 2, 2, 3]))
        rows = [{"tarea": task, "horas": rng.choice(list(_HOURS_WORDS))} for task in tasks]
        said = [f"{row['tarea']} ({_HOURS_WORDS[row['horas']]})" for row in rows]
        parts.append(f"Lo que hice: {_join(said)}.")
        expected["trabajos"] = rows
    if rng.random() < 0.6:
        materials = rng.sample(_MATERIALS, rng.choice([1, 2, 3]))
        parts.append(f"Usé {_join(materials)}.")
        expected["materiales"] = materials
    urgency = rng.random()
    if urgency < 0.25:
        parts.append("Me dijeron que es urgente.")
        expected["urgente"] = True
    elif urgency < 0.45:
        parts.append("No es urgente, puede esperar.")
        expected["urgente"] = False
    if rng.random() < 0.4:
        phone = f"6{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}"
        parts.append(f"El teléfono de contacto es el {phone}.")
        expected["telefono_contacto"] = phone
    if rng.random() < 0.3:
        email = f"{rng.choice(['compras', 'info', 'mantenimiento'])}@{_norm(client).replace(' ', '')}.es"
        parts.append(f"Su email es {email}.")
        expected["email_contacto"] = email
    if rng.random() < 0.4:
        offset = rng.choice([1, 2, 8])
        spoken = {1: "mañana", 2: "pasado mañana"}.get(offset) or f"el {(TODAY + timedelta(days=offset)).day} de marzo"
        parts.append(f"Vuelvo {spoken} a terminar.")
        expected["proxima_visita"] = (TODAY + timedelta(days=offset)).isoformat()

    head, rest = parts[0], parts[1:]
    rng.shuffle(rest)
    return Case(f"visit-{index:02d}", "Parte de visita técnica", VISIT_SCHEMA, " ".join([head, *rest]), expected)


MEETING_SCHEMA: dict[str, Any] = {
    "fecha": {"type": "date", "description": "Día de la reunión", "required": True},
    "asistentes": {"type": "list[str]", "description": "Nombres de quienes asistieron", "required": True},
    "temas": {"type": "list[str]", "description": "Temas tratados", "required": False},
    "acuerdos": {"type": "list[object]", "required": False, "description": "Tareas acordadas",
                 "columns": {"responsable": {"type": "str", "description": "Quién"},
                             "accion": {"type": "str", "description": "Qué"},
                             "fecha_limite": {"type": "date", "description": "Para cuándo"}}},
    "proxima_reunion": {"type": "date", "description": "Día de la próxima reunión", "required": False},
    "lugar": {"type": "str", "description": "Dónde fue la reunión", "required": False},
}
_ACTIONS = ["preparar el presupuesto", "llamar al proveedor", "revisar el contrato", "enviar el informe", "organizar la formación"]


def _meeting_case(rng: random.Random, index: int) -> Case:
    expected: dict[str, Any] = dict.fromkeys(MEETING_SCHEMA)
    people = rng.sample(_PEOPLE, rng.choice([2, 3, 4]))
    expected["asistentes"] = people
    say_date = rng.random() > 0.12
    day = TODAY - timedelta(days=rng.choice([0, 1, 3]))
    when = _spanish_day(rng, day) if say_date else ""
    parts = [f"Reunión {when + ' ' if when else ''}con {_join(people)}."]
    if say_date:
        expected["fecha"] = day.isoformat()
    if rng.random() < 0.7:
        topics = rng.sample(_TOPICS, rng.choice([1, 2]))
        parts.append(f"Hablamos del {_join(topics, 'y del')}.")
        expected["temas"] = topics
    if rng.random() < 0.7:
        rows = []
        for person in rng.sample(people, rng.choice([1, 2])):
            deadline = TODAY + timedelta(days=rng.choice([1, 6, 18]))
            rows.append({"responsable": person, "accion": rng.choice(_ACTIONS), "fecha_limite": deadline.isoformat()})
        said = [
            f"{row['responsable']} se encarga de {row['accion']} antes del {date.fromisoformat(row['fecha_limite']).day} de "
            f"{_MONTHS[date.fromisoformat(row['fecha_limite']).month - 1]}"
            for row in rows
        ]
        parts.append(f"Acordamos que {_join(said)}.")
        expected["acuerdos"] = rows
    if rng.random() < 0.4:
        nxt = TODAY + timedelta(days=rng.choice([7, 14]))
        parts.append(f"Nos volvemos a reunir el {nxt.day} de {_MONTHS[nxt.month - 1]}.")
        expected["proxima_reunion"] = nxt.isoformat()
    if rng.random() < 0.4:
        place = rng.choice(["la sala de juntas", "la oficina de Valencia", "la nave 3"])
        parts.append(f"Fue en {place}.")
        expected["lugar"] = place
    return Case(f"meeting-{index:02d}", "Acta de reunión", MEETING_SCHEMA, " ".join(parts), expected)


INCIDENT_SCHEMA: dict[str, Any] = {
    "date": {"type": "date", "description": "Day of the incident", "required": True},
    "time": {"type": "time", "description": "Time of the incident", "required": True},
    "location": {"type": "str", "description": "Where it happened", "required": True},
    "severity": {"type": "enum", "options": ["low", "medium", "high"], "description": "How serious it was", "required": True},
    "injured": {"type": "bool", "description": "Whether anyone was hurt", "required": True},
    "witnesses": {"type": "list[str]", "description": "Names of witnesses", "required": False},
    "reporter_phone": {"type": "phone", "description": "Phone number of the person reporting", "required": False},
}
_SEVERITY_PHRASES = {"low": "It was minor.", "medium": "It was moderately serious.", "high": "It was very serious."}


def _incident_case(rng: random.Random, index: int) -> Case:
    expected: dict[str, Any] = dict.fromkeys(INCIDENT_SCHEMA)
    day = TODAY - timedelta(days=rng.choice([0, 1]))
    place = rng.choice(_PLACES)
    hour, minute = rng.choice([(7, 40), (13, 5), (18, 30), (22, 15)])
    when = {0: "today", 1: "yesterday"}[(TODAY - day).days]
    parts = [f"Incident {when} at {hour % 12 or 12}:{minute:02d} {'am' if hour < 12 else 'pm'} in the {place}."]
    expected.update(date=day.isoformat(), time=f"{hour:02d}:{minute:02d}", location=place)
    if rng.random() > 0.15:
        severity = rng.choice(list(_SEVERITY_PHRASES))
        parts.append(_SEVERITY_PHRASES[severity])
        expected["severity"] = severity
    if rng.random() > 0.15:
        injured = rng.random() < 0.4
        parts.append("One worker was hurt." if injured else "Nobody was injured.")
        expected["injured"] = injured
    if rng.random() < 0.5:
        witnesses = rng.sample(_WITNESSES, rng.choice([1, 2]))
        parts.append(f"{_join(witnesses, 'and')} saw it.")
        expected["witnesses"] = witnesses
    if rng.random() < 0.3:
        phone = f"+44 7{rng.randint(100, 999)} {rng.randint(100000, 999999)}"
        parts.append(f"Call me back on {phone}.")
        expected["reporter_phone"] = phone
    return Case(f"incident-{index:02d}", "Incident report", INCIDENT_SCHEMA, " ".join(parts), expected, language="en")


def _legacy_cases() -> list[Case]:
    """The hand-written cases from before the generator; their dates are absolute."""
    cases = []
    for path in sorted(_LEGACY_DIR.glob("*.json")):
        raw = json.loads(path.read_text())
        cases.append(
            Case(
                id=f"legacy-{path.stem}",
                document_type_name=raw["document_type_name"],
                field_schema=raw["field_schema"],
                text=raw["input_text"],
                expected=raw["expected_fields"],
                prompt_instructions=raw.get("prompt_instructions"),
                received_at=None,
            )
        )
    return cases


def build_cases(visits: int = 35, meetings: int = 20, incidents: int = 20, legacy: bool = True) -> list[Case]:
    rng = random.Random(SEED)
    cases = [_visit_case(rng, i) for i in range(visits)]
    cases += [_meeting_case(rng, i) for i in range(meetings)]
    cases += [_incident_case(rng, i) for i in range(incidents)]
    return cases + (_legacy_cases() if legacy else [])
