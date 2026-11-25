from alembic import op

from anvil.config import ROOT

revision = "072"
down_revision = "071"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/072_rlgym_template_sop.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 template SOP")
