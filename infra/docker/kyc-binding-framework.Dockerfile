# Phase3 migration/observation driver only. Never serve as API/worker/native image.
ARG CORE_IMAGE
FROM ${CORE_IMAGE}
ARG CORE_IMAGE
ARG NATIVE_SOURCE_SHA256
LABEL org.adi.forge.component="kyc-binding-framework" \
      org.adi.forge.core-image="${CORE_IMAGE}" \
      org.adi.forge.native-source="${NATIVE_SOURCE_SHA256}"
COPY --chown=0:0 services/backend/migrations/135_kyc_operator_binding_reads.sql /app/services/backend/migrations/135_kyc_operator_binding_reads.sql
COPY --chown=0:0 services/backend/alembic/versions/135_kyc_operator_binding_reads.py /app/services/backend/alembic/versions/135_kyc_operator_binding_reads.py
COPY --chown=0:0 infra/gcp/kyc_binding_observation.py /opt/forge-bindings/observe.py
USER anvil
RUN ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 EXPECTED_NATIVE_SOURCE="${NATIVE_SOURCE_SHA256}" python -B -c "import os; from alembic.config import Config; from alembic.script import ScriptDirectory; from anvil.golden_kyc_source import source_hash; assert source_hash()==os.environ['EXPECTED_NATIVE_SOURCE']; scripts=ScriptDirectory.from_config(Config('services/backend/alembic.ini')); assert scripts.get_revision('135').down_revision=='134'"
CMD ["python", "-m", "alembic", "-c", "services/backend/alembic.ini", "upgrade", "135"]
