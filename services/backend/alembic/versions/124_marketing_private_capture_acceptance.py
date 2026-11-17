from pathlib import Path

from alembic import op

revision = "124"
down_revision = "123"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/124_marketing_private_capture_acceptance.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve original native capture acceptance evidence")
