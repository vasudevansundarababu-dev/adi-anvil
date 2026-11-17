# Private grader/evaluator image: no Docker CLI, socket, or candidate credentials.
FROM us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/backend@sha256:a2819e51c44c933b61329067aee68c327ec1ebddba7e2658c0607aee6abe230a
USER root
COPY runtime-checks /opt/forge-runtime-checks
COPY integrations/evaluators/nemo/pyproject.toml integrations/evaluators/nemo/uv.lock /app/integrations/evaluators/nemo/
RUN UV_PYTHON_DOWNLOADS=never uv sync --frozen --no-dev --python /usr/local/bin/python --project /app/integrations/evaluators/nemo
RUN python -c "import hashlib; from pathlib import Path; from urllib.request import urlopen; response=urlopen('https://github.com/open-policy-agent/opa/releases/download/v1.22.2/opa_linux_amd64_static',timeout=60); raw=response.read(80000001); response.close(); assert len(raw)<=80000000 and hashlib.sha256(raw).hexdigest()=='24e344d1fc394cd93dc75666f584cfb97c6981f7255af25f8d2979834317317b'; p=Path('/opt/anvil/opa'); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(raw); p.chmod(0o555)"
ENV ANVIL_NEMO_PYTHON=/app/integrations/evaluators/nemo/.venv/bin/python ANVIL_OPA_BINARY=/opt/anvil/opa ANVIL_OPA_SHA256=24e344d1fc394cd93dc75666f584cfb97c6981f7255af25f8d2979834317317b PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 PROMPTFOO_SAFE_MODE=true DO_NOT_TRACK=1 OTEL_SDK_DISABLED=true LANGSMITH_TRACING=false
USER 10001:10001
