from alembic import op

from anvil.config import ROOT

revision = "033"
down_revision = "032"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/033_two_roles.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Use a forward migration; historical memberships must not be rewritten.")
