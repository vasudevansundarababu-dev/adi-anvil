# Final fictional-comparison verification

Verified successor: `a1ddace319cd6e7e0472877ef5f181099613b63f`. All **965 tracked source paths** in the serving copy matched Git exactly; independent manifest SHA-256 `bcc6d59961f865547fa3e2b2055986b56cb22b9faf73e7ec973771505c1c2e6c`. Web PID 71800 was verified serving loopback 50679 from that source copy.

| Check | Actual result |
| --- | --- |
| Full benchmark SQL foundation started at ab38/schema062 | **209 passed, 29 native skips**, 121.88s |
| Standard integration foundation started at ab38 | **190 passed, 19 explicit opt-in/Praxis skips**, 107.69s |
| Forward 063 guard and approval-gate delta | **26 SQL/API tests passed**, 10.70s |
| Final real-OIDC browser tests | **3 passed**, 11.9s |

The 063 delta was implemented while the foundation batches were active; the two reviewed runtime changes and the added negative tests are separately covered by the focused batch. The 209-case suite was **not** rerun on schema063, and is not represented as a full successor-schema rerun. The final browser tests and exact-source comparison bind to a1ddace. Root separately ran the complete backend unit suite.

## Actual application proof

The tracked browser test used the existing synthetic Admin's real Keycloak login, configured two report reviewers, created and executed a new fictional comparison, reopened its stored result, navigated all four connected views and downloaded its exact-result technical PDF. There were no mocked routes, preseeded completed cells or reviewer duties created by the test. Two existing authenticated historical-evidence/PDF browser cases also passed.

Read-only SQL audited both actual executions:

| Execution | Stored result SHA-256 |
| --- | --- |
| Independent browser run `830aa7af-5448-4c15-8649-d8c467763dad` | `98c8cd4ce33f1f19dde9e8b94869a926d31a97e6fe333137802ec870a24a0fd5` |
| Root's visible Admin run `9791e3a8-9946-44b5-a912-785aac4badbe` | `df0f79b6baa2a82a15eb3bfdd96d6812ccb132fb0357632d8d0e74d66cc0aa81` |

Each stored eighteen actual scripted cells and means of **81, 18 and 43 out of 81**, calculated over two repetitions. Each had zero provider calls, matching executor/source hashes and exactly one actual Admin-execution provenance record. Both had **zero report decisions and zero legacy human-review rows**. The project still had no official comparisons, source reviews or qualifications created by this workflow. Admin execution authorized report release without pretending that independent reviewers verified it.

Both executive and technical PDFs were fetched through an authenticated browser and parsed with the existing PDF library. Their bytes contained the exact result digest, provider-zero disclosure, 81-point denominator, explicit software-only/model-performance limitation and no false independent-human-review claim. Private Golden expected-output exclusion was additionally tested with an actual canary in the focused API test; raw-prompt requests and stale-result PDF hashes were denied.

| Actual PDF | Bytes | SHA-256 |
| --- | --- | --- |
| Executive | 2,831 | `1f4f6ff93dbc08782ed575b0973561dd99e4f01703dec87a78222d9001cc0b83` |
| Technical | 17,389 | `157a5d0e7f03a28dc4af324c90da294e3b8670dbc9a313b10d0edd1dd8def1bc` |

## Security and failure provenance

The focused cases reject fourteen malformed policy snapshots without persisting authority. A completed manufactured SQL comparison whose qualification was subsequently revoked denied Admin report approval and created neither a score successor nor an approval decision. Configurable counts zero/one/four, distinct actual reviewers, Admin executor versus creator, exact hash approval, current duties, cross-project isolation, immutable older policy and concurrency were tested. Manufactured qualification/capture rows exist only in disposable SQL test fixtures; they are not native execution or release approval evidence.

Initial duplicate-review retries exposed an unhandled uniqueness error. Coding repaired it, preserving the uniqueness constraint, and independent retry tests passed. Separate test-harness idempotency/PDF-whitespace errors and their corrections are preserved in `rehearsal-report-policy-focused-tests.md`. Existing Authlib/Alembic deprecation warnings remain.

Private log SHA-256 bindings:

- Full SQL: `4d5c47eab284ddd3c5add7dfea77c7a9f6c3fc7860a87d74d4c24af489ddd4fe`
- Integration: `e2fc91d777ccb78ecc0259ea95ad0a9d8e10f6f7713a116dc13eda7858f94a5c`
- 063 focused delta: `087bc6d04246df2eef7390581d2edecc0d8f646c17b99ae07631da05790554c3`
- Final browser: `6f656520c58f849ac79e0364eb6de29a1813ea37fe94c339d86a6450868f3eb2`

Only the newly created disposable full-regression graph/container/volumes and two test databases were removed; their absence was verified. The dedicated role probe was retained stopped. Current preview data, existing drafts, historical evidence and older previews were preserved. No cloud resources, provider calls, new native executions, Praxis changes or deployment occurred. This is a local fictional software comparison, not a model benchmark or staging deployment.
