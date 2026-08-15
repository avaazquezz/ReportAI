"""One-off generator for the landing demo's input voice note, via OpenAI TTS —
replaces the earlier Higgsfield-generated audio (credit-constrained, out of scope
for a recurring tool). NOT wired into the Makefile.

Reads OPENAI_API_KEY from the environment directly (not app.core.config.settings —
this key belongs to this content-generation tool, not the production pipeline).

Usage (run inside the backend container, or anywhere with `openai` installed):
    OPENAI_API_KEY=sk-... python scripts/generate_landing_demo_audio.py

Writes backend/scripts/_landing_demo_input.mp3 — feed it to
generate_landing_demo_asset.py next.
"""

import os
import sys
from pathlib import Path

from openai import OpenAI

OUTPUT_PATH = Path(__file__).parent / "_landing_demo_input.mp3"

SCRIPT_TEXT = (
    "Hola, buenas tardes, soy Javier Molina. Hoy dieciocho de agosto acabo de terminar "
    "la reunión con Construcciones Marítimas del Levante, en sus oficinas de Alicante. "
    "Han asistido Marta Delgado, la directora de compras, Óscar Ferreira, del "
    "departamento técnico, y Laura Sanz, responsable de logística. Hemos repasado tres "
    "puntos: primero, el pedido trimestral, que sube un quince por ciento a partir de "
    "octubre; segundo, la ampliación del contrato de mantenimiento a dos años; y "
    "tercero, el cambio de proveedor de transporte para las entregas del sur. Se ha "
    "decidido aceptar el incremento de volumen reduciendo el plazo de entrega a dos "
    "semanas, y renovar el contrato de mantenimiento con las condiciones actuales. Como "
    "acciones: yo, Javier Molina, debo enviar la propuesta actualizada a Marta antes "
    "del viernes veintiuno de agosto; Óscar confirmará la disponibilidad de almacén el "
    "lunes veinticuatro de agosto; y Laura tiene que contactar con el nuevo "
    "transportista antes de fin de mes. Quedamos en vernos otra vez el quince de "
    "septiembre para cerrar el tema del transporte. En general, muy buena reunión."
)

INSTRUCTIONS = (
    "Warm, natural business voice, Spanish from Spain. Sounds like a real voice memo "
    "dictated right after leaving a client meeting, not a script being read aloud — "
    "conversational pace, slight informality, not overly polished."
)


def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY is not set in the environment.")

    client = OpenAI(api_key=api_key)
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=SCRIPT_TEXT,
        instructions=INSTRUCTIONS,
        response_format="mp3",
    ) as response:
        response.stream_to_file(OUTPUT_PATH)

    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
