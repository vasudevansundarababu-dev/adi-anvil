# Morning acceptance — user walkthrough

These are expected tests for the application Codex will build. They are not run instructions for the current documentation-only folder. First read `docs/generated/morning-report.md`; if setup or a required step is missing, record failure rather than assuming the mockup represents the application.

Estimated hands-on walkthrough: 45–60 minutes after a successful build. Live provider setup and real independent approvals can take longer. Run the happy path first, then negative checks. All examples are synthetic.

## Start and sign in

Use the exact commands/ports recorded by the build agent. Required intended contract: `pnpm preflight`, `pnpm setup:local`, `pnpm dev`. The final build must have tested these; do not run a command that remains an unimplemented requirement. Default web URL is http://127.0.0.1:3200, not the older port4186 static mockup.

Read `.local/demo-accounts.md` locally for generated development credentials. Do not paste credentials into Codex. Log in/out between roles; no unrestricted role-switch menu. Use a fresh demo project if the overnight test suite has already exercised the original records.

## MORN-01 — Create a research objective

As Researcher create “Synthetic commercial-constraint diagnostic,” origin ADI-initiated, capability-led. Hypothesis: supplied hard constraints are preserved in recommendations. Measurement plan: three original cases; two deterministic fixture candidates; one attempt each; anchored rubric and critical overrides; descriptive results only. Submit, have Researcher and Advisor recommendations and distinct Product Owner scope approval recorded. Reopen/reload: all state persists; audit identifies exact version.

Expected: objective approved only after the required quorum. Attempting self-approval through another role on the same user must fail. Synthetic role exercises are not genuine expert validation.

## MORN-02 — Import, qualify and publish three cases

As Data Engineer use Import built-in synthetic cases, choosing MKT-001, FIN-001 and STR-001. Inspect actor prompt/exhibit and separate private reference. Check each case has source ID/version, family, three capability mappings, rights/readiness and rubric. Complete synthetic content/research/calibration reviews with the appropriate distinct test users, then publish.

Expected: 3 actual cases and 3 families; target200 remains a planned portfolio number. The fixture rights scope permits only the local demo path, not an arbitrary external provider. Reimporting the identical sample does not add three new cases. No real faculty/partner review is claimed.

## MORN-03 — Run a correct and failing candidate end to end

Create a custom suite from those three exact published versions. Create a fixture protocol with both fixture candidates, one repetition, explicit test rubric/pass threshold, reviewers and frozen versions. Review/approve the protocol, then press Launch. No live credentials required; no paid approval is fabricated for a network-free fixture.

Expected: 6 episodes reach output captured/awaiting review through LangGraph. The run is illustrative, not measured model performance. Inspect one response:

| Case | Correct final choice | Constraint-blind final choice | Why the latter fails |
| --- | --- | --- | --- |
| MKT-001 | 10% discount | 20% discount | 25% gross margin is below the 30% floor |
| FIN-001 | Offer A | Offer C | USD400,000 is below required USD500,000 funding |
| STR-001 | North | West | USD125,000 launch investment exceeds USD120,000 budget |

## MORN-04 — Human grading and review recovery

As assigned Reviewer1 inspect references/outputs without model identity where practical. Use the supplied fixture test vectors: correct 4/4/4; constraint-blind 4/0/4 plus the case critical violation. Submit independent Reviewer2 judgments where required; pilot calibration/critical cases need required additional coverage. Disputes go to the distinct adjudicator, never averaged away.

Before one final review is submitted, stop and restart only the Anvil worker using the documented command. Return to the pending review and complete it. Expected: pending state survived, no extra candidate invocation, one successful resume, same original output. Do not stop unrelated processes.

Expected after all six scripted judgments: correct scores100, bad scores70/critical fail; 3 passes/3 failures, valid denominator6, mean85. Manual grades may differ legitimately; the UI must compute from submitted grades, not force these expected scores. Pending or missing grades never become zero.

## MORN-05 — Diagnostics and graph

Create/review a finding for the promotion margin violation, linking the output span and criterion R2. Open Diagnostics → capability Constraint preservation → linked task/episode/finding. Confirm exact IDs/versions and human-review status. Observation is the constraint violation; internal causal reasoning remains unknown.

Expected: graph nodes resolve to permitted canonical records. Stop only Anvil Neo4j, refresh: degraded state and table fallback appear; case/review/report data remain accessible. Restart/rebuild: links return without duplicates and scores unchanged.

## MORN-06 — Report and one-page Sales Kit

Draft a report from the six reviewed fixture episodes. Technical/domain reviewers and Product Owner complete exact-version audience/release approvals. Download the report HTML, CSV, JSON/ZIP and Sales Kit PDF/HTML/email draft as the permitted role. Open the actual files.

Expected: PDF exactly one readable page with logo/tagline; custom suite, synthetic source/illustrative execution labels and honest denominators. No hidden reference, raw restricted case content, credentials or internal brief in the external one-pager. Email sending remains disabled. An internal fixture export can be downloaded for testing but is not an approved real customer delivery. Changing a finding/score invalidates stale kit approval and creates a new version.

## MORN-07 — Safety and negative checks

| Action | Expected result |
| --- | --- |
| Sales opens a hidden-reference URL or grading API | Denied; no bytes/score mutation |
| Outsider guesses another project's object ID | 404/no content disclosure |
| Import MKT without the exhibit | Missing-input blocker; no candidate failure |
| Change exhibit while retaining same case version | Conflict; original bytes unchanged |
| Require interactive mode for STR | Unsupported adapter blocker |
| Register provider without key/model/budget | Not configured; no inference request |
| Launch/resume same command twice with same key | Same operation, no duplicate candidate dispatch |
| Trigger grading disagreement | Independent adjudication required |

Use dedicated new fixture projects/versions for these checks; do not modify the six final test episodes to force negative states.

## MORN-08 — Real models, once enabled

Follow [provider setup](07-PROVIDER-SETUP.md). Add credentials locally, select exact available model IDs and approve a total budget. Complete distinct-Admin activation/paid-scope approvals as actual authorized people, not the build agent. Freeze a new live protocol with only permitted actor input from the original three cases. Run dry preflight, then explicitly launch one case on one model. Inspect usage/output before expanding to at most 3N initial calls across N approved models.

Expected: actual provider request/model metadata where available; synthetic source with real execution origin; no predetermined response substitution; honest unknown costs if not returned/reconciled. Human scores are not predicted in advance. Results from different harness/settings must not be ranked without a declared comparison policy. No live run should have happened overnight if these prerequisites were absent.

## Acceptance record

For each MORN-01–08 record build/commit, date, tester, status (pass/fail/blocked/not run), expected/actual, redacted evidence and defect ID. MORN-08 blocked for no keys is not a pass. Overall local demo acceptance is separate from all baseline security gates and production/research validation. Ask Codex to fix observed failures using the actual evidence; do not rerun a destructive reset as a default remedy.
