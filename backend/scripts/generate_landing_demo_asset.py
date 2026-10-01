"""One-off generator for the landing page's demo example — NOT a recurring operational
command, so it isn't wired into the Makefile.

Runs the real pipeline steps (transcribe -> extract -> validate -> render -> convert to PDF)
on an audio file with the "safety_visit" starter template, bypassing the DB: the extraction
nodes are called via `.__wrapped__` (the raw function `observed_node` keeps through
functools.wraps) so no tenant/report/execution_log rows are needed. Uses the AI settings of
the environment (.env), like a fresh installation.

Usage (inside the backend container, so the AI keys and GOTENBERG_URL resolve):
    docker compose --project-directory . -f infra/docker-compose.yml exec backend \
        python scripts/generate_landing_demo_asset.py scripts/_landing_demo_input.mp3

Writes to backend/scripts/_landing_demo_output/ (or _landing_demo_output_en/ when the
input filename ends in "_en"): audio.mp3, transcript.txt, fields.json, informe.pdf,
meta.json (models/cost) — copy the ones you want into frontend/public/demo/.
"""

import asyncio
import json
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from app.services import transcription
from app.services.agent.nodes.extract import extract_node, validate_node
from app.services.agent.state import AgentState
from app.services.branding import Branding
from app.services.rendering.docx_render import fill_template
from app.services.rendering.gotenberg_client import convert_docx_to_pdf
from app.services.rendering.report_document import template_values
from app.services.templates import starters

STARTER = "safety_visit"
# The fictional coordinator's own firm: its name and logo head the report, as a client's would.
COMPANY = {"es": ("Prevención Levante", "PL"), "en": ("Northline Safety", "NS")}
COLOR = "#1F2A44"
# When the note is "sent": its "today" and "next Thursday" resolve against this.
SENT_AT = datetime(2026, 10, 1, 13, 40, tzinfo=ZoneInfo("Europe/Madrid"))


def _logo(initials: str, path: Path) -> None:
    image = Image.new("RGBA", (360, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 120, 120), radius=26, fill=COLOR)
    font = ImageFont.load_default(size=58)
    draw.text((60, 62), initials, font=font, fill="#FF6A45", anchor="mm")
    image.save(path)


async def generate(audio_path: Path) -> None:
    locale = "en" if audio_path.stem.endswith("_en") else "es"
    output_dir = Path(__file__).parent / ("_landing_demo_output_en" if locale == "en" else "_landing_demo_output")
    output_dir.mkdir(exist_ok=True)

    template_path = output_dir / "template.docx"
    schema = starters.build(STARTER, locale, str(template_path))
    starter = starters.STARTERS[STARTER]
    state = AgentState(
        thread_id="landing-demo",
        tenant_id=uuid.uuid4(),
        channel_connection_id=uuid.uuid4(),
        channel_type="landing_demo",
        sender_id="landing-demo",
        report_id=uuid.uuid4(),
        raw_payload={},
        language=locale,
        received_at=SENT_AT,
        document_type_id=uuid.uuid4(),
        document_type_name=starter.name[locale],
        field_schema=schema,
        prompt_instructions=starter.instructions[locale],
    )

    print("Transcribing (real call)...")
    transcript = await transcription.transcribe(audio_path.read_bytes(), audio_path.name, locale)
    print(f"  -> {transcript.text}")
    state = state.model_copy(update={"transcript": transcript.text, "source_text": transcript.text})

    print("Extracting fields (real call)...")
    state = await extract_node.__wrapped__(state)  # type: ignore[attr-defined]
    usage = state.last_tool_usage
    print(f"  -> {state.extracted_fields}")

    print("Validating against the field schema...")
    state = await validate_node.__wrapped__(state)  # type: ignore[attr-defined]
    if state.last_validation_error:
        sys.exit(f"Validation failed:\n{state.last_validation_error}")
    assert state.extracted_fields is not None

    print("Rendering the .docx and converting it to PDF...")
    name, initials = COMPANY[locale]
    logo = output_dir / "logo.png"
    _logo(initials, logo)
    docx_path = output_dir / "informe.docx"
    values = template_values(schema, state.extracted_fields, locale)
    await asyncio.to_thread(
        fill_template, str(template_path), values, str(docx_path), branding=Branding(name=name, color=COLOR, logo_path=str(logo))
    )
    await convert_docx_to_pdf(str(docx_path), str(output_dir / "informe.pdf"))

    shutil.copy(audio_path, output_dir / "audio.mp3")
    (output_dir / "transcript.txt").write_text(transcript.text, encoding="utf-8")
    (output_dir / "fields.json").write_text(json.dumps(state.extracted_fields, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = {
        "generated_at": datetime.now(UTC).isoformat(),
        "transcription_model": transcript.model,
        "extraction_model": usage.model_used if usage else None,
        "extraction_cost_usd": usage.cost_usd if usage else None,
    }
    (output_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nDone. Artifacts in {output_dir}\n{meta}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/generate_landing_demo_asset.py <path-to-audio-file>")
    asyncio.run(generate(Path(sys.argv[1])))
