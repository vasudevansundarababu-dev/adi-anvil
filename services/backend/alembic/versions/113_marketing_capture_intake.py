from pathlib import Path

from alembic import op

revision = "113"
down_revision = "112"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/113_marketing_capture_intake.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable private native capture intake evidence")
