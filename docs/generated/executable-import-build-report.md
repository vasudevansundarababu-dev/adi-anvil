# Executable-import completion report

1 November 2026. Local spec24 implementation on `codex/anvil-modern-workspace`.

All three golden exports pass the full application generation-to-native-Harbor software
path. This includes API intake, global model settings, one cumulative whole-import cap,
durable reservations and ambiguous-dispatch handling, generated verifiers/constraints/
fixtures, restricted Docker qualification, withheld source QA, actual MCP tools,
version-bound packages, bounded tool-agent evaluations, dashboards and notebook return.
Configuration rebinding preserves original cap, spend, history and revision provenance.
Local testing has no human approval gate. External paid processing retains exact source,
configuration and budget authority. Candidate inputs exclude private references and graders.

## Verification

- `ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=unix:///Users/vasudevansundarababu/.docker/run/docker.sock python3 -c 'import scripts.local as l; l.run([str(l.PY),"-m","pytest","services/backend/tests/integration/test_import_pipeline.py","-q","--tb=short","-x"],env=l.env())'`: **11 passed,326.40s**. All3 sources,21 withheld cases,18 actual native evaluation trials,3 notebook successors. Includes invalid code/edit recovery, permissions, revocation, cancellation, cumulative caps, no ambiguous retry, guard enforcement, output limits and concurrent lock ordering. Provider SDK responses use authored test transports, never a production golden-only compiler.
- `pnpm test:unit`: **298 passed**.
- Related API integration regression covering import pipeline, Praxis contracts/Harbor,
  preparation, execution, task pages, credentials and access: **49 passed,2 skipped**.
  Skips require two external legacy Praxis byte files not supplied to those tests.
- `pnpm check`: lint, formatting, types, production web build and OpenAPI checks passed.
- `pnpm exec playwright test tests/e2e/golden-executable-import.spec.ts tests/e2e/workspace-task-pages.spec.ts tests/e2e/workspace-preparation.spec.ts tests/e2e/workspace-model-versions.spec.ts`: **6 passed**. Includes notebook API download and safe retry after lost response.
- `scripts/verify_golden_imports.py --native`, through the local Python environment
  with explicit Docker opt-in: **3 tasks,21 authored oracle cases,9 actual native trials**.
- `scripts/package_golden_imports.py`, through the same environment: delivered3 exports,
  ZIP with schema/reference fixtures/two verification reports/manifest, separate local
  Docker image archive and SHA256SUMS. Delivery folder: `artifacts/golden-harbor-imports`.

Authlib/Alembic deprecation warnings remain non-failing. Earlier verifier staging failures
were fixed using root-only executable staging and Harbor-supported log mounts. Private
graders run independently; native Harbor receives only the trusted numeric grade after
the candidate finishes. Tests verify raw Harbor reward parity.

## Limits and operational handoff

No real paid model requests were sent. These results establish application behavior,
not model accuracy. No GCP deployment, remote push, email, IAM changes or registry push.
The supplied image digest identifies a local Docker image; publish/availability on GCP
was not tested. Cloud credential entry still needs its managed secret-store adapter.
Notebook support is portable download/edit/upload with authoritative Anvil revalidation,
not automatic Drive synchronization or provisioned Colab/Jupyter infrastructure.

Actual generation needs an explicitly scoped installation Admin, configured standard
model/credential/default cap, enabled server configuration and exact processing authority.
No settings or real keys were invented or seeded into the live installation. Evaluation
models remain separate. Existing live flags/credentials and unrelated edits were preserved.
Classic comparison branch remains unchanged. Local application URL: http://127.0.0.1:3202.
