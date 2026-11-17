from pathlib import Path

from alembic import op

revision = "122"
down_revision = "121"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/122_marketing_private_actor_custody.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve exact original actor artifact custody")
