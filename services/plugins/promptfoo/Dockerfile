# Promptfoo verifier plug-in (adi.verifier-plugin.v1). Built offline from the digest-pinned Node 22 image and the
# promptfoo 0.125.1 dependency tree installed once from its lockfile (owner-approved download); nothing is fetched
# during the build or at run time.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
WORKDIR /app
COPY package.json package-lock.json /app/
COPY node_modules /app/node_modules
COPY plugin.mjs /app/plugin.mjs
ENV HOME=/tmp PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 NODE_ENV=production
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin verifier
USER 10001
ENTRYPOINT ["node", "/app/plugin.mjs"]
LABEL ai.adi-labs.verifier-plugin.id="promptfoo" ai.adi-labs.verifier-plugin.version="1.0.0" \
      ai.adi-labs.verifier-plugin.upstream="promptfoo@0.125.1"
