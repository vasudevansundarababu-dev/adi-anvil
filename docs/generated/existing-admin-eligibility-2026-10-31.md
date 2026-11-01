# Existing Admin account eligibility

User clarification, 31 October 2026: Admin and RL Engineer are the access roles; an
existing Admin must not need a second account or invitation to run evaluations.

Removed account-origin restrictions from modern group authorizations and the legacy
provider/marketing/Harbor Admin checks and authorization counts. Eligibility requires
an active user with active Admin membership in the exact project. No users, passwords,
memberships, origin flags or credentials were changed. In particular, admin-1 remains
the same identity and its original provenance is retained. Modern authorization audit
metadata records `active-project-admin-v2` and the actor's seeded-origin boolean.

Sign-in, project scope, recent authentication, immutable model/key/task bindings, reviewed
configuration/rights, explicit budget, atomic reservation, revocation and no-retry behavior
remain. Synthetic outputs remain separate from actual provider execution. Saving or
enabling the server does not launch a model; the user's explicit Run is still required.

## Verification

- `pnpm test:unit`: 242 passed (3.81s).
- Existing `admin-1` is now the main execution-contract creator/authorizer in retained
  isolated test databases. Positive assertions verify its unchanged origin flag and
  immutable authorization/audit evidence. RL Engineer and outsider negatives remain.
- `ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=unix:///Users/vasudevansundarababu/.docker/run/docker.sock python3 -c 'import scripts.local as l; l.run([str(l.PY),"-m","pytest","services/backend/tests/integration/test_workspace_execution.py","services/backend/tests/integration/test_marketing.py","-xq"],env=l.env())'`:
  13 passed (48.83s), including staged Docker Harbor with native SDK MockTransports for
  OpenAI, Anthropic and Gemini. No external inference request or paid call was made.
- API security and three added Admin revocation cases: 50 passed, two failures (42.38s).
  The failures were task-boundary fixtures using an unassigned actor for private source
  references. Corrected only those test actors to the existing source owner. Follow-up
  of both cases plus workspace-access/privacy coverage: 6 passed (0.84s).
- The three new isolated tests revoke the authorizing user's activity, membership or
  Admin role and verify no authorization or SDK dispatch survives. Existing exact-cap,
  rights, project, cancellation, key-rotation, uncertain-outcome and duplicate-launch
  contracts remain verified by the execution suite.
- Initial static check found import ordering after the helper rename; corrected it.
  Final `pnpm check` passed: lint, formatting, TypeScript, production build and OpenAPI.
- Browser follow-up and final runtime state are recorded in BUILD-STATUS.

No schema migration was needed. Full-platform integration and backup/restore were not
repeated for this authorization-policy change. Prior recovery evidence remains historical.
No cloud rollout, IAM/account provisioning, email, dependency installation, identity
promotion, paid smoke or automatic launch occurred. Local live execution remains enabled
at the user's explicit request, with all per-run checks above. Unrelated user edits and
the classic comparison branch are preserved.
