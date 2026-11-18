# KYC v8 offline package technical compatibility review

Date: 2026-11-18. Scope: read-only package metadata and Gym contract review.
This is a technical check, not publication, legal approval, authenticated policy
approval, runtime qualification, or permission for live calls. Hidden expectations
and private grading contents were not inspected or displayed. Output objects were
hashed mechanically without inspecting their values.

Source: `kyc-v8-successor-package.zip` in the supplied golden-kyc-pilot offline
export directory. Candidate template SHA-256:
`fb9a4aa75baa4dc4490141063a3a2221d21531fb266d636694bf7389b500f92c`.

## Findings

- The dossier expressly declares v8 unpublished, no qualification receipts, and
  no created successor records. Its checker result is invalid with
  `TP_FORM_ID_TAKEN`. These are upstream completion items, not a failed Gym run.
- This ZIP is not the import grammar: it contains a wrapper directory and
  directory entries, lacks root `praxis-export.json`, and supplies successor
  candidate JSON rather than a manifest of exact form, actor, and private assets.
  Do not upload it as an executable export or repurpose the reused v7 ZIP as v8.
- All four id-map references agree with the successor objects' old task/record
  identities. All four `successor_output_sha256` values match the canonical output
  objects; they are intentionally not raw-file hashes. The manifest distinguishes
  raw-file SHA-256 from RFC8785 object/part/output SHA-256.
- The change report retains `NOT ASSESSED: needs policy-owner review` for effects
  on required decisions/outcomes in all four tasks. APR-05 explicitly approves
  the changed policy basis only. Resolve that residual impact assessment before
  asserting the complete successor revision is approved.
- Uploaded role labels, dates, quoted approvals and v7 reviewer UUIDs are evidence
  supplied by the package, not authenticated Gym decisions. The final successor
  revision needs an immutable review receipt/reference; existing Gym PO decisions
  must bind exact current subject hashes. No uploaded statement approves itself.
- Policy captures include XML, HTML and text larger than the current public-text
  allowance. Current `PolicyArtifact` supports complete raw UTF8 bytes or a
  canonical JSON artifact with an explicit pointer to its exact public string;
  it does not extract XML/HTML into a separately hashed projection. Delivery is
  bounded to 8192 public UTF8 bytes total and 131072 materialization bytes.
  Source documents cannot be silently truncated or rebound to a different hash.
- Package completeness explicitly disclaims a 12-Nov point-in-time guarantee for
  state captures dated 18-Nov. Preserve this limitation; do not infer legal
  effectiveness or amendment history from successful hash checks.

## One upstream completion handoff

After the owner's authorized publication step, Authoring must resolve the form-ID
conflict by its supported successor-version path or a new form identity; publish
the final exact v8 template and recompute every affected template/part/reference
hash; create all four append-only successor task revisions; resolve the outstanding
decision/outcome-impact statement and record final revision review provenance;
then export an actual bounded `praxis.authored-task-export.v1` package with root
`praxis-export.json`, exact product selectors, immutable revision IDs, declared
form/actor/private file references and hashes, opaque review receipt references,
and execution `{location: anvil_only, paid_calls: false}`. Keep private assets
separate from the actor projection. Preserve originals and predecessor mappings.

## Gym-owned engineering and admission

`golden_kyc_v7_export.product_template` already admits the same product semantics
for version 7 or successors; no version-8-only decoder is required. Exact current
template registration and qualification remain necessary. Generic archive limits
are 1 MiB compressed, 30 MiB expanded, 10 MiB per file, 1200 entries, safe unique
paths and STORE/DEFLATE; the final export must conform to these bounds.

Gym must supply a bounded, source-hash-preserving public-policy projection for
the captured formats and qualify exact applicable policy/evaluator/runtime
bindings. That work must not manufacture upstream publication, legal decisions,
case expectations, data rights or live-call authority. Existing review, project
isolation, policy qualification and spending gates remain in force.

No API writes, live model calls, cloud actions or Authoring source edits occurred.
