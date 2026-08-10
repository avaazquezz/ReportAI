from pathlib import Path

import httpx

from app.core.config import settings
from app.services.agent.tools.retry import retry_async

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def convert_docx_to_pdf(docx_path: str, output_path: str) -> str:
    async def _call() -> httpx.Response:
        async with httpx.AsyncClient(timeout=60) as client:
            with open(docx_path, "rb") as f:
                response = await client.post(
                    f"{settings.GOTENBERG_URL}/forms/libreoffice/convert",
                    files={"file": (Path(docx_path).name, f, _DOCX_MIME)},
                )
            response.raise_for_status()
            return response

    response = await retry_async(_call)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(response.content)
    return output_path
