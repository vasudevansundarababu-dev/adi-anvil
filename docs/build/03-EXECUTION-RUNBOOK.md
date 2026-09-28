# Eight-hour execution runbook

The clock starts when the user launches the build, not when this document was created. Record start time and eight-hour stop time in BUILD-STATUS.md. Finish earlier if complete; do not sleep to fill the window. Do not promise the IDE will remain running through sleep, quota exhaustion, approvals or network outages.

## Milestones and gates

Time ranges are planning allocations, not guaranteed completion times. Build the smallest complete slice within each milestone before expanding breadth. Read relevant product contracts at each stage; do not rely on memory after compaction.

| Milestone | Planning allocation | Build | Exit evidence |
| --- | --- | --- | --- |
| M0 | 0:00–0:40 | Tool/port/permission preflight, local Git, dependency lockfiles, root scripts, Compose | Version inventory; no sibling changes; named services healthy; offline candidate mode default |
| M1 | 0:40–1:40 | OIDC/session/RBAC/RLS, schema migration, private artifact boundary, branded shell | Genuine login; logout/session revocation; cross-project/role negatives; durable create/reload |
| M2 | 1:40–3:00 | Objective reviews, JSON case/file intake, rights/gaps, rubric/task/suite/protocol revisions | Fresh synthetic case import → review/publish → frozen fixture protocol; duplicate/version/gap blocks |
| M3 | 3:00–4:20 | PostgreSQL queue and LangGraph/checkpointer, fixtures, review/adjudication/resume | Good/bad responses scored correctly; worker restart at review; idempotent launch/resume; no private inputs leaked |
| M4 | 4:20–5:05 | Findings, outbox/Neo4j projection, graph inspector, fallback | Exact links; cross-project denial; graph outage/rebuild tests |
| M5 | 5:05–6:00 | Reports, authorized ZIP, PDF/HTML Sales Kit and email draft | Real downloaded files; exactly one-page PDF; immutable content hashes; honest origin/denominators; leakage tests |
| M6 | 6:00–7:00 | Requested provider adapters/config UI and mocked request/response suites; live preflight | Per-adapter contract results; actual paid smoke ONLY if all gates supplied; otherwise explicit blocked evidence |
| M7 | 7:00–8:00 | Integrated test/repair, fresh startup, accessibility, secrets/dependency checks, docs | Morning report with true status, test matrix, URLs/accounts path and next action; no surprise external effects |

Eight hours may not complete all baseline P0s and six provider integrations. If a milestone takes longer, update ETA/remaining scope honestly. At seven hours, prioritize cross-layer verification and fixing broken core paths; do not delete missing criteria to make the report green. A provider whose SDK compatibility cannot be established stays visibly unavailable, not routed silently to another model.

## Durable work loop

For every milestone: inspect current status → implement bounded change → run relevant unit/integration/browser checks → repair failures → rerun → record exact command/result/commit → make safe local checkpoint → continue to next milestone. The older “ask before each phase” wording does not apply to this user-authorized overnight run.

Update BUILD-STATUS.md after each milestone, important failure or architectural decision. Keep `docs/generated/test-matrix.md` with requirement ID, test name, expected result, actual status, commit and evidence path. Record not-run and blocked tests. Do not accept skipped security tests as passes.

If interrupted, inspect Git status and BUILD-STATUS, run the last smoke check, and resume the next incomplete gate without resetting history. Reuse valid work; do not regenerate the project or reinstall globally. Record versions and any migration already applied before attempting recovery.

## Preflight before unattended work

Read-only checks: Node/pnpm/Python/uv/Git versions, Docker daemon and Compose, free ports/disk, supported local architecture, VS Code workspace trust and granted repository/network permissions. The user's report that Docker works is not a substitute for checking the actual execution shell.

Dependency installation/build-image pulls may need network, cache or Docker socket permission. Resolve those prompts while the user is present. Use repository-local dependencies/caches where practical. Do not change global Codex approval settings or disable sandboxing. OS or organization restrictions can still stop the run; a prompt cannot override them. If missing prerequisites require a global install, pause that dependency and tell the user precisely what is missing.

The user should keep the machine powered, awake and VS Code running. Do not change sleep/security/system settings automatically. Never install a cron job, self-relaunch loop or account-switching workaround for usage limits. Provide a resume prompt instead.

## Stop conditions and safe alternatives

- Missing API credentials/model/budget: continue fixture journey and mocked adapters, not live dispatch.
- Missing independent real paid approvals: continue local development; do not impersonate two Admins to approve cost.
- Docker unavailable: source/unit work may continue; integration and complete-local-app status remain blocked. No SQLite substitution or fake successful startup.
- Scanner unavailable: trusted original fixture route only; general uploads stay quarantined.
- Graph unavailable: canonical workflow can continue and show degraded graph; no graph test falsely marked passed.
- Permission/security/contract ambiguity: record it and continue unrelated safe work. Do not bypass policy because the user is asleep.
- Test failure: fix product or test defect with rationale; never weaken a requirement or hardcode expected UI results just to pass.
- Work-window reached or all feasible work finished: stop dispatching work, leave durable records and report.

## Required morning report

Create `docs/generated/morning-report.md` and `.json` with: overall status (`complete_local`, `partial`, `blocked`); live verification separately; implemented routes/modules; commit/versions/start/end; exact setup/run commands actually tested; local URLs; credential-file location without values; three case IDs and expected outcomes; passed/failed/blocked/not-run tests; API spending (actual if known, otherwise unknown—not zero); unresolved issues; data/volume safety; next steps. Include representative screenshots and report/PDF paths under ignored test artifacts.

Do not send this report anywhere. The user will inspect it locally. Creating a report or finishing a build does not authorize GitHub publication.

## Guidance basis

This handoff uses durable specifications, milestone verification and saved status records, following the pattern described in [OpenAI's long-running Codex guidance](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex). Workspace and network permissions remain enforced independently of the prompt: [official approvals guidance](https://learn.chatgpt.com/docs/agent-approvals-security). These sources do not guarantee eight-hour uninterrupted execution or production readiness.
