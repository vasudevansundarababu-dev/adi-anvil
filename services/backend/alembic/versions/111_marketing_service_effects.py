from pathlib import Path

from alembic import op

revision = "111"
down_revision = "110"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/111_marketing_service_effects.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable private service effect evidence")
