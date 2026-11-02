FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --no-create-home --shell /bin/sh candidate && mkdir -p /workspace/inputs /workspace/output && chown -R 10001:10001 /workspace
COPY server.py tool_schemas.json /opt/anvil_golden/
COPY data/ /opt/anvil_golden/data/
USER 10001
WORKDIR /tmp
CMD ["sleep", "infinity"]
