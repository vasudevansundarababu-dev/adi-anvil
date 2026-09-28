# Fixture ingestion, reproducibility and isolation

## Supplied artifacts

`fixtures/cases/{MKT-001,FIN-001,STR-001}/case.json` is a **repository fixture manifest**, not the public API import schema. Each case has `actor/task.md`, `actor/exhibits.json` and `private/reference.json`. `fixtures/cases/rubric-template.json` supplies shared scoring definitions; the loader materializes a distinct immutable rubric per task. References and rubric are private artifacts, never candidate inputs.

`fixtures/candidate-outputs/responses.json` supplies six predetermined candidate responses. `fixtures/expected/morning-assertions.json` is a test assertion file, never an assessment authority in the application. The negative scenario file describes tests Codex must implement; it is not evidence that those tests ran.

## Loader to implement

1. Register only the three known fixture IDs and expected file paths/digests at build time. Do not let a browser submit arbitrary repository paths. Never evaluate expressions from JSON or execute uploaded content.
2. In local fixture mode only, expose “Import built-in synthetic cases” to an authorized Data Engineer. Show source origin, static mode and lack of faculty validation. Alternatively a local seed CLI uses the same services with an audited synthetic actor.
3. Map fixture files to server-owned artifact UUIDs; maintain actor/private classification. The shared rubric key is resolved by a fixed internal mapping, not a user-controlled path traversal. Derive API request bodies from typed schemas in product/15.
4. Build canonical case/task/rubric drafts through application services. Synthetic rights/review exercises are explicitly test records. Do not auto-create live external processing rights, faculty approvals or paid-run authority.
5. Validate all sources/exhibits/constraints and create gaps where data is absent. A source case is not automatically a published task; use the review/calibration/publication path in tests.
6. Enforce idempotency on exact fixture/version/hash. Editing an existing user's imported draft must not be overwritten by a repeated seed. For a fresh walkthrough create a new isolated demo project, not a database reset.

Public partner import accepts uploaded artifact IDs as specified. Support these three original text/JSON fixtures first. Real-file scanning/OCR is not silently bypassed. The Bodhium workbook remains a handoff format; an Excel parser is not required by the overnight core.

## Execution behavior

The fixture adapter reads only the predetermined candidate response for a registered fixture case and candidate ID. It does not compute a response from hidden references or expected scores. The expected-score file is loaded only by tests. The real candidate adapters read only the frozen actor-artifact allowlist, excluding the fixture-response library.

Two fixture candidates: `fixture-correct` and `fixture-constraint-blind`. Run three tasks × two candidates × one repetition = six illustrative episodes. Do not seed completed episodes as if the worker ran them. Launch through the real job queue/LangGraph path and exercise actual reviewer APIs. Scripted synthetic reviews may be used by E2E tests, but UI morning review remains a real user action.

Scripted test review scores: correct response R1/R2/R3 = 4/4/4 → 100, pass. Constraint-blind response = 4/0/4 → 70, fail with critical violation. Critical failures require secondary review. If actual manual grading differs, preserve it and show the resulting calculation; do not overwrite human grades with expected fixtures.

Expected aggregate after those six final scripted reviews: 3 cases, 3 families, 6 valid episodes, 3 passes, 3 failures, mean score85, pass rate50%, always labeled illustrative. Unknown/pending/invalid cases are not coerced into this expected denominator.

## Reference checks

- MKT: units100/125/140, revenue10000/11250/11200, gross profit4000/3750/2800; 10% discount chosen because 20% violates 30% margin.
- FIN: debt service140000/215000/116000; DSCR approximately1.7143/1.1163/2.0690; choose A, because B violates coverage and C lacks funding.
- STR: contributions41000/50000/61500; North chosen, South pending readiness and West over budget.

Test numeric calculations independently from stored expected values. Small display tolerances never override a hard feasibility boundary. A differently worded correct answer is not a failure. Real model results may be malformed, refuse, or produce alternatives: report and grade under the frozen contract instead of comparing exact text.

## Additional engineering cases to generate during build

Create fixture-only transport responses for refusal, malformed JSON, empty output, missing usage, timeout/unknown dispatch and cancellation; calibration examples for valid alternative and ambiguous reference; a 200-record **load-test-only** inventory grouped in explicit families. Do not call those 200 expert tasks. Keep all generated variants visibly synthetic and outside the three-case morning performance summary.
