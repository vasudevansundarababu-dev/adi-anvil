from pathlib import Path

from alembic import op

revision = "087"
down_revision = "086"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2]
            / "migrations/087_private_grading_reconciliation.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve terminal scoring custody and reconciliation evidence")
