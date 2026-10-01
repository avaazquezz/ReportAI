"""document_types.field_schema as json: keep fields in the order they were defined

JSONB stores object keys sorted (shortest first), so a schema came back in a different order from
the one its author wrote. Existing rows keep JSONB's order until they are saved again.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-01

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_types ALTER COLUMN field_schema DROP DEFAULT")
    op.execute("ALTER TABLE document_types ALTER COLUMN field_schema TYPE json USING field_schema::json")
    op.execute("ALTER TABLE document_types ALTER COLUMN field_schema SET DEFAULT '{}'::json")


def downgrade() -> None:
    op.execute("ALTER TABLE document_types ALTER COLUMN field_schema DROP DEFAULT")
    op.execute("ALTER TABLE document_types ALTER COLUMN field_schema TYPE jsonb USING field_schema::jsonb")
    op.execute("ALTER TABLE document_types ALTER COLUMN field_schema SET DEFAULT '{}'::jsonb")
