# Import every model so Base.metadata is fully populated for Alembic
# autogenerate diffing and for Base.metadata.create_all in tests.
from app.models.channel_connection import ChannelConnection  # noqa: F401
from app.models.document_template import DocumentTemplate  # noqa: F401
from app.models.document_type import DocumentType  # noqa: F401
from app.models.execution_log import ExecutionLog  # noqa: F401
from app.models.report import Report  # noqa: F401
from app.models.tenant import Tenant  # noqa: F401
from app.models.tenant_user import TenantUser  # noqa: F401
