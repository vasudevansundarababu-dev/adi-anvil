# Anvil architecture

## Application and identity

The Next.js modern workspace is the only supported UI. Root and legacy `/p` bookmarks
redirect to `/workspace`; historical records and APIs remain intact. Keycloak supplies
OIDC sessions. FastAPI enforces Admin/RL Engineer permissions and PostgreSQL project
isolation; hiding a control in the browser is never an authorization check.

## Import and generation

Praxis exports carry exact source bytes, hashes and lineage. Anvil owns destination
access and execution admission. A v3 import freezes its generation configuration and
whole-import budget ledger. An Admin chooses the installation generation model separately
from per-run evaluation models. The import worker observes safe supplied-image tool
contracts, requests executable Python, and qualifies it in credential-free containers.
Generated positive/negative fixtures and withheld source QA must pass before publication.
Only declared rule IDs and source weights contribute to scores.

An ambiguous provider outcome keeps its reservation; it is never retried automatically.
Regeneration consumes the original cumulative ledger. Editing creates a successor draft;
previous Ready packages and run version bindings remain immutable. Colab/Jupyter notebooks
are manual export/import artifacts; the server revalidates returned code independently.

## Execution and evidence

Execution groups bind exact task/package, rubric, model, credential and framework
versions. Run admission checks rights, server configuration and budget reservations.
The dedicated Harbor worker owns Docker access. Candidate tools run with no external
network, a read-only root, bounded CPU/RAM/processes and separate writable outputs.
The broker validates tool actions before dispatch and captures observable events.
Private evaluation code, fixtures and hidden references never enter the candidate image.
The isolated trusted grader produces a receipt checked against Harbor's recorded reward.

PostgreSQL is canonical for resources, revisions, artifacts, jobs, audit, score and budget
ledgers. LangGraph runs diagnostic workflows with durable checkpoints. Neo4j is a
rebuildable evidence projection. Task history owns result dashboards and comparison;
incompatible scoring/version bindings do not claim directly comparable score deltas.

## Credentials and cloud

Local secrets are encrypted and write-only through application APIs. Cloud generation
uses a pre-provisioned Secret Manager secret. API writes append-only versions using VM
workload identity; private disk indexes contain version locators, not keys. Loads verify
the credential ID, configuration binding and exact allowed secret resource. The runtime
has version-add/access permissions on that secret only. Paid evaluation credentials are
disabled for the YC release. Keys and metadata tokens never enter Docker child environments.

The existing GCP host uses a private Compute Engine VM behind an HTTPS load balancer,
production Keycloak and persistent disk-backed PostgreSQL/Neo4j/artifacts. Migrations are
additive; a pre-release disk snapshot protects rollback. Deployment evidence records exact
image tags, commits and checks. A healthy endpoint alone does not prove a model run.

## Source and verification

- `apps/web/src/components`: tasks, model settings, preparation, execution and diagnostics.
- `services/backend/src/anvil`: APIs, policies, generation, sandbox, Harbor broker and workers.
- `services/backend/migrations`: canonical schema and database boundaries.
- `services/backend/tests/unit`, `integration`: rules, credentials, privacy, budgets and native runs.
- `tests/e2e`: modern entry, OIDC, imports, readiness, run history and comparison.
- `contracts/praxis/golden-v3`: Marketing, KYC/AML and fraud software conformance cases.

See [BUILD-STATUS](../../BUILD-STATUS.md) for current evidence and
[executable import runbook](../runbooks/executable-import.md) for supported operations.
Controlled provider responses and scripted reference trials verify software mechanics;
they are explicitly not measurements of live model quality.
