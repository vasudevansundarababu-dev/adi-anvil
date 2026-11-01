from alembic import op

from anvil.config import ROOT

revision = "034"
down_revision = "033"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/034_admin_run_authority.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; run authorization is immutable audit evidence.")
