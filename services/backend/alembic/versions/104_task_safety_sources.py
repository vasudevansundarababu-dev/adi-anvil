from pathlib import Path

from alembic import op

revision = "104"
down_revision = "103"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/104_task_safety_sources.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable safety source qualification and revocation evidence")
