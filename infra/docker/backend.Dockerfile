# ADI Anvil API and worker image (same image, different command). Built from the repository root.
# Contains source, migrations and committed synthetic fixtures only; never .env, .local or .secrets.
FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv

FROM node:24.21.0-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS promptfoo
WORKDIR /opt/promptfoo
COPY integrations/evaluators/promptfoo/package.json integrations/evaluators/promptfoo/package-lock.json ./
# Lockfile integrity applies to the entire tree. Lifecycle scripts cannot fetch
# additional binaries or run package-provided installation programs.
RUN npm ci --ignore-scripts --omit=dev --no-audit --no-fund \
    && node -e "const fs=require('node:fs'); if(JSON.parse(fs.readFileSync('node_modules/promptfoo/package.json')).version!=='0.125.1') process.exit(1)" \
    && mkdir -p /opt/anvil-node-libs \
    && cp -L /usr/lib/*-linux-gnu/libstdc++.so.6 /opt/anvil-node-libs/libstdc++.so.6 \
    && cp -L /lib/*-linux-gnu/libgcc_s.so.1 /opt/anvil-node-libs/libgcc_s.so.1

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV ANVIL_ROOT=/app \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/app/services/backend/.venv/bin:$PATH
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=promptfoo /usr/local/bin/node /opt/anvil-node/bin/node
COPY --from=promptfoo /opt/anvil-node-libs/ /opt/anvil-node/lib/
COPY infra/docker/api-evaluator-node /opt/anvil-node/run-node
ENV ANVIL_EVALUATOR_NODE=/opt/anvil-node/run-node
WORKDIR /app
COPY --from=promptfoo /opt/promptfoo/ integrations/evaluators/promptfoo/
COPY integrations/evaluators/promptfoo/worker.mjs integrations/evaluators/promptfoo/redteam-worker.mjs integrations/evaluators/promptfoo/
RUN chmod 755 /opt/anvil-node/run-node \
    && test "$(/opt/anvil-node/run-node --version)" = v24.21.0 \
    && /opt/anvil-node/run-node --check integrations/evaluators/promptfoo/worker.mjs \
    && /opt/anvil-node/run-node --check integrations/evaluators/promptfoo/redteam-worker.mjs
COPY .python-version ./
COPY services/backend/pyproject.toml services/backend/uv.lock services/backend/
RUN uv sync --frozen --no-dev --no-install-project --project services/backend
COPY services/backend/alembic.ini services/backend/
COPY services/backend/alembic services/backend/alembic
COPY services/backend/migrations services/backend/migrations
COPY services/backend/src services/backend/src
COPY services/harbor/src services/harbor/src
COPY services/harbor/pyproject.toml services/harbor/requirements.lock services/harbor/
COPY services/harbor/runtime/pyproject.toml services/harbor/runtime/uv.lock services/harbor/runtime/build-requirements.in services/harbor/runtime/build-requirements.lock services/harbor/runtime/
COPY infra/docker/marketing-runtime.Dockerfile infra/docker/seal-runtime-wheels.py infra/docker/
COPY integrations/evaluators/local_worker.py integrations/evaluators/local_worker.py
COPY integrations/evaluators/nemo/uv.lock integrations/evaluators/nemo/uv.lock
COPY services/openenv/uv.lock services/openenv/uv.lock
COPY contracts contracts
COPY runtime-checks/api_installed.py /opt/forge-runtime-checks/api_installed.py
RUN python -c "import hashlib; from pathlib import Path; from urllib.request import urlopen; response=urlopen('https://github.com/open-policy-agent/opa/releases/download/v1.22.2/opa_linux_amd64_static',timeout=60); raw=response.read(80000001); response.close(); assert len(raw)<=80000000 and hashlib.sha256(raw).hexdigest()=='24e344d1fc394cd93dc75666f584cfb97c6981f7255af25f8d2979834317317b'; p=Path('/opt/anvil/opa'); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(raw); p.chmod(0o555)"
ENV ANVIL_OPA_BINARY=/opt/anvil/opa ANVIL_OPA_SHA256=24e344d1fc394cd93dc75666f584cfb97c6981f7255af25f8d2979834317317b
COPY fixtures fixtures
COPY task-packs task-packs
COPY assets/brand assets/brand
RUN uv sync --frozen --no-dev --project services/backend \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin anvil \
    && mkdir -p /app/.data/artifacts && chown -R anvil /app/.data && chmod 700 /app/.data
USER anvil
EXPOSE 8200
CMD ["python", "-m", "uvicorn", "anvil.api:app", "--host", "0.0.0.0", "--port", "8200", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
