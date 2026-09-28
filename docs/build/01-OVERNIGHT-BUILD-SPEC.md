# Overnight build specification — ADI Anvil

Version 1.1 · 27 September 2026 · Local implementation target, not completed software

## 1. Outcome and authority

Build a real, independently runnable local application, not another static mockup. User-approved stack: Next.js, React, TypeScript, Tailwind, FastAPI, LangGraph, PostgreSQL and Neo4j with local Keycloak. Docker/Compose are reported working. Run in the new ADI-Anvil directory; keep the old specification project unchanged. Private GitHub publication waits for user review.

The user requests an eight-hour build window and morning end-to-end tests, including live model evaluation. The user currently has **no API keys**. Build provider integrations and mock-contract tests now; real requests are conditional on exact models, credentials, total budget, data permissions and runtime approvals. A working fixture journey is a useful partial result, not satisfaction of the requested live test.

The full baseline is [product engineering](../product/14-MVP-V1-ENGINEERING-BUILD-SPEC.md), [data/API contracts](../product/15-MVP-DATA-AND-API-CONTRACTS.md), [acceptance tests](../product/16-MVP-BUILD-AND-TEST-PLAN.md), [brand](../product/17-ANVIL-BRAND-AND-UI.md) and [Sales Kit](../product/18-AUTOMATED-SALES-KIT-SPEC.md). This overlay replaces the old repository location and phase-0–1-only prompt, expands provider support, and makes the entire local journey the overnight target. It does not relax any scientific/security gate.

## 2. Required vertical slice

1. Log in as a real local OIDC test identity; only assigned projects are visible.
2. Create an objective, measurement plan and exact-version recommendations/approval.
3. Import permitted source files and a case pack; show gaps, rights and version history. Human-readable partner paths are mapped to uploaded artifact IDs; never accept arbitrary filesystem reads or remote URLs.
4. Create/review task and rubric, validate calibration fixtures, publish a task, freeze a suite and protocol.
5. Execute deterministic fixture candidates through the actual LangGraph worker with durable checkpoints; optionally execute explicitly authorized real candidates through the same boundary.
6. Review output using hidden reference/rubric access restricted to assigned reviewers. Submit blinded grades, secondary review, adjudication where required and resume interrupted execution exactly once.
7. Inspect evidence-linked findings in the graph and canonical table fallback. Do not present inferred internal reasoning or causal certainty.
8. Review and download the full report/manifest/evidence ZIP, plus one-page PDF/HTML Sales Kit, draft email and internal brief. Fixture origin survives every export.

All business actions persist through API and PostgreSQL. React state/localStorage or JSON fixtures are not substitutes for persistence. Canned candidate responses are allowed only in the explicitly labeled fixture adapter. Seed records must go through application services and record synthetic provenance; do not seed fabricated live approvals or actual model results.

## 3. Screens to implement

| Screen | Essential UI and persisted action |
| --- | --- |
| Login / project chooser | Brand, OIDC login/logout, role/project banner, helpful denied state |
| Objectives | Both origins, hypothesis, measurement plan, review requests and revision-bound approval |
| Case bank / import | Actual/qualified/planned counts; JSON pack validation; file receipt; duplicate detection; gap/rights view; actor/private tabs filtered by role |
| Task / rubric | Output contract, capabilities/family/split, 0–4 anchors/weights, calibration evidence and publish gates |
| Suites / protocols | Exact versions, compatible mode, per-candidate parameters, reviewer assignments, token/time/spend bounds, comparison limitations |
| Providers / models | Adapter readiness, secret-present boolean only, exact model ID, endpoint allowlist, pricing revision, activation and missing-gate checklist |
| Run console | Explicit launch, per-episode status, usage/cost provenance, cancel/reconcile, blocked versus failed versus awaiting review |
| Review inbox | Blinded output, controlled reference access, evidence locators, score dimensions, critical flags and independent adjudication |
| Diagnostics | Read-only Neo4j graph, node inspector, freshness/degraded indicator and PostgreSQL-backed fallback |
| Reports / Sales Kit | Reviewed evidence, honest denominators, version/rights gates, real PDF/HTML/ZIP downloads, email draft only |

The six-view mockup is a visual reference, not the entire screen inventory. Do not make required controls open a generic “coming soon” dialog. Pending integration controls must show why blocked. Search/filter, validation, loading, empty/error states and keyboard access are required.

## 4. Local operating contract

Use project-scoped Compose name `adi-anvil`, local service names/volumes with that prefix, configurable loopback ports: web3200, API8200, Postgres5542, Neo4j7475/7688, Keycloak8180. Check collisions; report and document alternate ports instead of killing another application's processes. Database `anvil_local`; non-owner application credentials plus migration identity, schemas `anvil` and `anvil_checkpoints`.

One pnpm workspace for Anvil-owned TS packages. One Python uv project at `services/backend`, containing installable `anvil` modules and separate API/worker entry points. This deliberately normalizes the older proposed `services/api`/`services/worker` layout to avoid cross-service sys.path hacks; it does not merge the API and worker processes. CI and containers use the same locked versions. Resolve supported patches during M0 and record them, not `latest` image tags.

Infrastructure runs via Compose; web/API/worker may run as local processes for development, with production-style Dockerfiles also supplied. A root launcher must start/stop only these processes and provide meaningful errors. Cloud-ready interfaces are required; actual cloud readiness/IAM/TLS is not claimed.

Required runnable commands, implemented by Codex before recommending them:

| Command | Contract |
| --- | --- |
| `pnpm preflight` | Tools/versions/ports/Docker/permissions/readiness only; no source data or secret values printed |
| `pnpm setup:local` | Idempotent Anvil-only dependencies, infrastructure, migrations and original demo bootstrap; never silently purge |
| `pnpm services:up` / `pnpm services:down` | Start/stop named infrastructure; down preserves volumes |
| `pnpm db:migrate` | Exact Anvil database only; separate migration identity |
| `pnpm seed:demo` | Reusable synthetic project/users and three cases; repeat does not duplicate/overwrite edited records |
| `pnpm dev` | Start web/API/worker, print local URLs, fail if dependency unusable |
| `pnpm check` | Formatting/lint/types/frontend build/backend contracts; nonzero on failures |
| `pnpm test:unit` / `pnpm test:integration` / `pnpm test:e2e` | Network-free candidate fixtures; API/DB/browser assertions, not snapshots alone |
| `pnpm test:smoke` | Morning fixture path, synthetic data only |
| `pnpm test:live -- --dry-run` | Validate provider/config/permissions/budget; no inference |
| `pnpm test:live -- --run-id <approved-id>` | Explicit frozen approved run only; blocked without all gates |
| `pnpm demo:new -- --name <name>` | New isolated demo project for a fresh walkthrough, no deletion/reset |
| `pnpm graph:rebuild -- --project-id <id>` | Authorized canonical projection rebuild, not arbitrary Cypher |
| `pnpm backup:local` / `pnpm restore:test` | Private backup and verification into a new disposable target, never overwrite live DB |

Until the build creates these commands they are requirements, not runnable instructions. No claimed completion from missing-script stubs returning success.

## 5. Accounts and artifact safety

Seed unique local users: researcher, advisor, product-owner, data-engineer, reviewer-1, reviewer-2, adjudicator, sales, admin-1, admin-2, outsider. The outsider has a different test project. Generate local credentials into ignored `.local/demo-accounts.md`, permission-restricted, not predictable production credentials in Git. Login remains OIDC; role switching requires genuine logout/login. Synthetic seed decisions clearly label test origin; distinct IDs do not prove real independent expert judgment.

The core morning path may use trusted repo fixtures by hash, through a local-only loader with explicit UI. General user upload remains quarantined until real scanning works. Never expose “trusted fixture” as a client-controlled bypass on the normal upload endpoint. Provide dry-run errors for missing file, unsafe path, duplicate version, rubric weights and unsupported mode. Native XLSX partner-template parsing is not a night-one requirement; accept the documented JSON interchange and report Excel as a later convenience, not an implemented importer.

## 6. Provider expansion

Implement separate adapters: fixture, OpenAI Responses, Anthropic Messages, Gemini generateContent, Mistral chat completion, Meta Model API Responses, and a restricted OpenAI-compatible chat endpoint for approved open-weight hosting/local serving. Native provider parameters, refusal/blocked states, token limits, usage categories and errors must be normalized deliberately, never assumed identical. No mandatory LangChain model wrapper, gateway subscription or cloud host.

Provider list, environment variables, readiness states and live gate rules are in [05](05-LIVE-EVALUATION.md) and [07](07-PROVIDER-SETUP.md). No API credentials currently exist in this handoff. Mock transport tests are mandatory for each implemented adapter. Each adapter independently reports `specified`, `implemented`, `contract_tested` and `live_verified`; one passing provider does not mark all green.

## 7. Definition of done

The local MVP requires the full happy path, negative access/rights tests, durable review restart, correct score/denominator handling, graph degradation/rebuild, actual one-page PDF and export leakage checks. Map all applicable F-ENG and F-SK baseline criteria to implemented tests. Any missing P0 is an explicit incomplete gate, not removed from the checklist. Live verification is a separate requested outcome and must report `blocked` if secrets/models/budget/approvals are absent.

Eight hours is a work window, not a promise of complete production software. Prefer a verified end-to-end slice, then cover remaining criteria; never sacrifice controls to finish more screens. The morning report must separate working, partially built, blocked and unimplemented features. No production-ready or scientific-validity claim follows from demo acceptance.
