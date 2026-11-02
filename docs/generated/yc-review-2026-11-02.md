# YC review checkpoint — 2 November 2026

## Review first

- [Module definitions and distinctive features](../product/MODULE-GUIDE.md).
- [Architecture](../architecture/README.md) and [source/test map](../../README.md).
- [Both applications: verified entry points and sign-in](../runbooks/reviewer-sign-in.md).
- [30-day roadmap](../build/11-30-DAY-ROADMAP.md): remaining Anvil/Praxis work, SME
  review API roundtrip and expert taskbank recruitment targets.
- [5 PM demo plan](../build/12-YC-DEMO-PLAN.md).

## Benchmarks increment

Modern `/workspace/{project}/benchmarks` reuses the existing canonical Factory APIs;
former `/p/{project}/factory` bookmarks redirect there. It displays loaded executable
task candidates separately from catalog metadata, and supports confirmed profiles,
registration, deterministic recommendation, Suite drafts and gap drafts. No new catalog,
schema migration, rights grant or model invocation is introduced. Admin/RL Engineer
authorization, project isolation and exact-version bindings remain server enforced.

Qualified static synthetic diagnostic tasks and approved objectives are prerequisites
for this matching path. Full benchmark manifests, release qualification and expert
TaskBanks are not claimed. Professor/guide validation and 200–500 independently authored
samples per domain are targets in the roadmap, not existing inventory or partnerships.

## Gemini: diagnosis versus recovery

**Later bounded live recovery check, 2 November, 4:23 PM Chicago:** user separately
authorized one new `gemini-3.8-flash` diagnostic capped at$0.10, no retries. After
user-confirmed fresh sign-in, group `4a7a2820-60ef-43df-be4e-81af262613a7` succeeded
with exactly one provider call costing$0.008462. Its synthetic generated verifier
reported100/100. All six earlier unknown requests/reservations and all pre-existing
spend windows remained unchanged. This verifies one real successful trial, not broad
model reliability, expert-calibrated performance or reconciliation of past failures.
Current exact tested profile: **Gemini 3.8 Flash · $0.10 diagnostic**. Existing
profiles configured for2.0Flash were preserved. Details: latest BUILD-STATUS entry.

**Demo clarification:** the default Benchmarks page is now an explicitly labeled
two-page UI mockup, per the user's later direction. The library links to a per-domain
comparison/protocol/coverage/failure dashboard. All displayed results and counts are
illustrative; full functionality is deferred. GDPVal remains Planned. The persistent
UI MOCKUP disclosure must remain visible in recordings. The previously verified
static diagnostic catalog remains separate at `/benchmarks/catalog`; its capabilities
must not be attributed to the mock dashboard.

Benchmarks source `b0eec40`, including diagnostic hardening, is running as image
`b0eec40-1793655919` on the existing Anvil host. Cloud Build
`7e6ac130-886d-4491-a6c3-d349e7561b7d` succeeded;
API/web/Harbor image identity, API/database/TLS/OIDC and public Keycloak Admin404 passed.
Deployed native SDK success/503/504 mocks each made one controlled request and zero
provider calls. Native Harbor/tool-agent/private-grader roundtrip passed with no fake
model result persisted.

After explicit user approval and a fresh Anvil sign-in, exactly one agent-initiated
Gemini-only Marketing diagnostic ran: group `25b42364-41f8-4bb0-adea-d72c5fbf4d80`,
check `515b13dc-7885-4aa1-a63c-c524af8df369`, cap$0.35 (below approved$0.50), estimated
ceiling$0.33024. Its only provider request returned **504 / DEADLINE_EXCEEDED** after
89.495s. Outcome/cost remain unknown, with$0.033024 reserved. No retry was attempted.
The four pre-existing unknown rows and their reservations were compared before/after
and are identical. At that checkpoint, known$0.646810 + unknown bounds$1.640448 =
$2.287258, below the unchanged$50 budget.

A separate subsequent user-created group `8248cb16-8543-47ca-a80a-c2353cd03797`
recorded successful Astra/Claude trials and Gemini **503 / UNAVAILABLE** after7.002s.
This is a provider service error, not proof that the task answer failed. Its reservation
also remains held. No automatic retry, forced model switch or zero-cost assumption.

The new local mitigation allows up to180s per request for newly created exact
`gemini-3.8-flash` plans, bounded by the episode time remaining. Other models keep90s;
existing plans are immutable. Token/call/spend ceilings are unchanged. Clear HTTP503/504
messages now appear in run dashboards/task logs. The mitigation is locally tested;
no extra live verification is authorized or claimed. Longer timeouts do not cure503.

## Verification for the new increment

| Check | Result |
| --- | --- |
| `pnpm test:unit` | 348 passed; existing Authlib deprecation warning |
| `node --test tests/provider_failure.mjs` / `pnpm test:ui-policy` | 2 passed; safe error display and malformed/private metadata handling |
| Factory API integration | 1 passed |
| Execution + Factory integration | 16 passed, 1 optional native-Harbor skip |
| `pnpm test:e2e tests/e2e/factory.spec.ts` | 1 passed,6.2s; modern link/bookmark, catalog/profile/Suite/gap, reload persistence |
| Related Benchmarks/preparation/comparison browser suites | 4 passed,45.9s |
| Three-golden native import/Harbor/notebook acceptance | 1 passed,301.73s; controlled providers, no paid calls |
| `pnpm check` | Passed lint/format/types/production build/API generation; final exact-source repeat recorded in BUILD-STATUS |

Final affected browser/build results are also recorded in BUILD-STATUS.
No skipped/blocked check counts as passed.
No current code-coverage percentage or scientific-validity claim is made. Earlier
release reports remain dated historical evidence.

## Check-in boundary

Only explicit reviewed source/docs/tests are included in local checkpoints. Preserve
unrelated AGENTS/cloud-runbook/Next environment changes and the classic comparison
branch. Existing remotes are retained. These new review changes are prepared locally;
no push or repository visibility change is part of this checkpoint.
