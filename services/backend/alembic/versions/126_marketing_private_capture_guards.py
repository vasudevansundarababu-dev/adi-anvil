from pathlib import Path

from alembic import op

revision = "126"
down_revision = "125"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/126_marketing_private_capture_guards.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve original physical acceptance guards")
