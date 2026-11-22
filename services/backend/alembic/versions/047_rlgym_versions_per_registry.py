from alembic import op

from anvil.config import ROOT

revision = "047"
down_revision = "046"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/047_rlgym_versions_per_registry.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 versions per registry")
