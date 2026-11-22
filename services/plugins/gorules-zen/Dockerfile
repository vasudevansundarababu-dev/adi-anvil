# GoRules ZEN verifier plug-in (adi.verifier-plugin.v1). Built offline: the base image is pinned by digest and present
# locally, and zen-engine is the verified wheel copied into the build context (nothing is downloaded during the build).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG ZEN_WHEEL
COPY ${ZEN_WHEEL} /tmp/
RUN pip install --no-index --no-deps /tmp/${ZEN_WHEEL} && rm /tmp/${ZEN_WHEEL} \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin verifier
COPY plugin /app/plugin
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
USER 10001
ENTRYPOINT ["python", "-m", "plugin"]
LABEL ai.adi-labs.verifier-plugin.id="gorules-zen" ai.adi-labs.verifier-plugin.version="1.0.0" \
      ai.adi-labs.verifier-plugin.upstream="zen-engine==2.1.3"
