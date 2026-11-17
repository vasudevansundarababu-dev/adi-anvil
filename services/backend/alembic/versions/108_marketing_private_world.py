from pathlib import Path

from alembic import op

revision = "108"
down_revision = "107"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/108_marketing_private_world.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve private world source and qualification history")
