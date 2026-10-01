from app.core.config import settings
from app.services.agent.state import AgentState
from app.services.observability.execution_log import observed_node
from app.services.rendering.gotenberg_client import convert_docx_to_pdf
from app.services.rendering.report_document import fill_report_docx


@observed_node("render")
async def render_node(state: AgentState) -> AgentState:
    assert state.extracted_fields is not None
    docx_path = await fill_report_docx(
        report_id=state.report_id,
        document_type_id=state.document_type_id,
        field_schema=state.field_schema or {},
        fields=state.extracted_fields,
        language=state.language,
        output_path=f"{settings.DOCUMENT_STORAGE_PATH}/{state.report_id}/rendered.docx",
    )
    return state.model_copy(update={"rendered_docx_path": docx_path})


@observed_node("convert_pdf")
async def convert_pdf_node(state: AgentState) -> AgentState:
    assert state.rendered_docx_path is not None
    output_path = f"{settings.DOCUMENT_STORAGE_PATH}/{state.report_id}/rendered.pdf"
    pdf_path = await convert_docx_to_pdf(state.rendered_docx_path, output_path)
    return state.model_copy(update={"rendered_pdf_path": pdf_path})
