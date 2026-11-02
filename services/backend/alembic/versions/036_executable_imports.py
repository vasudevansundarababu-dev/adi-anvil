"""Description-first import generation and cumulative ledger."""

from alembic import op

from anvil.config import ROOT

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/036_executable_imports.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only evidence migration")
