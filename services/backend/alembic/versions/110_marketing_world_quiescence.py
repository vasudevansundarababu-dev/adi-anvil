from pathlib import Path

from alembic import op

revision = "110"
down_revision = "109"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/110_marketing_world_quiescence.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable API fences and quiescence evidence")
