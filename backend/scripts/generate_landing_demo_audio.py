"""One-off generator for the landing demo's input voice note, via OpenAI TTS —
replaces the earlier Higgsfield-generated audio (credit-constrained, out of scope
for a recurring tool). NOT wired into the Makefile.

Reads OPENAI_API_KEY from the environment directly (not app.core.config.settings —
this key belongs to this content-generation tool, not the production pipeline).

Usage (run inside the backend container, or anywhere with `openai` installed):
    OPENAI_API_KEY=sk-... python scripts/generate_landing_demo_audio.py [es|en]

Locale defaults to "es". Writes backend/scripts/_landing_demo_input.mp3 (es) or
_landing_demo_input_en.mp3 (en) — feed it to generate_landing_demo_asset.py next.
"""

import os
import sys
from pathlib import Path

from openai import OpenAI

ES_SCRIPT_TEXT = (
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

ES_INSTRUCTIONS = (
    "Warm, natural business voice, Spanish from Spain. Sounds like a real voice memo "
    "dictated right after leaving a client meeting, not a script being read aloud — "
    "conversational pace, slight informality, not overly polished."
)

EN_SCRIPT_TEXT = (
    "Hi, good afternoon, this is James Whitfield. Today, August eighteenth, I just "
    "wrapped up the meeting with Harbor Point Industrial Supply, at their offices in "
    "Savannah, Georgia. In attendance were Sarah Mitchell, VP of Procurement, Marcus "
    "Reed from the technical department, and Emily Chen, who handles logistics. We "
    "went over three items: first, the quarterly order, which is going up fifteen "
    "percent starting in October; second, extending the maintenance contract to two "
    "years; and third, changing the freight carrier for deliveries to the southern "
    "region. We agreed to accept the volume increase by cutting the delivery window "
    "down to two weeks, and to renew the maintenance contract on the current terms. "
    "As for next steps: I, James Whitfield, need to send the updated proposal to "
    "Sarah by Friday, August twenty-first; Marcus will confirm warehouse availability "
    "on Monday, August twenty-fourth; and Emily has to reach out to the new carrier "
    "before the end of the month. We're set to meet again on September fifteenth to "
    "close out the transport piece. Overall, a really good meeting."
)

EN_INSTRUCTIONS = (
    "Warm, natural business voice, American English. Sounds like a real voice memo "
    "dictated right after leaving a client meeting, not a script being read aloud — "
    "conversational pace, slight informality, not overly polished."
)


def main() -> None:
    locale = sys.argv[1] if len(sys.argv) > 1 else "es"
    if locale not in ("es", "en"):
        sys.exit(f"Unknown locale {locale!r}, expected 'es' or 'en'.")

    script_text, instructions = (EN_SCRIPT_TEXT, EN_INSTRUCTIONS) if locale == "en" else (ES_SCRIPT_TEXT, ES_INSTRUCTIONS)
    suffix = "_en" if locale == "en" else ""
    output_path = Path(__file__).parent / f"_landing_demo_input{suffix}.mp3"

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY is not set in the environment.")

    client = OpenAI(api_key=api_key)
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=script_text,
        instructions=instructions,
        response_format="mp3",
    ) as response:
        response.stream_to_file(output_path)

    print(f"Wrote {output_path} ({output_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
