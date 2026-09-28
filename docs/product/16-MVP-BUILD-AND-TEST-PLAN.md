# ADI Anvil — MVP v1.0 Build Sequence and Acceptance Plan

Version: 1.0 · 27 September 2026 · Coding handoff, not implementation authorization or test results

Read [the engineering specification](14-MVP-V1-ENGINEERING-BUILD-SPEC.md), [contracts](15-MVP-DATA-AND-API-CONTRACTS.md), [brand handoff](17-ANVIL-BRAND-AND-UI.md) and [Sales Kit extension](18-AUTOMATED-SALES-KIT-SPEC.md). All tests below are **specified, not executed against an application**. The HTML mockup is a local design demonstration only.

## 1. Delivery strategy

Build one tested vertical slice before expanding case count. Use independently owned frontend/backend/database, user-selected LangGraph, PostgreSQL and the recommended Neo4j projection. Start with synthetic fixtures; no need for Bodhium source access, provider credentials or GPU to develop the workflow. Do not convert synthetic fixture grades into scientific results.

The user's latest direction defers advanced TNG/TTM/learned-planning specification to a later version pending further reading and their input. LangGraph remains the v1.0 orchestration choice. Do not invent a transition model or full graph editor as a substitute for that missing future specification.

### Phase 0 — Confirm build baseline and isolate the project

Deliver repository-local architecture decisions, dependency lockfiles, `.env.example` containing variable names/placeholders only, independent names/ports, formatting/lint/typecheck/test commands and local infrastructure definition. Resolve actual mutually compatible package patches, security advisories and Neo4j edition/license constraints; record versions rather than copying Praxis's lockfile. If the user requests Git, initialize this folder independently and confirm the intended remote before publishing. Do not modify sibling projects.

Environment variables to document: `ANVIL_ENV`, `PUBLIC_ORIGIN`, `API_ORIGIN`, `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `CHECKPOINT_DATABASE_URL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD_FILE`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET_FILE`, `ARTIFACT_ROOT`, `MALWARE_SCANNER_ENDPOINT`, `ANVIL_LIVE_PROVIDERS_ENABLED=false`, `ANVIL_FIXTURE_MODE=true`, approved provider key-file reference only if activated. Disable external LangSmith tracing by default. No real secret in an example, screenshot, artifact or commit.

Exit: clean independent build with no sibling import; local services healthy; no provider call during startup/migration/seeding.

### Phase 1 — Brand, identity and trusted foundations

Implement Next.js/React/Tailwind shell using Anvil's own design tokens, full logo on login and accessible live text in navigation. Add OIDC, project membership, roles, CSRF, session revocation, scope checks, version/ETag middleware, redacted audits, artifact quarantine and typed errors. Provision local test identities for all separated roles without treating them as production identities.

Exit: a Researcher can sign in and see only an assigned project; Sales cannot access hidden materials by URL/API; another project ID returns 404; logout invalidates API access; theme and keyboard paths work.

### Phase 2 — Objective → case → qualified suite

Implement objective revisions/reviews; requirements; case manifest dry-run/import; rights/readiness; immutable originals; enhancement revisions; rubric and calibration review; family/capability mapping; suite freeze. Source rights remain unknown by default. Scanning integration may initially be tested with controlled clean/malicious fixtures, but real uploads remain blocked until actual scanner qualification.

Use three original synthetic illustrative cases matching the mockup, not a fabricated Bodhium delivery. Add a generated 200-case **load-test-only** inventory whose count is never advertised as 200 expert-authored tasks. Group variants into families and deliberately include duplicates, revoked rights, missing references and unsupported modes.

Exit: one synthetic task reaches published status through distinct reviewers; blocked tasks cannot enter an executable frozen suite; repeats and family IDs remain distinct from case counts.

### Phase 3 — LangGraph evaluation and durable review

Implement protocol review, cost/approval ledger, PostgreSQL job leases, typed LangGraph graph, persistent PostgreSQL checkpointer and `fixture_static_v1`. Exercise complete, refused, malformed, operational error, unknown execution, interrupted review and cancellation fixtures. Resume through authenticated review decisions, not generic checkpoint APIs. Pin graph version per thread.

Add the optional single-response provider adapter behind a disabled-by-default feature flag and contract tests with mocked responses. Do not run it with a real key unless separately authorized. The feature is not ready for real cases until actual capability, pricing, data permission and approval gates pass. External-result import supports lab-owned models without requiring direct endpoint access.

Exit: interrupt/restart/resume preserves the episode and reviewer decision; duplicate launch/resume creates no duplicate inference; crash after dispatch cannot cause an unapproved retry; no hidden reference in candidate state or request.

### Phase 4 — Adjudication, diagnostics and Neo4j

Implement anchored grading, blind reviews, mandatory secondary sampling, disputes/adjudication and evidence-linked findings. Add typed canonical graph relationships, transactional outbox, Neo4j projector, bounded authorized traversal and table fallback. Demonstrate graph rebuild from canonical records and graceful graph outage. No planner learning, full TNG editor, automatic causal graph or memory transfer between protected cases.

Exit: numeric fixture score, critical override, missing-data and dispute cases agree with expected results; graph links resolve to exact versions and respect project/visibility; graph outage cannot change an approval or score.

### Phase 5 — Reports, releases and local pilot readiness

Build static escaped report HTML/Markdown, scorecard CSV and versioned manifest/evidence ZIP. Complete technical/domain/audience review, release approval and authorized download. Correct a released fixture by supersession/revocation, not overwriting files. Test backup/restore across PostgreSQL, artifacts and checkpoints; rebuild Neo4j. Measure performance on the declared local hardware and fixture size.

Implement automatic Sales Kit draft/refreshed-version jobs, exactly-one-page branded PDF/accessible HTML, email draft, internal briefing, content/recipient approval, and idempotent fixture email dispatch. Include all F-SK tests in the Sales Kit specification. Real sending stays disabled until separately authorized sender/credentials/recipients are configured; a generated kit never grants send authority.

Exit: an authorized user completes the full synthetic workflow locally; required P0 tests pass with recorded evidence; scientific/customer readiness is labeled separately. No cloud deployment, external email or Notion update follows automatically.

## 2. Required acceptance tests

All are P0 release gates unless explicitly called P1. Each test must record build ID, dependency/DB versions, fixture IDs, executor, time, expected/actual result and evidence. A screenshot does not substitute for an API/database assertion. Tests must fail when the corresponding guard is intentionally removed.

### Access, versioning and data boundaries

- F-ENG01: Expired/revoked session and invalid OIDC state/nonce/audience are denied; a reused login callback fails.
- F-ENG02: Cross-project UUID substitution fails on list/detail/artifact/review/graph/export/job/resume endpoints; response does not expose existence or content.
- F-ENG03: Role checks survive direct API use. Sales cannot alter grades or read references; a platform Admin without content role cannot read case bytes.
- F-ENG04: CSRF and wrong-origin mutation requests fail; authenticated GET never starts a run or export build.
- F-ENG05: Stale ETag edit fails with 412; same idempotency key/body replays original result; changed body conflicts.
- F-ENG06: Submitted revisions cannot be edited; changed source/rubric/model/prompt makes old approvals inapplicable to the new revision.
- F-ENG07: One person holding multiple roles cannot satisfy separated recommendations, approval, paid quorum or dispute adjudication.
- F-ENG08: Cross-project FKs, missing tenant context and pooled connection context leakage fail database-level tests with non-owner application credentials.

### Intake and qualification

- F-ENG09: Dry-run manifest validation creates no case records; partial failure returns row errors; commit is atomic and duplicate delivery does not inflate count.
- F-ENG10: MIME mismatch, executable/macro file, path traversal, decompression bomb, oversized file and unavailable scanner remain blocked/quarantined. Test without executing uploaded content.
- F-ENG11: Original bytes/digest are unchanged by enhancement; a derivative cannot inherit faculty-reviewed status without its own matching review evidence.
- F-ENG12: Unknown/revoked/expired external processing rights block live dispatch; separate raw redistribution and training permissions block those exports.
- F-ENG13: Missing exhibits/reference/rubric/calibration or unsupported interactive mode blocks qualification/execution; no false model failure is created.
- F-ENG14: Case/source/task/family/variant/episode counts stay distinct; related-case split conflict blocks suite freeze.
- F-ENG15: Hidden references are absent from actor artifact resolver, provider payload, LangGraph candidate state, routine logs and unauthorized graph responses.

### LangGraph, queues and spending

- F-ENG16: Fixture execution is deterministic and network-free; all downstream outputs remain illustrative, even after human review/export.
- F-ENG17: Two distinct active Admin approvals bind exact provider/run/destination/ceiling; expiration, rights revocation or configuration change prevents dispatch.
- F-ENG18: Concurrent launches reserve no more than the allowed ceiling and enqueue one operation per idempotency key; unknown pricing fails closed.
- F-ENG19: Kill worker before dispatch, after dispatch and after output persistence. Only safe stages retry; ambiguous paid call becomes execution_unknown with no duplicate inference.
- F-ENG20: Expired lease cannot commit with stale token; graph/checkpoint completion never substitutes for canonical provider reconciliation.
- F-ENG21: Human-review interrupt survives process restart; authorized final decision resumes exactly one pending thread; duplicate/stale/wrong-project resumes fail or replay safely.
- F-ENG22: Reviewer decision cannot inject arbitrary LangGraph state, access another thread's checkpoint or re-execute a cancelled episode.
- F-ENG23: Graph code/version mismatch blocks resume unless an explicitly tested migration path is selected; recursion/time/token caps yield visible terminal or blocked state.
- F-ENG24: Cancellation prevents new dispatch and accurately labels uncertain in-flight work; UI never claims confirmed provider cancellation without evidence.
- F-ENG25: Actual provider cost absent remains unknown, not zero; estimated/reserved/reconciled amounts remain separately labeled.

### Scientific validity and diagnostics

- F-ENG26: Rubric weights must total 10,000; every 0–4 anchor exists; missing judgments do not silently become zero or dynamically change weights.
- F-ENG27: Fixture dimensions at weights 6000/4000 and scores 4/2 produce 80.00; a critical violation still fails; threshold 85 produces fail without a violation. These numbers are test fixtures, not a real rubric.
- F-ENG28: Reviewer 2 cannot see reviewer 1's unfinished grade/model identity; prescribed disagreements require an independent adjudicator rather than averaging.
- F-ENG29: A valid alternative solution receives credit; ambiguous reference triggers review/invalidity rather than automatic candidate failure.
- F-ENG30: Report denominators include a visible accounting for launched, completed, unknown, invalid and unscorable episodes. Null/zero-denominator scores render N/A, never 0%.
- F-ENG31: Imported results retain original execution origin through ADI review; final-only output cannot manufacture missing action trajectories.
- F-ENG32: Report cannot claim GDPval, school endorsement, MBA human baseline, causal internal reasoning or improvement without corresponding registered evidence.

### Neo4j and release

- F-ENG33: Replay duplicated and out-of-order outbox events; graph remains duplicate-free and latest-version correct without skipping a failed watermark gap.
- F-ENG34: Every graph hop enforces project/visibility; a tombstoned canonical record disappears immediately from graph API responses even before asynchronous deletion.
- F-ENG35: Neo4j outage degrades only graph exploration; canonical CRUD/grading/reporting remains correct; fallback identifies projection unavailability.
- F-ENG36: Rebuild a projection from PostgreSQL and compare expected nodes/edges/version digests; checkpoint DB is not used as the knowledge graph.
- F-ENG37: Export excludes hidden references, private source files, secrets and protected learning content without specific permission; reject unsafe ZIP paths/HTML/CSV formulas.
- F-ENG38: Revocation after pack generation prevents a new download; an old release remains auditable and a correction receives a new version/hash.
- F-ENG39: Local backup restore recovers canonical evidence and pending LangGraph review; graph reconstruction and artifact checksum verification succeed.
- F-ENG40: Independent Anvil build/test passes with sibling project paths unavailable; no mandatory `@praxis/shared`, Enterprise service or shared credentials.
- F-ENG41: At 320px/768px/1440px and both themes, core tasks are keyboard operable, labeled and legible; no global horizontal overflow, clipped approval controls or color-only statuses. Table-local scrolling is acceptable.
- F-ENG42: Development fixture keys, identity bootstrap and scanner bypass are refused by non-local configuration. No live provider call occurs during CI, health checks or seed startup.

P1 performance targets to validate, not measured claims: 200 source-case inventory with related versions; list/detail p95 under 500ms excluding file bytes/provider calls; graph depth≤3/≤200 nodes under 2 seconds; UI responsive during a 400-episode fixture batch; worker restart recovers safe queued work within 90 seconds. Record CPU/RAM/disk, concurrency and sample duration. Failing performance targets requires tuning or an explicit accepted limitation, not invented capacity claims.

## 3. CI and local developer contract

On each proposed change: format/lint → frontend typecheck/build → backend types/schema checks → unit tests → PostgreSQL/Neo4j integration tests → LangGraph restart/interrupt tests → API contract snapshot check → browser E2E with fixture adapter → dependency/secret scan. GitHub Actions is a proposed CI runner once a repository is authorized; use no production secrets in pull-request jobs. Pin actions and service images; protect deployment separately. No live model smoke tests in normal CI.

Developers must expose documented commands equivalent to `dev`, `services:up`, `db:migrate`, `db:seed:fixtures`, `test:unit`, `test:integration`, `test:e2e` and `check`. The scaffold must implement those commands before telling the user to run them. This document does not claim they exist today. Local `down` must not delete volumes by default; reset/purge requires an explicit destructive-operation warning and exact target.

Migration order: identity/projects → artifact/version/review core → objectives/cases/rubrics → suites/protocols/runs/jobs/budget → assessments/findings/reports/releases → graph outbox → controlled LangGraph saver setup. Run migration/rollback tests on disposable fixtures; backup and forward-fix strategy before real data. Existing unrelated databases are never migration targets.

## 4. Historical incremental prompt — superseded for this overnight build

Do not execute the historical prompt below for the overnight build. Use [the current launch prompt](../../CODEX-OVERNIGHT-PROMPT.md) and [all-milestone runbook](../build/03-EXECUTION-RUNBOOK.md). The quoted text is retained for provenance only; its phase-0–1 restriction, old local Git restriction and per-phase user-request sequencing are superseded. External publication/spend gates remain in force.

```text
Build the first approved implementation slice of ADI Anvil in this independent
project. Read AGENTS.md and README.md, then docs/14-MVP-V1-ENGINEERING-BUILD-SPEC.md,
docs/15-MVP-DATA-AND-API-CONTRACTS.md, docs/16-MVP-BUILD-AND-TEST-PLAN.md and
docs/17-ANVIL-BRAND-AND-UI.md and docs/18-AUTOMATED-SALES-KIT-SPEC.md before editing.

Product: ADI Anvil — Frontier Evaluation & Diagnostics Platform.
Frontend: Next.js, React, TypeScript and Tailwind; match the inspected Praxis
design family using Anvil-owned files. Do not import sibling ADI packages.
Agent orchestration: Python LangGraph with PostgreSQL-backed checkpoints.
Canonical operational database: PostgreSQL. Relationship projection: Neo4j.

Begin with phases 0–1 only: isolated scaffold, compatible pinned dependencies,
local services, identity/RBAC/audit foundations and the branded app shell.
Use synthetic fixtures only. Implement documented commands and verify them.
Show a bounded plan, then implement and test this slice; report exact changes,
tests passed/failed/not run, remaining gates and instructions to run locally.

Do not build TNG/TTM learned planning, full graph authoring, optimizer/training
services, Tinker/H100 management, Enterprise deployment or a duplicate Praxis
SME workbench. Do not fabricate real cases or performance data.
Do not initialize/push Git, deploy cloud resources, send email, update Notion,
use real source material, install paid services or call live models without
the corresponding explicit authorization. Preserve existing unrelated edits.
```

For the current authorized overnight run, proceed through all applicable milestones with test gates and recorded decisions. Do not create new user tasks or silently expand permissions.

## 5. Decisions still needed before real operations

Named review/approval/release owners; permitted partner sample and actual rubric inputs; first real model/agent interface; actual data-destination terms/pricing; project retention; expected customer acceptance; production identity/hosting/graph edition. These do not prevent local fixture-based development. Source rights, faculty validation, partner investment and revenue commitments remain unverified/unagreed unless separately supplied.
