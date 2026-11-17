from pathlib import Path

from alembic import op

revision = "125"
down_revision = "124"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/125_marketing_private_ordinal_context.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve original private native scoring authority")
