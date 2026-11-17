# Two separately addressable task runtime identities share an exact locked closure.
ARG TASK_RUNTIME_IMAGE
FROM ${TASK_RUNTIME_IMAGE}
ARG TASK_KIND
LABEL io.adi.forge.task-kind=${TASK_KIND}
ENV ANVIL_TASK_RUNTIME_KIND=${TASK_KIND}
USER 10001:10001
