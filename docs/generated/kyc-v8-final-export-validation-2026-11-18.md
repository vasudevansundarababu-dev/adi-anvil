# KYC v8 final offline export validation

User supplied `kyc-v8-final-export/` on18November2026. This supersedes the
earlier successor dossier for structural import validation; it does not silently
approve policy, runtime, private case expectations, rights or spending.

## Passed file and schema controls

- 68/68 declared payload SHA256s and sizes match; the only additional file is the
 manifest itself. No symlinks were found.
- Import ZIP has10 members,37680 compressed bytes,116061 expanded bytes, with
 `praxis-export.json` at its root. Archive safety and CandidateExport schema pass.
- All9 declared form/actor/private canonical asset hashes match, with no
 undeclared ZIP paths. The form hash matches the published authoring profile.
- All4 product selectors and successor task template references match the exact
 v8 specification. Revision IDs, review references, lineage mappings and authored
 output hashes agree. All prior unassessed change-report entries are resolved.
- Temporal evidence includes the39 state files and federal source with matching
 hashes. Its limitations remain explicit:18November captures do not independently
 establish12November state-law text; CA/NY rendered text and TX/IL applicability
 analogy remain disclosed. This report does not supply independent legal review.

Template SHA256:
`8449adb008b6ecea7858b594dd5765f60b9b9596b57568d25f5e0598a334f7d5`

ZIP SHA256:
`ced49fece4cc9d0ad46b7c3a3b1d3ab4f15ffbf2a33e03646e0bb74595674f60`

## Gym actions and remaining controls

The original publication record uses uppercase`PUBLISHED`. Gym previously
accepted only lowercase`published`; additive migration131 and matching API/UI
checks recognize exactly those two enum spellings, preserving original bytes.
Candidate, conflicting alias, wrong identity/version and other spellings refuse.
These fixes passed local tests; deployment evidence is tracked in BUILD-STATUS.

Source approval records describe actual human events, but offline metadata is
not authenticated Authoring API evidence. Exact registration, explicit local PO
publication attestation, technical qualification and current policy/input/review
bindings remain separate. Upload cannot create any of those approvals by itself.

Actual Admin browser registration was attempted; the browser upload security
gate declined permission. Read-only QA lookup still found only unchanged v7.
User was provided exact UI registration steps; no alternate upload or credential
workaround was attempted. Runtime engineering continues independently.

No live model calls, live Authoring integration, v7 modifications, policy
approvals or private dataset/expectation disclosures were performed.
