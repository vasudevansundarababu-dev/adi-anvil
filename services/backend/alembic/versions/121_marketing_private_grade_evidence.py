from pathlib import Path

from alembic import op

revision = "121"
down_revision = "120"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/121_marketing_private_grade_evidence.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve exact private grade evidence provenance")
