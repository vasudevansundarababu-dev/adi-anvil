from pathlib import Path

from alembic import op

revision = "095"
down_revision = "094"


def upgrade():
    op.get_bind().exec_driver_sql(
        (
            Path(__file__).resolve().parents[2] / "migrations/095_marketing_workflow_effects.sql"
        ).read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Preserve ambiguous and completed Marketing effect custody")
