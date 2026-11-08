"""uq_reports_one_active_per_sender leaves out the web app: a technician may keep several drafts open

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-07

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = "status IN ('pending', 'awaiting_doctype_selection', 'awaiting_details', 'awaiting_approval')"
_COLUMNS = ["tenant_id", "requester_channel", "requester_identifier"]


def upgrade() -> None:
    op.drop_index("uq_reports_one_active_per_sender", table_name="reports")
    op.create_index(
        "uq_reports_one_active_per_sender", "reports", _COLUMNS, unique=True,
        postgresql_where=sa.text(f"{_ACTIVE} AND requester_channel <> 'web'"),
    )


def downgrade() -> None:
    # Fails while a technician has two web drafts open: finish or cancel them first.
    op.drop_index("uq_reports_one_active_per_sender", table_name="reports")
    op.create_index("uq_reports_one_active_per_sender", "reports", _COLUMNS, unique=True, postgresql_where=sa.text(_ACTIVE))
