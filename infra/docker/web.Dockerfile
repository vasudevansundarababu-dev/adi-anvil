# ADI Anvil web image. Built from the repository root with the locked pnpm workspace.
FROM node:24.21.0-bookworm-slim AS build
RUN corepack enable && corepack prepare pnpm@10.34.5 --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile --filter @anvil/web...
COPY apps/web apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @anvil/web build

FROM node:24.21.0-bookworm-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=build --chown=node /app /app
USER node
WORKDIR /app/apps/web
EXPOSE 3202
CMD ["node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3202"]
