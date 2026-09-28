# Reported result import

This local path imports already-produced evidence. It does not call a model, reproduce the external study or establish processing rights. Execution origin remains `customer_reported` or `partner_reported` after Anvil review and export.

1. A Researcher creates a protocol in external-result mode with one `external-reported` candidate, the frozen suite and distinct reviewers/adjudicator. An Advisor reviews its exact version.
2. The Researcher prepares a customer- or partner-reported run. The launch endpoint rejects candidate dispatch for this mode.
3. A Data Engineer validates an `anvil.external_results.v1` JSON manifest in Run console. Validation creates a receipt candidate, not episodes. Correct errors before commit.
4. Commit binds the exact validated manifest hash and rechecks current qualification, rights, artifacts and exposure. Replay returns the original immutable receipt. Supplied output enters durable human review; missing output remains unscorable. Unknown execution remains unknown.
5. Independently reviewed reports retain execution origin and import receipt hashes. Producer scores never overwrite Anvil reviewer scores. Exported receipts omit arbitrary producer configuration parameters and raw evidence.

Required fields and attempt shape are in [the interchange contract](../product/15-MVP-DATA-AND-API-CONTRACTS.md#63-external-results-manifest--interchange-v1). This slice additionally requires explicit `producer_manifest_hash` (null if unknown), timezone-bearing execution date, and explicit `trace_coverage` when a trace is supplied. Unknown protocol hash requires nonempty incomparability reasons. One repetition/attempt per task is supported; duplicates are rejected. Unknown task IDs, wrong-project artifacts, mismatched origin, protected-test exposure and mismatched protocol hashes reject the batch.

Current file boundary: general uploads remain quarantined because a general scanner is not qualified. Do not change scan status to bypass this. Aggregate-only manifests can explicitly omit output; trusted synthetic integration tests exercise the output-bearing path without authorizing arbitrary real files. No imported score or source claim grants faculty validation, ADI execution provenance, distribution rights or paid-call authority.
