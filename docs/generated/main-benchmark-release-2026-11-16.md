# Main Anvil benchmark release — 16 November 2026

Deployed to https://anvil-34-36-217-66.sslip.io/workspace on the existing
`adi-anvil-mvp-2026/us-west1-a/anvil-mvp-v1`. Verified21:37UTC /1:37PM Pacific.
User explicitly selected updating the main site with the benchmark branch.

Source: benchmark branch `a8a1a42`, plus local commit
`d50388076f9f66181ed470afe4a0ecf10cd92801`. Isolated worktree:
`/Users/vasudevansundarababu/Code-Repo/ADI-Anvil/.local/main-release-20261116`.
Original dirty working tree is preserved and remains older. Do not redeploy its
HEAD. No GitHub push or merge occurred.

Production wiring adds the OpenEnv lock directory to the image context and enables
the existing benchmark API with an owner-only, disjoint private vault. Existing
generation, paid-evaluation, email, OIDC and secret configuration is unchanged.
New benchmark/environment UI and API code is shipped. Native/model execution
still requires its existing runtime, source, rights, credential and budget admission;
this release does not transfer temporary QA execution authority to production.

## Validation

- Cloud Build `b8abf3d6-25ae-4f37-b980-eacbcc07f2ee`: SUCCESS.
- Image tag `d503880-main-20261116`; actual web/API/worker/Harbor containers running.
- Backend registry digest `sha256:2a552602bdde45f3a72f5b4ec0a7f5ac800bba08119d331065ec9cffbcc2dc05`.
- Web digest `sha256:e363c36d3246781a72c1c47d9381750b80d54f8c2072efb61e9e25d93fe9b82c`.
- Harbor digest `sha256:7ad7a80ddc0f728109a3b8233606be5766fd4621eefb9b95dc1f3f26eb4b3fcf`.
- `uv sync --frozen --project services/backend` and `pnpm install --frozen-lockfile`: PASS.
- `pnpm --filter @anvil/web check` and `pnpm --filter @anvil/web build`: PASS.
- Full backend unit suite:935 PASS, one existing Authlib deprecation warning.
  Initial attempts lacked required test configuration, short socket paths and
  independent Harbor runtime; those failures are retained, not counted as passes.
  Corrected command used `ANVIL_ROOT=/private/tmp/av1116 ANVIL_ENV=local
  WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_FIXTURE_MODE=true
  PYTHONPATH=/private/tmp/av1116/services/backend/src` with the release venv's
  `python -m pytest /private/tmp/av1116/services/backend/tests/unit -q`.
  This short-path source export was made from exact committed release source.
- `node --test tests/benchmark-dashboard.mjs tests/benchmark-results.mjs tests/benchmark-rehearsal.mjs`:26 PASS.
- Disposable migration Cloud Build `21501f89-9fb2-4d87-87cd-29419fe98cc1`: SUCCESS.
  New backend image against pinned PostgreSQL17; fresh069 and038→069 paths,
  both repeated, including restricted evaluator-role reuse across databases.
- Production038→069: PASS. Public API/database ready; live dispatch disabled.
- Pre/post complete-row fingerprints for calls, spending windows, generation calls,
  imports, users and memberships: identical. Runtime app/Harbor env hashes: identical.
- HTTPS workspace and actual browser-to-Keycloak sign-in form: PASS. Exact OIDC
  issuer verified; public administration404; anonymous benchmark dashboard401.
- Full authenticated production benchmark operation: NOT RUN; no password accessed,
  approval clicked, model/generation request dispatched or fixture copied from QA.
- Full SQL/security/browser/native regression suite on successor production source:
  NOT RUN in this session; historical evidence remains source-specific.

## Recovery and persistence

Snapshot `anvil-before-benchmark-20261116`: READY before migration. Original image
tag `15e35f1-1794018124`. Root-only recovery directory on the existing main VM:
`/var/lib/anvil/releases/d503880-main-20261116`, containing original `.env`,
Compose, SQL dump, config hashes and fingerprint checks. No backup downloaded.

Migration history is forward-only. Review schema compatibility before image-only
rollback. Restore canonical data only through an explicitly reviewed recovery plan;
do not automatically overwrite current data from the pre-release snapshot/dump.
VM image/Compose metadata was updated after successful rollout; all other metadata,
including existing generation scope, remains preserved. No VM recreation, IAM grant,
database reset, volume deletion or temporary QA VM restart.

No paid model call was made during this release. Existing unknown outcomes and
reserved amounts are preserved. Cloud build/snapshot charges are not reconciled;
no zero-infrastructure-cost claim is made.
