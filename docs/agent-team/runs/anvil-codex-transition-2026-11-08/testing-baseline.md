# Codex Testing baseline and environment preparation

2026-11-08. Independent Testing agent; preliminary development baseline, not the final QA verdict. Started from transition commit `54484d0fdf0040cc378f7f18348236e9f865ac63`; Coding concurrently edits the working tree, so no immutable final tested-SHA claim is made.

## Supported isolated prerequisites actually prepared

- Existing supported Python 3.12.14 interpreter reused without modifying its installation. Frozen backend `uv sync` installed 85 packages into `/private/tmp/anvil-testing-backend`; cache `/private/tmp/anvil-testing-uv`. An initial offline attempt was blocked by an uncached macOS ARM psycopg binary wheel; subsequent authorized locked download succeeded.
- Separately locked Harbor 0.25.0 runtime installed 91 packages into ignored `.local/harbor-venv`, required by existing tests' exact client path. No Harbor/Docker native execution occurred during this install.
- `pnpm install --frozen-lockfile --ignore-scripts --store-dir /private/tmp/anvil-testing-pnpm-store` installed 52 packages in this clean checkout. No lockfile change or global install. Node 24.21.0 and pnpm 10.34.5 match repository declarations.
- Offline tests use a constructed environment allowlist, fresh owner-only HOME/TMP/vault, fixture mode, live providers/email/tracing disabled, no ambient credential or deployed database variables.

## Checks actually observed

| Check | Actual result | Boundary |
| --- | --- | --- |
| `node --test tests/provider_failure.mjs tests/readiness_catalog.mjs` | 12 passed, zero failed/skipped | Node module-type performance warnings only |
| `pnpm --filter ./apps/web exec tsc --noEmit --incremental false` | Exit 0 | Working-tree development baseline |
| Full backend units, initial incomplete setup | 701 passed, 28 failed | Missing `.local` gateway parent; Harbor not installed. Not a green run |
| Focused gateway reproducer after parent creation, restricted shell | Failed with socket bind EPERM | Execution permission limitation; not evidence of an auth/product defect |
| Same focused long-owned-trial gateway test, socket permission granted | 1 passed | No product edits or permission loosening |
| Full backend units after prerequisites and local socket permission | 744 passed, one Authlib deprecation warning, 37.60 seconds | Concurrent Coding source; not final immutable QA. Counts overlap focused checks |
| Fresh dedicated PostgreSQL canonical/checkpointer migration | Exit 0, head 049 | New isolated local database only |
| First benchmark SQL batch | 21 passed, 23 failed, 59 errors, 19 deselected | Misconfigured vault outside installation correctly rejected. Prior failure retained in private local log; corrected run pending |
| Benchmark SQL after vault correction, before fixture feature flags | 35 passed, nine failed, 59 errors, 19 deselected | Benchmark intake default-off correctly returned 503; setup corrected with explicit fictional-only intake/evaluator flags |
| Explicit benchmark SQL batch after full fixture setup | 103 passed, 19 deselected, one Authlib warning, 23.96 seconds | Native tests deliberately deselected, not counted as native pass; real new local PostgreSQL/auth/API paths |
| Separately locked Harbor adapter unit guards | Seven tests passed | `PYTHONPATH=services/harbor/src .local/harbor-venv/bin/python -m unittest discover -s services/harbor/tests -q`; no Docker execution |
| Independent local port/origin regressions | 22 passed; Ruff check/format passed | Defaults unchanged; supported ports accepted; remote/mismatched origins, Unicode/malformed/out-of-range ports rejected |
| Real authenticated browser benchmark intake journey | One passed, 3.2 seconds | Genuine new Keycloak login, actual gzip API/SQL upload and persisted receipt; no API mocks |

Commands invoke the isolated interpreter directly with `-p no:cacheprovider`; no skipped native cases are counted as pass. Final source checkpoint must receive independent reruns and new evidence.

## New owned test database

Created only `anvil-codex-testing-pg-20261108`, volume `anvil-codex-testing-pg-20261108-data`, unique binding `127.0.0.1:57672`. Exact preloaded image `postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3`, linux/arm64, `--pull=never`, bounded CPU/memory/PIDs and no-new-privileges. Owner/app/worker credentials are freshly generated, stored only in owner-only temporary state; no credential values are included here. App/worker roles are nonsuperuser/NOBYPASSRLS. No existing containers, volumes, services, projects or cloud resources were modified.

The fixture vault is now fresh owner-only `.local/testing-vault` inside this installation, as product policy requires. The initial external temporary vault was rejected; policy was preserved.

## Native qualification constraint

Read-only Docker image inspection confirmed both exact PostgreSQL image above and `python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e` preloaded on Docker Desktop, linux/arm64. No pulls were needed or performed.

However, `NativeDocker` currently requires the installation's `.local/benchmark-docker/docker.sock` and hardcodes `sudo -n /usr/bin/docker`, reflecting the old dedicated Linux runtime. This Mac's Docker Desktop socket is a different endpoint. Native qualification remains blocked pending a reviewed portable dedicated runtime configuration; image availability alone is insufficient. Do not spoof the expected socket, loosen socket permissions or replace the approved restricted adapter with stock Harbor probes. This constraint does not block independent offline and isolated SQL work.

Remaining baseline/final work: fresh/upgrade/repeat migration evidence; auth/finalization regression integration with required independent fixtures; supported native runtime decision; final T07–T10 requirement/API/browser verification on a checkpoint; build and staging-readiness handoff. No paid calls, QA completion claim or deployment occurred.

The corrected SQL command was `python -m pytest services/backend/tests/benchmark -k 'not real_native and not native_actor and not native_' -q -p no:cacheprovider --tb=short`, through a temporary allowlist helper. It enables only fictional benchmark intake/evaluation, leaves all paid flags false, and uses the dedicated generated local credentials. No live dispatch or judge path was invoked. Prior setup failures remain recorded above and were not masked by changing tests/product policy.

## Authenticated browser prerequisites

Read-only inspection confirmed the exact pinned Keycloak `quay.io/keycloak/keycloak:26.3.5@sha256:357829ec7c4693397533035092ad13b0644bcc95ded311f33a3738c4d9e9bdba` and Neo4j `neo4j:5.26.12-community@sha256:9f75e8df4325a24f00fdd7a8c0bcce650a58375049b1058e496e8b43d6c36b37` images already preloaded, linux/arm64. No pulls or starts performed for them yet.

Elevated temporary loopback-bind checks found all repository default ports 3202/8200/8180/7475/7688 occupied (`EADDRINUSE`). No existing service was contacted, stopped or reused. The current backend local origin, Next API rewrite, Playwright base URL and generated identity redirect are fixed to 3202/8200. A reviewed configurable loopback-only setup is needed for separate fresh browser services; do not point new tests at existing application instances or change another checkout's ports/settings. Root was informed before proceeding.

Root subsequently implemented reviewed local port configuration, with default behavior preserved. Testing added `services/backend/tests/unit/test_local_ports.py` (22 cases). Fresh services now use web 64829, API 64830, identity 64831, graph HTTP 64832 and Bolt 64833, all loopback. New containers are `anvil-codex-testing-oidc-20261108` and `anvil-codex-testing-graph-20261108`; new graph volume `anvil-codex-testing-graph-20261108-data`; exact preloaded pins and `--pull=never`. Generated realm and synthetic account files remain owner-only and ignored. No existing default-port services were changed.

`tests/e2e/benchmark-workspace.spec.ts` used the real separate Keycloak sign-in and actual API to import an unsigned fictional three-task archive, verified gzip/CSRF/idempotency headers, quarantined/unsigned status, persisted detail after refresh, disabled unreviewed build, absence of invented comparisons/results and cross-project denial. First test attempt encountered Chrome inspector POST-body-cache eviction after navigation; the test now independently reads the persisted receipt through authenticated GET. The corrected test passed without a product behavior change. Screenshot `artifacts/test-runs/benchmark-workspace.png` was visually inspected: authentic current UI, clearly fictional quarantined source and paid calls disabled, no credentials visible. This is intake/UI evidence, not full benchmark/native qualification. Native remains blocked.

The root production build briefly overlapped the existing dev process; root reported build success and no remaining build process. The subsequent actual browser run passed, so no dev-health fault was observed. This is recorded rather than treating build output as independent browser coverage.
