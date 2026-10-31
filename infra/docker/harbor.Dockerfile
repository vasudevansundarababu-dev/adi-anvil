# Dedicated synthetic software-check host. API and normal worker never receive Docker access.
ARG BACKEND_IMAGE=anvil-backend:0.2.1-local
FROM docker:29.8.0-cli@sha256:eccaacfeed644c7de222ff047483568cb988dde95476fbaaf10ea2d04921bb66 AS dockercli
FROM ${BACKEND_IMAGE}
USER root
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/ /usr/local/lib/docker/cli-plugins/
COPY services/harbor/requirements.lock /opt/harbor-requirements.lock
COPY services/harbor/src /opt/anvil-harbor
RUN uv venv /opt/harbor --python /usr/local/bin/python \
    && uv pip install --python /opt/harbor/bin/python -r /opt/harbor-requirements.lock
ENV ANVIL_HARBOR_EXECUTABLE=/opt/harbor/bin/harbor \
    ANVIL_HARBOR_WORKER_ENABLED=synthetic-checks-only \
    ANVIL_HARBOR_WORK_ROOT=/var/lib/anvil/harbor-checks \
    ANVIL_HARBOR_DOCKER_HOST=unix:///var/run/docker.sock
ENV ANVIL_HARBOR_AGENT_PATH=/opt/anvil-harbor
CMD ["python", "-m", "anvil.harbor_worker"]
