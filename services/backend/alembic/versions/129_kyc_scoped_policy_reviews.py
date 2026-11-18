from pathlib import Path

from alembic import op

revision = "129"
down_revision = "128"


def upgrade():
    c = op.get_bind()
    if c.exec_driver_sql("SELECT 1 FROM anvil.schema_versions WHERE version=129").first() is None:
        c.exec_driver_sql(
            (Path(__file__).resolve().parents[2] / "migrations/129_kyc_scoped_policy_reviews.sql").read_text(),
            execution_options={"no_parameters": True},
        )


def downgrade():
    raise RuntimeError("Destructive downgrade is not authorized; use a forward migration.")
