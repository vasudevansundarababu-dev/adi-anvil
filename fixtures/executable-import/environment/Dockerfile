FROM us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/native-fixture-security@sha256:72b8eaacefaa82ffdec3ee632375df24057962d8c14cc327f1990113f7c2b951
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --no-create-home --shell /bin/sh candidate && mkdir -p /workspace/inputs /workspace/output && chown -R 10001:10001 /workspace
COPY server.py tool_schemas.json /opt/anvil_golden/
COPY data/ /opt/anvil_golden/data/
USER 10001
WORKDIR /tmp
CMD ["sleep", "infinity"]
