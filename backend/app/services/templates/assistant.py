"""The template assistant: a company uploads a document it already fills in by hand, the model
proposes which parts of it change from one report to the next and what field each one is, the
admin corrects that in the panel, and the tagged template is built from their original file.

Each upload is a draft kept on disk (the original, and what was proposed for it) until it is
applied or it expires; nothing touches the document type before "apply"."""

import re
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypeVar

from docxtpl import DocxTemplate
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.schemas.document_type import ColumnSpec, ColumnType, FieldSchemaEntry
from app.services.branding import TEMPLATE_VARIABLE, Branding
from app.services.i18n import LANGUAGE_NAMES, normalize_language
from app.services.llm import structured_completion
from app.services.rendering.docx_render import fill_template
from app.services.templates.docx_tagging import (
    Block,
    TableShape,
    TagPlan,
    apply_plan,
    example_values,
    read_blocks,
)

DRAFT_TTL = timedelta(days=2)
_MAX_PROMPT_CHARS = 40_000
_TAG = re.compile(r"\{\{|\{%")

ProposedType = Literal[
    "str", "int", "float", "bool", "date", "time", "email", "phone", "list[str]", "list[int]", "enum", "list[object]"
]
_LIST_TYPES = ("list[str]", "list[int]")


class ProposedColumn(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,59}$")
    type: ColumnType = "str"
    description: str = ""


class ProposedField(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,59}$")
    label: str
    type: ProposedType
    description: str = ""
    required: bool = True
    options: list[str] | None = None
    columns: list[ProposedColumn] | None = None

    def spec(self) -> FieldSchemaEntry:
        return FieldSchemaEntry(
            type=self.type,
            description=self.description,
            required=self.required,
            label=self.label or None,
            options=self.options if self.type == "enum" else None,
            columns=(
                {c.name: ColumnSpec(type=c.type, description=c.description) for c in self.columns or []}
                if self.type == "list[object]"
                else None
            ),
        )


class ProposedValue(BaseModel):
    block_id: str
    text: str  # exactly as it appears in the block
    field: str


class ProposedCell(BaseModel):
    cell: int
    column: str


class ProposedTable(BaseModel):
    table_id: str
    first_row: int  # the first row with values (after the header)
    last_row: int
    cells: list[ProposedCell]
    field: str


class ProposedList(BaseModel):
    block_ids: list[str]  # consecutive paragraphs, one item each
    field: str


class Proposal(BaseModel):
    """Also the shape of what the panel sends back once the admin has corrected it."""

    fields: list[ProposedField] = []
    values: list[ProposedValue] = []
    tables: list[ProposedTable] = []
    lists: list[ProposedList] = []


class Draft(BaseModel):
    id: uuid.UUID
    document_type_id: uuid.UUID
    filename: str
    created_at: datetime
    already_tagged: bool  # the upload was a template already: nothing to propose
    proposal: Proposal
    blocks: dict[str, str]  # id → text, to show each value in its context
    tables: dict[str, list[list[str]]]


_Item = TypeVar("_Item", bound=BaseModel)


class PlanError(ValueError):
    """What was asked cannot make a working template; the message says what to fix."""


def _folder(tenant_id: uuid.UUID, draft_id: uuid.UUID) -> Path:
    return Path(settings.DOCUMENT_STORAGE_PATH) / "template_drafts" / str(tenant_id) / str(draft_id)


def original_path(tenant_id: uuid.UUID, draft_id: uuid.UUID) -> Path:
    return _folder(tenant_id, draft_id) / "original.docx"


def load_draft(tenant_id: uuid.UUID, draft_id: uuid.UUID) -> Draft | None:
    path = _folder(tenant_id, draft_id) / "draft.json"
    if not path.exists():
        return None
    return Draft.model_validate_json(path.read_text())


def drop_draft(tenant_id: uuid.UUID, draft_id: uuid.UUID) -> None:
    shutil.rmtree(_folder(tenant_id, draft_id), ignore_errors=True)


def drop_expired_drafts() -> int:
    """Uploads nobody applied: removed after DRAFT_TTL."""
    root = Path(settings.DOCUMENT_STORAGE_PATH) / "template_drafts"
    cutoff = (datetime.now(UTC) - DRAFT_TTL).timestamp()
    dropped = 0
    for folder in root.glob("*/*") if root.exists() else []:
        if folder.is_dir() and folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder, ignore_errors=True)
            dropped += 1
    return dropped


def _prompt(blocks: list[Block], tables: list[TableShape], language: str) -> str:
    lines = [f"[{b.id}] {b.text}" for b in blocks]
    for table in tables:
        lines.append(f"\nTable {table.id} ({len(table.rows)} rows):")
        lines.extend(f"  row {r}: " + " | ".join(cells) for r, cells in enumerate(table.rows))
    text = "\n".join(lines)
    if len(text) > _MAX_PROMPT_CHARS:
        text = text[:_MAX_PROMPT_CHARS] + "\n[… document truncated]"
    return (
        f"The document is written in {LANGUAGE_NAMES[normalize_language(language)]}. Its paragraphs, each "
        f"with its id, and its tables:\n\n{text}"
    )


_SYSTEM = """You turn a filled-in example of a company's document (a work report, an inspection, \
minutes…) into a template for reports dictated by voice.

Find every value that would change from one report to the next — names of clients, people and \
places, dates, times, quantities, prices, descriptions, observations, results — and NOT the fixed \
parts: titles, headings, labels such as "Client:", legal text, the company's own name and details.

Define one field per value: a snake_case name in the document's language (ASCII only, e.g. \
"fecha_visita"), a short label for people in the document's language, a type, a description that \
tells someone what to say for it, and whether a report needs it. Types: str, int, float, bool, \
date, time, email, phone, enum (with its options), list[str] for a bulleted or numbered list of \
items, list[object] for a table whose rows repeat (with its columns). Never use the name "branding".

Then say where each value is:
- values: the paragraph id and the text EXACTLY as it appears there (a part of the paragraph, \
without its label: "14/09/2026", not "Fecha: 14/09/2026");
- tables: for a table with several rows of the same kind (after a header row), the first and last \
of those rows, and which cell (0-based) holds which column; the field is a list[object];
- lists: the ids of consecutive paragraphs that are the items of one list; the field is a list[str].
A value in a table cell that is not part of repeated rows is an ordinary value."""


def _each(items: Any, model: type[_Item]) -> list[_Item]:
    parsed = []
    for item in items if isinstance(items, list) else []:
        try:
            parsed.append(model.model_validate(item))
        except ValidationError:
            continue
    return parsed


def _parse(raw: dict[str, Any]) -> Proposal:
    """The model's answer, item by item: one malformed field is dropped, not the whole proposal."""
    return Proposal(
        fields=_each(raw.get("fields"), ProposedField),
        values=_each(raw.get("values"), ProposedValue),
        tables=_each(raw.get("tables"), ProposedTable),
        lists=_each(raw.get("lists"), ProposedList),
    )


def _clean(proposal: Proposal, blocks: dict[str, str], tables: dict[str, list[list[str]]]) -> Proposal:
    """Keeps only what can actually be done: a value must be in its paragraph, a field must exist
    and fit how it is used. The model is good at this, not infallible."""
    fields: dict[str, ProposedField] = {}
    for f in proposal.fields:
        if f.name == TEMPLATE_VARIABLE or f.name in fields:
            continue
        try:
            f.spec()
        except ValidationError:
            continue
        fields[f.name] = f
    values = [
        v
        for v in proposal.values
        if v.field in fields and fields[v.field].type not in (*_LIST_TYPES, "list[object]") and v.text and v.text in blocks.get(v.block_id, "")
    ]
    table_list = [
        t
        for t in proposal.tables
        if t.field in fields
        and fields[t.field].type == "list[object]"
        and t.table_id in tables
        and 0 < t.first_row <= t.last_row < len(tables[t.table_id])
        and {c.column for c in t.cells} <= {c.name for c in fields[t.field].columns or []}
    ]
    lists = [lst for lst in proposal.lists if lst.field in fields and fields[lst.field].type in _LIST_TYPES and lst.block_ids and all(i in blocks for i in lst.block_ids)]
    used = {v.field for v in values} | {t.field for t in table_list} | {lst.field for lst in lists}
    return Proposal(fields=[f for f in fields.values() if f.name in used], values=values, tables=table_list, lists=lists)


_ROW_LOOP = re.compile(r"\{%\s*tr\s+for\s+(\w+)\s+in\s+(\w+)")
_LIST_LOOP = re.compile(r"\{%\s*p\s+for\s+\w+\s+in\s+(\w+)")


def _from_tags(path: str, texts: list[str]) -> Proposal:
    """A file that is a template already: its tags become the fields, and it is used as it is. A
    row loop is a table (its columns read off `item.column`), a paragraph loop a list."""
    text = "\n".join(texts)
    tables = {name: var for var, name in _ROW_LOOP.findall(text)}
    lists = set(_LIST_LOOP.findall(text))
    fields = []
    for name in sorted(DocxTemplate(path).get_undeclared_template_variables() - {TEMPLATE_VARIABLE}):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,59}", name):
            continue
        label = name.replace("_", " ").capitalize()
        if name in tables:
            columns = sorted(set(re.findall(rf"\b{tables[name]}\.(\w+)", text)))
            fields.append(ProposedField(name=name, label=label, type="list[object]", columns=[ProposedColumn(name=c) for c in columns]))
        elif name in lists:
            fields.append(ProposedField(name=name, label=label, type="list[str]"))
        else:
            fields.append(ProposedField(name=name, label=label, type="str"))
    return Proposal(fields=fields)


async def create_draft(
    *, tenant_id: uuid.UUID, document_type_id: uuid.UUID, filename: str, content: bytes, language: str
) -> Draft:
    draft_id = uuid.uuid4()
    folder = _folder(tenant_id, draft_id)
    folder.mkdir(parents=True, exist_ok=True)
    original = original_path(tenant_id, draft_id)
    original.write_bytes(content)
    try:
        blocks, tables = read_blocks(str(original))
    except Exception as exc:
        drop_draft(tenant_id, draft_id)
        raise PlanError("The file isn't a Word document (.docx) that can be read") from exc
    block_texts = {b.id: b.text for b in blocks}
    table_rows = {t.id: t.rows for t in tables}

    already_tagged = any(_TAG.search(b.text) for b in blocks)
    if already_tagged:
        proposal = _from_tags(str(original), [b.text for b in blocks])
    else:
        result = await structured_completion(
            system=_SYSTEM,
            user=_prompt(blocks, tables, language),
            model_cls=Proposal,
            tool_name="propose_template",
            max_tokens=16_000,
        )
        proposal = _clean(_parse(result.data), block_texts, table_rows)

    draft = Draft(
        id=draft_id,
        document_type_id=document_type_id,
        filename=filename,
        created_at=datetime.now(UTC),
        already_tagged=already_tagged,
        proposal=proposal,
        blocks=block_texts,
        tables=table_rows,
    )
    (folder / "draft.json").write_text(draft.model_dump_json())
    return draft


def _plan(draft: Draft, proposal: Proposal) -> TagPlan:
    """Checks the corrected proposal makes sense and turns it into what the Word editing needs."""
    fields = {f.name: f for f in proposal.fields}
    if len(fields) != len(proposal.fields):
        raise PlanError("Two fields have the same name")
    if TEMPLATE_VARIABLE in fields:
        raise PlanError("'branding' is reserved for the company's logo and name")
    for f in proposal.fields:
        try:
            f.spec()
        except ValidationError as exc:
            raise PlanError(f"Field {f.name}: {exc.errors()[0]['msg']}") from exc

    def expect(name: str, kinds: tuple[str, ...], where: str) -> None:
        if name not in fields:
            raise PlanError(f"{where} uses {name!r}, which is not one of the fields")
        if fields[name].type not in kinds:
            raise PlanError(f"{where} needs {name!r} to be of type {' or '.join(kinds)}")

    scalar = ("str", "int", "float", "bool", "date", "time", "email", "phone", "enum")
    for v in proposal.values:
        expect(v.field, scalar, f"«{v.text}»")
    for t in proposal.tables:
        expect(t.field, ("list[object]",), "A table")
        columns = {c.name for c in fields[t.field].columns or []}
        if not {c.column for c in t.cells} <= columns:
            raise PlanError(f"A table cell of {t.field!r} is not one of its columns")
    for lst in proposal.lists:
        expect(lst.field, _LIST_TYPES, "A list")
    return TagPlan(
        values=[(v.block_id, v.text, v.field) for v in proposal.values],
        tables=[(t.table_id, t.first_row, t.last_row, {c.cell: c.column for c in t.cells}, t.field) for t in proposal.tables],
        lists=[(lst.block_ids, lst.field) for lst in proposal.lists],
    )


def _labels(proposal: Proposal) -> dict[str, Any]:
    """Each field shows its own name in the preview: the clearest map of what goes where."""
    values: dict[str, Any] = {}
    for f in proposal.fields:
        if f.type == "list[object]":
            values[f.name] = [{c.name: f"«{c.name.replace('_', ' ')}»" for c in f.columns or []}]
        elif f.type in _LIST_TYPES:
            values[f.name] = [f"«{f.label}»"]
        else:
            values[f.name] = f"«{f.label}»"
    return values


def build_template(tenant_id: uuid.UUID, draft: Draft, proposal: Proposal, output: str) -> None:
    """Writes the tagged template, and proves it renders: a template that fails here would fail
    on the first report instead."""
    original = str(original_path(tenant_id, draft.id))
    if draft.already_tagged:
        shutil.copyfile(original, output)
    else:
        problems = apply_plan(original, _plan(draft, proposal), output)
        if problems:
            raise PlanError("; ".join(problems))
    used = DocxTemplate(output).get_undeclared_template_variables() - {TEMPLATE_VARIABLE}
    unknown = used - {f.name for f in proposal.fields}
    if unknown:
        raise PlanError(f"The template uses tags that are not fields: {', '.join(sorted(unknown))}")
    try:
        fill_template(output, _labels(proposal), str(Path(output).with_suffix(".check.docx")))
    except Exception as exc:
        raise PlanError(f"The template doesn't render: {exc}") from exc
    finally:
        Path(output).with_suffix(".check.docx").unlink(missing_ok=True)


def preview_docx(
    tenant_id: uuid.UUID,
    draft: Draft,
    proposal: Proposal,
    mode: Literal["labels", "example"],
    branding: Branding | None,
    folder: str,
) -> str:
    template = f"{folder}/template.docx"
    build_template(tenant_id, draft, proposal, template)
    values = (
        _labels(proposal)
        if mode == "labels" or draft.already_tagged
        else example_values(str(original_path(tenant_id, draft.id)), _plan(draft, proposal))
    )
    return fill_template(template, values, f"{folder}/preview.docx", branding=branding)


def merged_schema(existing: dict[str, Any], proposal: Proposal) -> dict[str, Any]:
    """The document type's fields after applying: its own first, then the template's — a field
    the admin edited in the assistant takes the assistant's definition."""
    schema = dict(existing)
    for f in proposal.fields:
        schema[f.name] = f.spec().model_dump(mode="json", exclude_none=True)
    return schema
