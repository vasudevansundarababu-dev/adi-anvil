from pathlib import Path

from alembic import op

revision = "100"
down_revision = "099"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/100_diagnostic_reference_custody.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve frozen reference identity and exact execution slots")
