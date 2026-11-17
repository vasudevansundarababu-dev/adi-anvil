from pathlib import Path

from alembic import op

revision = "089"
down_revision = "088"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/089_governed_ai_runtime.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve governed AI dispatch and qualification custody")
