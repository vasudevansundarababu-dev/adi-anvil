from pathlib import Path

from alembic import op

revision = "082"
down_revision = "081"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/082_marketing_task2_runtime.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Retain immutable Marketing runtime evidence")
