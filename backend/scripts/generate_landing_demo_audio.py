"""One-off generator for the landing demo's input voice note — a site safety inspection
dictated by a (synthetic, OpenAI TTS) voice; the landing says so. NOT wired into the Makefile.

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
    "Hola, soy Lucía Ferrer. Acabo de salir de la visita de coordinación en la obra "
    "Residencial Las Acacias, en la calle Mayor catorce de Paterna; el promotor es "
    "Inmobiliaria Mediterránea. Hoy es jueves, uno de octubre. La obra está en estructura, "
    "con el forjado de la planta tercera. Estaban trabajando Construcciones Albufera, "
    "que es la contrata principal, Estructuras Levante con el encofrado, Montajes Soler "
    "con el andamio y Grúas Martínez con la grúa torre. He visto tres cosas. Primero, en "
    "el forjado de tercera falta la barandilla del borde norte, unos diez metros: es de "
    "Estructuras Levante y la tienen que poner antes de seguir trabajando en esa zona, o "
    "sea, inmediato. Segundo, dos operarios de Montajes Soler estaban sin casco debajo de "
    "la grúa; se ha corregido en el momento, pero lo dejo anotado. Y tercero, el cuadro "
    "eléctrico de obra tiene la puerta rota y no cierra; eso es de Construcciones "
    "Albufera y hay que cambiarlo antes del viernes nueve. He paralizado los trabajos en "
    "el borde norte hasta que pongan la barandilla, y lo he anotado en el libro de "
    "incidencias. Por lo demás, orden y limpieza bien y los accesos señalizados. La "
    "próxima visita, el jueves ocho de octubre."
)

ES_INSTRUCTIONS = (
    "Natural female voice, Spanish from Spain. A construction health and safety coordinator "
    "dictating a voice memo right after leaving a building site: conversational pace, "
    "slight informality, confident, not a script being read aloud."
)

EN_SCRIPT_TEXT = (
    "Hi, this is Dana Brooks. I just finished the safety inspection at Maple Ridge "
    "Apartments, phase two, 140 Oak Street in Riverside; the client is Northgate "
    "Developments. Today is Thursday, October first. The job is at the structure stage, "
    "they're forming the third-floor deck. On site were Harbor Build, the general "
    "contractor, Summit Concrete doing the formwork, Iron Line Rebar on the rebar, and "
    "Apex Crane running the tower crane. I found three issues. First, the edge protection "
    "is missing on the north side of the third-floor deck, about thirty feet. That's "
    "Summit Concrete, and it has to go up before anyone works in that area, so "
    "immediately. Second, two Iron Line workers had no hard hats under the crane; that was "
    "fixed on the spot, but I'm logging it. Third, the site electrical panel has a broken "
    "door that won't close; that's on Harbor Build, and it needs replacing by Friday the "
    "ninth. I stopped work on the north edge until the guardrail is in, and I recorded it "
    "in the site log. Otherwise, housekeeping is good and access routes are signed. Next "
    "inspection is Thursday, October eighth."
)

EN_INSTRUCTIONS = (
    "Natural female voice, American English. A construction site safety inspector "
    "dictating a voice memo right after leaving a building site: conversational pace, "
    "slight informality, confident, not a script being read aloud."
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
        voice="coral",
        input=script_text,
        instructions=instructions,
        response_format="mp3",
    ) as response:
        response.stream_to_file(output_path)

    print(f"Wrote {output_path} ({output_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
