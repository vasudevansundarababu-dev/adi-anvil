# Policy evaluation QA change matrix

Version 2.0 · 9 November 2026 · Based on specification 34

## Replacement assumptions

Retire tests requiring three reviewers, Admin-only new evaluator configuration, mandatory custom policies, evaluators installed in Praxis, arbitrary runtime package installation, AI judgment as deterministic compliance, or every integration producing a comparable score. Preserve project isolation, current immutable history, existing paid-call controls and real report-review records. No live provider calls belong in default CI.

## Praxis acceptance cases

- PRX-Q01 / PRX-01,05: Save and export a Project with no policies. Existing v1 Tasks remain byte/hash-identical; custom checks are N/A, normal tasks unaffected.
- PRX-Q02 / PRX-01,04: Pasted UTF-8 text, TXT, Markdown, PDF and DOCX preserve exact source bytes/hash and separate extraction status. Broken extraction retains original and displays a clear error.
- PRX-Q03 / PRX-02: Project default applies to all selected member Tasks. Task additions and explicit exclusions are versioned; contradiction is displayed, not silently overwritten.
- PRX-Q04 / PRX-03: Save document-only policy with zero rules. Export succeeds; Anvil shows Needs testable rules, not Pass.
- PRX-Q05 / PRX-03,10: Public agent instruction and evaluator-only expected outcomes remain separate; candidate projection contains no private test goals or reference answers.
- PRX-Q06 / PRX-04: Editing creates a new policy version; previous export/source bytes remain retrievable. Author metadata does not create an approval.
- PRX-Q07 / PRX-06,07: Legacy export.v1 rejects appended unknown fields. Policy attachment uses its own explicit schema version and source Project identity.
- PRX-Q08 / PRX-08,09: Duplicate same-version identical imports are idempotent. Changed hash under same identity/version conflicts.
- PRX-Q09 / PRX-08,09: Missing Task/version/hash, cross-Project reference or deleted Task binding is rejected with its field path.
- PRX-Q10 / PRX-09: Reject unknown schema, duplicate keys/IDs, absolute/traversal/alias paths, oversized inputs, hash mismatch and credentials/executable fields; no partial Ready state.
- PRX-Q11 / PRX-01,05: Actual Admin and RL Engineer can author; outsider/cross-Project users cannot. No role-switch UI or new approval request is used.
- PRX-Q12 / PRX-10: Malicious text in a policy attachment never executes commands, changes configuration or authorizes network access.

## Anvil integration and API cases

- ANV-Q01 / ANV-01: Both actual roles can configure/test new integrations in an authorized Project; cross-Project/unauthenticated/CSRF writes fail. Unrelated Admin permissions remain unchanged.
- ANV-Q02 / ANV-02,03: Registry entry alone is unavailable. Missing package, incompatible version, absent artifact, missing credentials, auth failure and failed fixture tests cannot produce Ready.
- ANV-Q03 / ANV-03: Real Pass/Fail/Unknown configuration fixtures exercise each claimed capability. HTTP200 with wrong JSON or zero checks is not success.
- ANV-Q04 / ANV-03,13: Rotation, adapter changes or runtime health failure invalidate new work; frozen historical reports retain original identities and results.
- ANV-Q05 / ANV-04: Each shipped open-source adapter has actual package/runtime version evidence and a runnable focused test. Uninstalled/archived libraries remain unavailable. No fake binary or local imitation counts as the upstream engine.
- ANV-Q06 / ANV-04,10: Imported policies cannot install packages, load arbitrary modules, run commands, pull models/images or acquire host sockets.
- ANV-Q07 / ANV-05: Model-based/mixed rails, orchestration and trace capture cannot satisfy a deterministic policy requirement. Capabilities are checked per configuration, not provider brand.
- ANV-Q08 / ANV-06,07: At least two documented API adapters preserve exact path/body/header semantics with MockTransport contracts; redirects, timeout, 401/403/429/5xx, oversized/malformed/unknown results and ambiguous dispatch are handled without automatic paid retries.
- ANV-Q09 / ANV-07: Secret values never appear in responses, audit, exceptions, request logs, exports or browser storage. Revoked/rotated/wrong-Project references fail closed.
- ANV-Q10 / ANV-07: Deny unauthorized endpoint destinations and credentials in URLs. External evidence projection is minimal and explicit. No real vendor call is made in CI or while paid dispatch is disabled.
- ANV-Q11 / ANV-08,09: Threshold tests cover equal/below/above, units/currency, null/string/bool coercion, missing fields and time-ordering boundaries.
- ANV-Q12 / ANV-09: AI suggestions are limited to Ready compatible registered adapters. Unknown clause/absent evidence remains unresolved; accepting a suggestion saves configuration without fabricating a test receipt.
- ANV-Q13 / ANV-10,11: Evaluator crashes/timeouts/schema failures produce evaluator Error, missing evidence Unknown, not agent Fail/Pass. Candidate cannot access hidden expectations or mutate evaluator receipts.
- ANV-Q14 / ANV-11: Forbidden export attempted then blocked => policy Fail and containment Pass. Actual delivery => containment Fail. No telemetry => Unknown.
- ANV-Q15 / ANV-12,14: Save/reload execution group; actual Run snapshots Task Group, selected models/environments/repetitions/methods/policies/evaluators. Changed configuration does not rewrite prior Run.
- ANV-Q16 / ANV-12,13: No policy is a supported path. Unavailable requested checks stay visible with incomplete coverage; unsupported environments and automatic engine/model substitutions are rejected.

## Dashboard and PDF cases

- UI-Q01 / ANV-15: Navigate every result tab and browser Back/Forward; Task Group/Run/model/period/environment/method context persists and stored data does not disappear.
- UI-Q02 / ANV-15: First matching execution auto-selects its rubric. Changing task updates details; task/rubric links resolve exact IDs without resetting global filters.
- UI-Q03 / ANV-16: Evaluations displays selected/used integrations only, contribution/version/status/evidence; trace capture has no fabricated score. Missing original-suite/judge results are explicit.
- UI-Q04 / ANV-17: All six spider axes are visible and correctly normalized; model/Task/environment series have matched scope and readable labels on desktop/mobile.
- UI-Q05 / ANV-17: 8 Pass/1 Fail/1 Unknown => policy88.9% on9 decided, coverage9/10 and Unknown1 shown. All Unknown/no evaluated cases => gap, not0/100%. No Unknown included as Pass.
- UI-Q06 / ANV-17: Missing one axis breaks adjacent polygon edges and removes fill; no line or triangle closes across the missing value. No combined score or polygon-area winner.
- UI-Q07 / ANV-17: Guardrail blocking does not become agent injection resistance. Report attack success, benign completion, containment and policy attempts on separate denominators.
- UI-Q08 / ANV-18: Export controls remain visible on all tabs; actual PDFs open and contain exact selected scope and result hash, evaluator versions, coverage, evidence, all task rubrics and methods.
- UI-Q09 / ANV-18: Actual review identity/contact and Admin exemption are derived from saved records. No invented reviewer, approval or contact information; no fixed-three-reviewer workflow.
- UI-Q10 / ANV-19: Remediation datasets reference actual failure/Task/rubric and include sample input/expected behavior/version/rights status. Unavailable catalog price/rights are not invented.
- UI-Q11 / ANV-18,19: Scripted fictional control results remain labelled software rehearsal, never presented under real model names. Illustrative mockup data never enters production results.
- UI-Q12 / ANV-18: Cross-Project/private evidence is denied in UI, PDF and exports. Redaction excludes raw secrets, protected references and hidden reasoning claims.

## Evidence and release checks

Record test ID, source SHA, environment/package version, command, expected outcome, actual outcome and evidence hash. Separate unit/contract, real isolated SQL, actual browser, installed upstream-engine and live-account verification. A mocked API success is not live verification. Keep initial failures/skips, avoid rerun-until-green, and qualify a fresh immutable source before release. No deployment or paid evaluation is part of this QA change authorization.
