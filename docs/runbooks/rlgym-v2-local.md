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

## Stub controls (each stands for a real trigger)

| Control | Stands for |
|---|---|
| `POST :8211/stub/bootstrap` | Studio releases Golden KYC V8 (registry events, A-06, A-03) |
| `POST :8211/stub/scenarios/release-v4`, `release-v5` | Studio releases the second seed family (v4 lacks the known fixtures and fails qualification; v5 is the fixed release) |
| `POST :8211/stub/scenarios/fault/{version}` `{"fault": "reset_keeps_findings"}` then `requalify/{version}` | A released version starts failing re-qualification (the urgent path) |
| `POST :8211/stub/inbox-items/{id}/status` `{"state": "planned", "planned_version": "v6"}` | Studio plans, releases or declines an inbox item |
| `POST :8212/stub/projects/prj_7f3a91c2/export` `{"export_id": "exp-0002", "corrections": {...}}` | ADI Forge re-exports corrected tasks |

Checks, in order: `pnpm check`, `pnpm test:unit`, `pnpm test:e2e`, `pnpm test:integration` (needs `pnpm dev` running).
RL Gym v2 tests: `tests/e2e/rlgym-v2.spec.ts`, `services/backend/tests/unit/test_rlgym_v2_unit.py`,
`services/backend/tests/integration/test_rlgym_v2.py` (each run creates its own disposable `it-…` workspace).
Synthetic data only; no model is called.
