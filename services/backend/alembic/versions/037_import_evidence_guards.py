from alembic import op

from anvil.config import ROOT

revision = "037"
down_revision = "036"


def upgrade():
    op.get_bind().exec_driver_sql(
        (ROOT / "services/backend/migrations/037_import_evidence_guards.sql").read_text(),
        execution_options={"no_parameters": True},
    )


def downgrade():
    raise RuntimeError("Forward-only import evidence migration")
