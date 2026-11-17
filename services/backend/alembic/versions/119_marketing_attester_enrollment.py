from pathlib import Path

from alembic import op

revision = "119"
down_revision = "118"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/119_marketing_attester_enrollment.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve original public-key enrollment custody")
