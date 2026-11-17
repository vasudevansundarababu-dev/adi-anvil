from pathlib import Path

from alembic import op

revision = "114"
down_revision = "113"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/114_marketing_opening_program.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable opening planning and effect evidence")
