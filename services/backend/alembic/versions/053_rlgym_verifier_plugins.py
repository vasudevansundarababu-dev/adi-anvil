from alembic import op

from anvil.config import ROOT

revision = "053"
down_revision = "052"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/053_rlgym_verifier_plugins.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 verifier plug-ins")
