# Policy evaluation implementation progress

## Current integrated delivery

The foundation-only remaining list below is historical. The current local implementation connects import/persistence/extraction, saved mappings, plans/Run snapshots, separate durable capture/assessment, all seven dashboard views, remediation sample exports and actual PDF reports. Current evidence, preview and remaining external qualification boundaries are in `benchmark-integrated-handoff.md`. Current source is a local checkpoint; the earlier remote PR head is not evidence of a missing local implementation.

## Authorization and handoff

On November 9 the user approved the final design and requested a detailed Praxis coding handoff, QA changes for both products, then Anvil implementation. The isolated Anvil checkout is the only product repository being edited. Praxis changes are specified for its independent team; its repository and the original dirty Anvil checkout remain untouched. No deployment, merge, external handoff message, cloud change or live paid call is authorized by this launch.

Normative target: product specifications 34 and 35. The rendered four-page implementation Word document and three-page QA Word document, versioned schema and fictional examples are in `Documents/Codex/anvil-dashboard-design-review/output/praxis-handoff-v2`. The handoff ZIP is `output/Praxis-Anvil-Coding-Handoff-v2.zip`. QA is to create separate Praxis, Anvil and cross-product suites, trace each case to requirement IDs, and include negative cases and evidence requirements. The documents specify the full target; they are not a completion claim.

## Implemented foundation

- Optional strict Project-policy sidecar validator, exact file/Task/Project binding and candidate-safe instruction projection. Existing legacy export untouched.
- Additive migration064: project-scoped append-only evaluator configurations, validation receipts and revocations; actual author binding and forced RLS.
- Both Admin and RL Engineer configure and test without an extra approval queue. API keys use existing encrypted storage, recent authentication and secret-free idempotency records.
- Evaluators administration screen saves configurations and tests known Pass/Fail/Unknown cases. Ready is configuration/source/runtime-bound; revoked, absent runtime and untested configurations are explicit.
- Actual ZEN2.1.3, checksum-qualified local OPA1.22.2, NeMo0.24.1 literal checks and Promptfoo0.125.1 literal assertions. Model-based rails are not deterministic custom-policy compliance.
- Bounded exact Arthur prompt-validation and Openlayer existing-test evaluation API contracts. Contract-tested does not mean account/live-verified. Openlayer queue acceptance is Not evaluated, never Pass. No live-dispatch route is enabled.
- Independently locked NeMo and TruLens environments; TruLens2.16.0 precision/calibration worker is tested as a metric, not a custom-policy verdict. No model weights downloaded or providers called.

## Validation and retained failures

Foundation full offline suite930 PASS, including actual OPA and ZEN checks. Earlier empty-source-root collection error,33 socket/fixture-setup failures and subsequent927PASS/3helper-import errors are retained as setup history. Corrected whole suite passed930; no product guard was relaxed.

First real SQL run exposed a PLpgSQL table-specific record lookup bug (4FAIL/1PASS); corrected. The five focused SQL/API tests then passed on a second fresh schema. Expanded four-local-adapter/both-role suite passed11 on a fresh schema. Final five-local-adapter/both-role suite passed13 from a fresh64-migration schema, including actual pinned OPA CLI, ZEN, NeMo and Promptfoo runtime checks, revocation, cross-project denial and immutable history.26 existing dashboard/result/rehearsal Node contracts, current types, Ruff and diff checks passed. The930-unit/build result is the foundation predecessor; later adapter extensions are focused delta evidence, not a full successor qualification claim.

Actual NeMo allowed/forbidden/missing library cases3 PASS; actual TruLens measured/missing/undefined/mismatch cases4 PASS. These are software integration checks, not model performance. Arthur/Openlayer/OPA wire contracts use MockTransport. Historical application native evidence is not current qualification.

Final focused parser/rule/HTTP contracts68 PASS, zero failures/skips, including numeric interoperability bounds, strict upstream duplicate-JSON rejection and actual OPA. Final configuration delta13 PASS after the numeric change; owned QA container stopped again and data retained. Final expanded frontend Next16.4.1 production build and Ruff PASS. Source hashes and exact evidence categories are in `policy-evaluator-adapters-evidence.json`; the whole930-unit result remains predecessor evidence. A public-file-only secret-pattern scan checked997 source files with zero findings; no private credentials were read for that scan.

Types and production build passed after independently synchronizing the committed frontend lock to actual Next16.4.1. Initial build used stale installedNext16.3.6 and is not locked-release evidence. Build-generated next-env declarations were restored to the original tracked form. New Evaluators browser QA and native requalification have not run.

## Runtime ownership

Only new owned QA container `anvil-evaluator-sql-20261109` and its fresh databases are used. Private test configuration remains under `/private/tmp/anvil-evaluator-sql-20261109`; never copy credentials into reports. Local isolated environments are `/private/tmp/anvil-evaluators-20261109-venv`, `anvil-nemo-evaluator-20261109`, `anvil-trulens-evaluator-20261109`; actual OPA binary/installation checksum is in `/private/tmp/anvil-evaluator-tools-20261109`. Existing previews50678/50679 and older local services are untouched.

## Remaining at the historical foundation milestone

This milestone is not the full approved dashboard release. Remaining: actual sidecar import/persistence/extraction screens; saved policy mapping and Task/environment compatibility; execution-group/Run snapshots and evaluator worker integration; selected/used evaluation views and task-level safety evidence; six-axis charts, persistent context/export fixes, remediation and complete PDF changes; browser and independent QA. Final API-key testing needs exact service/resource/budget and user-supplied keys. Willingness to buy a small API allowance is not a fabricated spending authorization.

Fiddler Auditor0.0.5 pins older Jinja/OpenAI dependencies and uses Elastic licensing. Phoenix Evals3.9.5 also uses Elastic licensing. Do not label those permissive open source or silently bundle an incompatible stack. Pramaana's supported API contract remains unverified. Archived LLM Guard remains unavailable. Catalog names alone must never become Ready Run options.
