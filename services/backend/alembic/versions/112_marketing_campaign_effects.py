from pathlib import Path

from alembic import op

revision = "112"
down_revision = "111"


def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2] / "migrations/112_marketing_campaign_effects.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve immutable private campaign transition evidence")
