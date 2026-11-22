# RL Gym v2 — local run

The new RL Gym (Anvil, modified) runs next to the existing workspace behind the local setting `RLGYM_V2=1`.
Design source: `adi-labs-design` branch `claude/rl-gym-spec-forge-changes-mockups`, `rl-gym/BUILD-LOCAL.md`.

```bash
pnpm preflight
```

```bash
pnpm setup:local
```

```bash
pnpm dev
```

```bash
pnpm rlgym:demo
```

- Workspace: http://127.0.0.1:3202 (with `RLGYM_V2=1`, `/` opens `/gym`; the previous workspace stays at `/workspace`).
- API http://127.0.0.1:8200 · Keycloak http://127.0.0.1:8180 · Studio stub http://127.0.0.1:8211 · ADI Forge stub http://127.0.0.1:8212.
- Accounts: `.local/demo-accounts.md` (never copy them anywhere). RL Gym profiles: admin-1 and admin-2 are Admin and binding
  approvers; reviewer-1 is an RL Engineer and binding approver; researcher and the other identities are RL Engineers;
  sales is a Viewer; outsider belongs only to the `isolation-control` workspace.
- `pnpm setup:local` appends the RL Gym settings and local client keys to `.env` (existing values are never replaced)
  and seeds the `adi-labs-research` workspace. `pnpm rlgym:demo` makes the Studio stub release Golden KYC V8
  (golden-kyc-openenv v2 and v3 qualified by the RL Gym, 20 evaluator configurations tested, template activated) and the
  ADI Forge stub export KYC November (`prj_7f3a91c2`, 40 tasks). Both steps are idempotent.
- A worktree can use its own Docker volumes: set `ANVIL_COMPOSE_PROJECT` before the first `pnpm setup:local`
  (this worktree uses `adi-anvil-rlgym`).

## Runs (work package 2.7)

Runs → New run (or Run benchmark on a project or a saved suite version) shows the admission checklist live; Start run
freezes the manifest and queues the episodes. A runner thread in the API process (`pnpm dev`) then:

1. builds `rlgym-local/golden-kyc-openenv:v3-…` with Docker from the Studio stub's recipe for that version, offline,
   on the pinned local base image (`RLGYM_ENV_BASE_IMAGE`, digest-pinned; nothing is pulled);
2. starts one container per run (`rlgym-run-…`, no network, read-only, no capabilities, CPU/memory/pid limits);
3. runs each episode as a fresh tool-server process in it, with the controlled mock agent (no model called);
4. seals the evidence bundle to `.local/rlgym/evidence/<workspace>/<run>/` (read-only, SHA-256 in the database);
5. scores it with the bound evaluator configurations (reference answers fetched for the scorer only) and stops the
   container when the run finishes.

The default suite (40 cases) with the three mock profiles is 120 episodes and takes about 30 seconds. Re-score is
explicit (run page ⋯ Re-score…). Set `RLGYM_RUNNER=off` to keep the API from running episodes. The episode viewer and SME review are
work package 2.9.

## Report and PDF (work package 2.8)

A completed run's Report tab has five views (Overview, Task results, Agent performance, Failures & evidence, Trust &
Safety) and drill-downs (capability, axes, task, case, Trust & Safety category, policy findings, risk, review item with
the RL engineer diagnosis). Export PDF stores the view as a report revision and prints it with headless Chrome
(`scripts/render-report-pdf.mjs`, Playwright) to `.local/rlgym/reports/` (write-once, hashed). Runs → tick completed
runs → Package (n) writes a hashed JSON bundle to `.local/rlgym/packages/`.

## Stub controls (each stands for a real trigger)

| Control | Stands for |
|---|---|
| `POST :8211/stub/bootstrap` | Studio releases Golden KYC V8 (registry events, A-06, A-03) |
| `POST :8211/stub/scenarios/release-v4`, `release-v5` | Studio releases the second seed family (v4 lacks the known fixtures and fails qualification; v5 is the fixed release) |
| `POST :8211/stub/scenarios/fault/{version}` `{"fault": "reset_keeps_findings"}` then `requalify/{version}` | A released version starts failing re-qualification (the urgent path) |
| `POST :8211/stub/inbox-items/{id}/status` `{"state": "planned", "planned_version": "v6"}` | Studio plans, releases or declines an inbox item |
| `POST :8212/stub/projects/prj_7f3a91c2/export` `{"export_id": "exp-0002", "corrections": {...}}` | ADI Forge re-exports corrected tasks |

Checks, in order (with `pnpm dev` running): `pnpm check`, `pnpm test:unit`, `pnpm test:e2e`, then

```bash
ANVIL_HARBOR_DOCKER_HOST=unix:///Users/vasudevansundarababu/.docker/run/docker.sock pnpm test:integration
```

While the RL Gym follows the local Studio (`rlgym-registry studio`), switch it back to the stub before running
`pnpm test:integration` or `pnpm test:e2e` (`python3 scripts/local.py rlgym-registry stub`, `pnpm stop`, `pnpm dev`):
the tests drive the Studio stub, and the running API would otherwise file the stub's events under Studio's registry
and deliver test workspaces' inbox items to the real Studio.

The Docker host is an explicit opt-in for the import sandbox's Docker-backed tests (Docker Desktop has no
/var/run/docker.sock). `pnpm test:e2e` and `pnpm test:integration` rebuild `artifacts/test-runs/journey.json` with
`tests/prepare_journey_fixture.py` when it is missing or stale.
RL Gym v2 tests: `tests/e2e/rlgym-v2.spec.ts`, `services/backend/tests/unit/test_rlgym_v2_unit.py`,
`services/backend/tests/integration/test_rlgym_v2*.py` (each module creates its own disposable `it-…` workspace).
Run tests (`test_rlgym_v2_runs.py`) need Docker.
Synthetic data only; no model is called.
