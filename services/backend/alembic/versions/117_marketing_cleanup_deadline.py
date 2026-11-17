from pathlib import Path

from alembic import op

revision = "117"
down_revision = "116"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/117_marketing_cleanup_deadline.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve original cleanup identity and timing")
