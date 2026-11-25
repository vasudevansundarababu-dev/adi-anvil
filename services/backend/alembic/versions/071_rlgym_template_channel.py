from alembic import op

from anvil.config import ROOT

revision = "071"
down_revision = "070"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/071_rlgym_template_channel.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 template activation channel")
