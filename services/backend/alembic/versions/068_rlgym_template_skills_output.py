from alembic import op

from anvil.config import ROOT

revision = "068"
down_revision = "067"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/068_rlgym_template_skills_output.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only RL Gym v2 template output schema and skills (KYC Judgment C4)")
