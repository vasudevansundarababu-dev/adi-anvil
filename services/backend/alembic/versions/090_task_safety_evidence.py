from pathlib import Path

from alembic import op

revision = "090"
down_revision = "089"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/090_task_safety_evidence.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve prompt versions and actual safety event evidence")
