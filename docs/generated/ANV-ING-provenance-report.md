# Immutable source provenance increment

Implemented in the existing importer after authorization for autonomous local work.
Contract: `docs/build/ANV-ING-provenance-contract.md`. Usage:
`docs/runbooks/task-data-import.md`.

Migration018 adds a project-scoped immutable declaration table. The API accepts five
explicit source classes and owner/attestation basis. Synthetic declarations require
generator/authoring version and seed/recipe identifier. Declaration digest, author and
timestamp follow the published dataset version into row lineage and run snapshots.
Legacy imports remain unclassified. Changing a declaration or retroactively declaring
an imported artifact requires reupload. No new worker grants; references stay isolated.

Only explicitly declared ADI synthetic sources publish through this development path.
Other classes require reviewed rights/privacy controls that remain unimplemented.
Declarations are attestations, not clearance. Synthetic fixtures never receive partner
labels. Imported runs remain configured drafts; arbitrary task execution is unqualified.

Verification: `pnpm db:migrate`, `pnpm check`, `pnpm test:unit` (130),
`pnpm test:integration` (67), `pnpm test:e2e` (4;45.6s). Fresh/repeated001–018
passed using `tests/migration_smoke.py` and the local environment loader in retained
`anvil_migrationcheck_446c2001b9f4`. Final regression/secret scan recorded in BUILD-STATUS.

Remaining: reviewed rights/privacy approvals, automated PII discovery/redaction,
connectors, scientifically qualified imported execution and measured performance.
`adi-ls-geo-001` and `adi-ls-intent-gap-002` remain undefined; neither is implemented.
Factory metadata release and full benchmark acceptance remain partial.
