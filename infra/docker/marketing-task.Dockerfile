# Candidate actor/private-verifier image. Operator/daemon image remains separate.
# Both arguments must be exact reviewed immutable references for the SAME Python base.
ARG TASK_RUNTIME_IMAGE
ARG PYTHON_IMAGE
FROM ${TASK_RUNTIME_IMAGE} AS installed
USER root
RUN python3 -I -B -c "import hashlib,json,pathlib; base=pathlib.Path('/usr/local'); files=[base/'bin/python3.12',*[p for p in (base/'lib/python3.12').rglob('*') if p.is_file() and not {'site-packages','__pycache__'}.intersection(p.parts)]]; pathlib.Path('/opt/anvil-base-python-identity.json').write_text(json.dumps({str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},sort_keys=True))"
FROM ${PYTHON_IMAGE}
COPY --from=installed /opt/anvil-runtime /opt/anvil-runtime
COPY --from=installed /opt/anvil-base-python-identity.json /opt/anvil-base-python-identity.json
RUN python3 -I -B -c "import hashlib,json,pathlib; base=pathlib.Path('/usr/local'); files=[base/'bin/python3.12',*[p for p in (base/'lib/python3.12').rglob('*') if p.is_file() and not {'site-packages','__pycache__'}.intersection(p.parts)]]; assert json.loads(pathlib.Path('/opt/anvil-base-python-identity.json').read_text())=={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'Actor/runtime Python base differs'"
COPY --from=installed /opt/anvil-runtime-source/services/backend /opt/anvil-runtime-source/services/backend
COPY --from=installed /opt/anvil-runtime-source/services/harbor /opt/anvil-runtime-source/services/harbor
COPY --from=installed /opt/anvil-runtime-source/services/openenv /opt/anvil-runtime-source/services/openenv
COPY --from=installed /opt/anvil-runtime-source/infra/docker /opt/anvil-runtime-source/infra/docker
COPY --from=installed /opt/anvil-runtime-source/integrations/evaluators /opt/anvil-runtime-source/integrations/evaluators
# Never copy task/export fixtures or their private QA expectations into actor images.
COPY --from=installed /opt/anvil-runtime-source/contracts/praxis/*.schema.json /opt/anvil-runtime-source/contracts/praxis/
COPY --from=installed /opt/anvil-runtime-source/contracts/workflow/*.schema.json /opt/anvil-runtime-source/contracts/workflow/
COPY --from=installed /opt/anvil/opa /opt/anvil/opa
# Keep only fields admitted by the existing strict image environment profile.
# The renderer supplies exact bounded per-task context, never ambient credentials.
ENV PATH=/opt/anvil-runtime/bin:/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /task
USER 10001:10001
# No inherited operator UV/Anvil/telemetry env, entrypoint, socket, volume or port.
# The fixed verifier argv now resolves python3 from the installed wheel venv.
