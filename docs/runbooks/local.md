# Local operation

The current environment is macOS arm64, Node 24.21.0, pnpm 10.34.5, Python 3.12.14 in the backend virtualenv, uv 0.12.19 and Docker Compose 5.5.1. Versions are locked independently; no sibling repository is required.

`pnpm setup:local` creates random owner-only local credentials, installs frozen pnpm/uv locks, starts the three named infrastructure services, migrates and seeds distinct identities. Repeating setup preserves existing credentials, records and volumes. Do not replace an existing `.env` with `.env.example`; the latter documents placeholders.

`pnpm dev` starts the API, worker and web app. Open http://127.0.0.1:3202. Keycloak is http://127.0.0.1:8180; API is http://127.0.0.1:8200. Credentials are in `.local/demo-accounts.md`; do not copy them into tickets, screenshots or commits. The default project is an illustrative synthetic workspace. `pnpm demo:new --name "My synthetic review"` creates a separate empty project with the same distinct local identities.

Use Researcher for objectives, suites, protocols, run launch and reports; Data Engineer for fixture or manifest intake and task publication; assigned Reviewer/Advisor for qualification and grading; Product Owner for scope, rights and release decisions; Sales for permitted kit downloads and network-free mail simulations. Sign out and sign in to the assigned identity. A local role exercise does not constitute expert validation or paid authority.

Run checks in order: `pnpm check`, `pnpm test:unit`, `pnpm test:e2e`, `pnpm test:integration`. E2E creates a new isolated project and leaves auditable records. Later integration tests use its saved protocol. `services/backend/.venv/bin/python tests/graph_outage.py` intentionally stops and restarts only Neo4j. `services/backend/.venv/bin/python tests/migration_smoke.py` creates a retained disposable database and tests migrations twice.

`pnpm worker:restart` restarts only the registered worker. `pnpm stop` stops registered API/web/worker process groups. `pnpm services:down` stops infrastructure while retaining volumes. Never use volume deletion or a database reset as routine recovery. Logs and the process registry are under ignored `.local/`; inspect locally and redact before sharing.

The CI workflow is a local draft, not evidence of a GitHub run. Browser tests use installed Chrome locally and Playwright Chromium in CI. Live models, production identity, general clean-file intake and real email require separate qualification/authority; see BUILD-STATUS.md for exact gaps.

Keep E2E and integration sequential: integration consumes the saved E2E project, while E2E deliberately supersedes reports and restarts the worker. Do not run the400-episode load script concurrently with either. The clean-install rehearsal exposed and fixed two historical-fixture assumptions; tests now create those prerequisites explicitly. The authenticated-read audit freezes only its project's jobs/projection while checking business-table immutability and exact access-audit appends.
