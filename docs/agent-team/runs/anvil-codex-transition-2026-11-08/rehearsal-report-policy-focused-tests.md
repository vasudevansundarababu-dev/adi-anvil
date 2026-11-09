# Fictional execution and report-policy focused verification

Development verification on a fresh isolated PostgreSQL database migrated through 062; this is not the final checkpoint regression verdict.

The independent focused batch passed **20 actual SQL/API tests** in 10.55 seconds. Private log SHA-256: `5a0deb4bd67b2c618b973a1b2770f42c3e6cbc620dc73095dc384b453d5c2897`.

Coverage includes actual execution of eighteen fixed scripted cells against public fictional inputs; exact output persistence/hash bindings; an independent arithmetic score check; the full-suite mean of two repetitions out of 81 points; no candidate filesystem reads or private expected-answer input; source-change rejection both before and after execution; one execution under concurrent retry; idempotency, project isolation, worker privilege denial and immutable terminal results. Existing source, qualification, score-review and comparison tables remain unchanged by the separate rehearsal path. Report-policy bookkeeping is deliberately separate.

Actual SQL/API review-policy checks cover Admin-configured counts of zero, one and four distinct reviewers; repeated-review retry without count inflation; actual execution actor rather than draft creator determining Admin exemption; non-Admin configuration/approval denial; exact-result hash approval; SQL actor/Admin spoof rejection; current individual reviewer duty and cross-project denial; and preservation of the previously frozen policy after later project configuration changes.

Actual PDF responses are blocked while report review is pending and become available after explicit Admin authorization. Actual Admin execution and a frozen zero-review policy require no extra PDF approval. Wrong result hashes and raw-prompt requests are rejected. A name containing literal HTML is escaped, and a real private Golden draft's expected-answer canary is absent from the exported PDF.

Two additional cases exercise the existing comparison path using explicitly manufactured SQL qualification/capture metadata, not native execution. A v2 protocol created and admitted by the actual test Admin with zero reviewer-duty IDs publishes eighteen completed cells with the 81-point task primary and an explicit Admin exemption, while creating no legacy human-review rows and setting `reviewer_verified=false`. Revoked qualification still blocks that Admin. Existing v1 protocol identity remains unchanged. These synthetic SQL fixtures are not user approval, current source qualification or model-performance evidence.

## Preserved failures and corrections

The first 16-case review batch had 14 passes and two failures: a valid reviewer retry with a new idempotency key raised an unhandled uniqueness error. The uniqueness constraint prevented count inflation; Coding repaired the retry behavior without weakening it. The corrected 16-case batch passed. Initial failure log SHA-256: `13edb273e9a4ea88930b0f2a94c8426c23f181083ed9e0c1b61455a224dc8e71`; successor log: `1e283b3091a3f9e785c241099a79b6af468edb136e89221920f06a19039dfd81`.

The first expanded 20-case batch had three test-harness failures: two changed protocol requests reused the fixture's prior idempotency key and were correctly rejected, while PDF extraction inserted a line break in an asserted phrase. Tests were corrected to use fresh keys and normalize extracted whitespace; product guards were unchanged. Preserved log SHA-256: `bad9815724fea48b49c652cf41334563d83ed26150fe82250d858c21a82b2362`.

All three independent test files passed Ruff. The existing Authlib deprecation warning remains. No paid/provider calls, cloud resources, native execution, deployment, Praxis changes or modifications to the current preview's drafts were performed by Testing. Full regression remains bound to the subsequent immutable checkpoint.
