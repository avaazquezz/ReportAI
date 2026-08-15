"""One-off generator for the landing page's real demo example — NOT a recurring
operational command, so it isn't wired into the Makefile.

Runs the real pipeline nodes directly (transcribe -> extract -> validate -> render ->
convert to PDF) against a real audio file, bypassing the DB entirely: node functions are
called via `.__wrapped__` (the raw function `observed_node` preserves via functools.wraps)
so no tenant/report/execution_log rows are needed. Reuses the same field schema and
auto-generated .docx template as the seeded demo tenant.

Usage (run inside the backend container so GROQ/ANTHROPIC keys and GOTENBERG_URL resolve):
    docker compose --project-directory . -f infra/docker-compose.yml exec backend \
        python scripts/generate_landing_demo_asset.py scripts/_landing_demo_input.mp3

Writes to backend/scripts/_landing_demo_output/: audio.mp3, transcript.txt, fields.json,
informe.pdf, meta.json (cost/latency) — copy the ones you want into frontend/public/demo/.
"""

import asyncio
import json
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.services.agent.nodes.extract import extract_node, validate_node
from app.services.agent.nodes.media import transcribe_node
from app.services.agent.state import AgentState
from app.services.rendering.docx_render import fill_template
from app.services.rendering.gotenberg_client import convert_docx_to_pdf
from scripts.seed_demo_tenant import FIELD_SCHEMA, _generate_template

OUTPUT_DIR = Path(__file__).parent / "_landing_demo_output"

PROMPT_INSTRUCTIONS = (
    "Extract meeting minutes fields from an internal company meeting transcript."
)


def _base_state(audio_path: Path) -> AgentState:
    return AgentState(
        thread_id="landing-demo",
        tenant_id=uuid.uuid4(),
        channel_connection_id=uuid.uuid4(),
        channel_type="landing_demo",
        sender_id="landing-demo",
        report_id=uuid.uuid4(),
        raw_payload={},
        media_local_path=str(audio_path),
        document_type_id=uuid.uuid4(),
        document_type_name="Meeting Minutes",
        field_schema=FIELD_SCHEMA,
        prompt_instructions=PROMPT_INSTRUCTIONS,
    )


async def generate(audio_path: Path) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    state = _base_state(audio_path)

    print("Transcribing (Groq Whisper, real call)...")
    # observed_node wraps with functools.wraps, which sets __wrapped__ to the raw node —
    # bypassing DB-backed execution logging, which this standalone script has no rows for.
    state = await transcribe_node.__wrapped__(state)  # type: ignore[attr-defined]
    assert state.transcript
    print(f"  -> {state.transcript}")

    print("Extracting fields (Claude, real call)...")
    state = await extract_node.__wrapped__(state)  # type: ignore[attr-defined]
    print(f"  -> {state.extracted_fields}")

    print("Validating against the field schema...")
    state = await validate_node.__wrapped__(state)  # type: ignore[attr-defined]
    if state.last_validation_error:
        sys.exit(f"Validation failed, fix the transcript or schema:\n{state.last_validation_error}")

    print("Rendering .docx from the auto-generated template...")
    template_path = OUTPUT_DIR / "template.docx"
    _generate_template(template_path)
    docx_path = OUTPUT_DIR / "informe.docx"
    await asyncio.to_thread(fill_template, str(template_path), state.extracted_fields, str(docx_path))

    print("Converting to PDF via Gotenberg...")
    pdf_path = OUTPUT_DIR / "informe.pdf"
    await convert_docx_to_pdf(str(docx_path), str(pdf_path))

    shutil.copy(audio_path, OUTPUT_DIR / "audio.mp3")
    (OUTPUT_DIR / "transcript.txt").write_text(state.transcript, encoding="utf-8")
    (OUTPUT_DIR / "fields.json").write_text(
        json.dumps(state.extracted_fields, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    usage = state.last_tool_usage
    meta = {
        "generated_at": datetime.now(UTC).isoformat(),
        "extraction_model": usage.model_used if usage else None,
        "extraction_cost_usd": usage.cost_usd if usage else None,
    }
    (OUTPUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\nDone. Artifacts in {OUTPUT_DIR}")
    print(f"Extraction cost: ${meta['extraction_cost_usd']:.6f}" if meta["extraction_cost_usd"] else "")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/generate_landing_demo_asset.py <path-to-audio-file>")
    asyncio.run(generate(Path(sys.argv[1])))
