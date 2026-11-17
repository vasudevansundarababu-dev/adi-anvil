# CANDIDATE ONLY: requires reviewed services/harbor/runtime/uv.lock first.
# Separate runtime artifact; API/normal worker images and old Harbor lock unchanged.
# Invocation must supply reviewed immutable image references. No default/floating base.
ARG UV_IMAGE
ARG PYTHON_IMAGE
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE}
ARG UV_VERSION
USER root
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_NO_CACHE=1 UV_COMPILE_BYTECODE=0 PYTHONDONTWRITEBYTECODE=1
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/anvil-runtime-source
COPY services/backend/pyproject.toml services/backend/uv.lock services/backend/
COPY services/backend/src services/backend/src
COPY services/backend/migrations services/backend/migrations
COPY services/backend/alembic.ini services/backend/alembic.ini
COPY services/backend/alembic services/backend/alembic
COPY services/harbor/pyproject.toml services/harbor/
COPY services/harbor/src services/harbor/src
COPY services/harbor/requirements.lock services/harbor/requirements.lock
COPY services/openenv/uv.lock services/openenv/uv.lock
COPY integrations/evaluators/promptfoo/redteam-worker.mjs integrations/evaluators/promptfoo/redteam-worker.mjs
COPY integrations/evaluators/local_worker.py integrations/evaluators/local_worker.py
COPY contracts contracts
COPY integrations/evaluators/nemo/uv.lock integrations/evaluators/nemo/uv.lock
COPY integrations/evaluators/promptfoo/worker.mjs integrations/evaluators/promptfoo/worker.mjs
COPY integrations/evaluators/promptfoo/package-lock.json integrations/evaluators/promptfoo/package-lock.json
COPY infra/docker/marketing-runtime.Dockerfile infra/docker/seal-runtime-wheels.py infra/docker/
# Missing final reviewed lock must fail the build, never resolve in a build step.
COPY services/harbor/runtime/pyproject.toml services/harbor/runtime/uv.lock services/harbor/runtime/
COPY services/harbor/runtime/build-requirements.in services/harbor/runtime/build-requirements.lock services/harbor/runtime/
RUN set -eux; test -n "${UV_VERSION}" \
    && test "$(uv --version)" = "uv ${UV_VERSION} (x86_64-unknown-linux-musl)" \
    && test "$(/usr/local/bin/python -c 'import sys,platform; print("%d.%d/%s/%s" % (*sys.version_info[:2],sys.platform,platform.machine()))')" = 3.12/linux/x86_64 \
    && mkdir /opt/anvil-runtime-wheels \
    && uv --version > /opt/anvil-runtime-wheels/uv-version.txt \
    && /usr/local/bin/python -m venv --copies --without-pip /opt/anvil-runtime-builder \
    && uv pip install --python /opt/anvil-runtime-builder/bin/python \
       --no-build --no-deps --require-hashes -r services/harbor/runtime/build-requirements.lock \
    && uv build --wheel --python /opt/anvil-runtime-builder/bin/python \
       --no-build-isolation --offline --no-index \
       --out-dir /opt/anvil-runtime-wheels services/backend \
    && uv build --wheel --python /opt/anvil-runtime-builder/bin/python \
       --no-build-isolation --offline --no-index \
       --out-dir /opt/anvil-runtime-wheels services/harbor \
    && /usr/local/bin/python -I -B infra/docker/seal-runtime-wheels.py \
    && /usr/local/bin/python -m venv --copies --without-pip /opt/anvil-runtime \
    && UV_PROJECT_ENVIRONMENT=/opt/anvil-runtime uv sync \
       --project services/harbor/runtime --frozen --no-dev --no-editable --no-build --no-install-local \
    && uv pip install --python /opt/anvil-runtime/bin/python --no-deps --no-index \
       --no-build --require-hashes -r /opt/anvil-runtime-wheels/first-party.requirements.lock
ENV ANVIL_ROOT=/opt/anvil-runtime-source HOME=/tmp LANGSMITH_TRACING=false DO_NOT_TRACK=1 OTEL_SDK_DISABLED=true
USER 10001:10001
# Both first-party packages are installed into this one venv's site-packages.
# No site-packages overlay, executable .pth, PYTHONPATH or environment activation.
# No container entrypoint/worker/service/port/volume; operator uses exact interpreter.
