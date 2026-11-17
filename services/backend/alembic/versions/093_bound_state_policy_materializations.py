from pathlib import Path

from alembic import op

revision = "093"
down_revision = "092"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2]
            / "migrations/093_bound_state_policy_materializations.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve exact policy source and review provenance")
