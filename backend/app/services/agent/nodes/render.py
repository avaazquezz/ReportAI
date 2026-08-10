import asyncio

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.document_template import DocumentTemplate
from app.repositories.base import BaseRepository
from app.services.agent.state import AgentState
from app.services.observability.execution_log import observed_node
from app.services.rendering.docx_render import fill_template
from app.services.rendering.gotenberg_client import convert_docx_to_pdf


async def _load_active_template(document_type_id: object) -> DocumentTemplate:
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(DocumentTemplate, session)
        templates = await repo.list(
            filters={"document_type_id": document_type_id, "is_active": True}, limit=1
        )
        if not templates:
            raise ValueError(f"No active template for document_type {document_type_id}")
        return templates[0]


@observed_node("render")
async def render_node(state: AgentState) -> AgentState:
    assert state.extracted_fields is not None
    template = await _load_active_template(state.document_type_id)
    output_path = f"{settings.DOCUMENT_STORAGE_PATH}/{state.report_id}/rendered.docx"
    docx_path = await asyncio.to_thread(
        fill_template, template.file_path, state.extracted_fields, output_path
    )
    return state.model_copy(update={"rendered_docx_path": docx_path})


@observed_node("convert_pdf")
async def convert_pdf_node(state: AgentState) -> AgentState:
    assert state.rendered_docx_path is not None
    output_path = f"{settings.DOCUMENT_STORAGE_PATH}/{state.report_id}/rendered.pdf"
    pdf_path = await convert_docx_to_pdf(state.rendered_docx_path, output_path)
    return state.model_copy(update={"rendered_pdf_path": pdf_path})
