# Offline publication acceptance

Offline publication acceptance is an explicit local project Product Owner
attestation. It does not verify an Authoring API signature, approve policy text,
qualify installed software or authorize inference. No actual project attestation
is created by migration130 or by uploading a file.

The existing authenticated API publication path remains separate. Its historical
receipts keep their meaning. Offline receipts retain `publication_verified:
false`, `publication_accepted: true` and a hashed `publication_basis` with kind
`po_attested_offline`. Offline qualification and revocation records are not
enqueued as authenticated Authoring events.

## Review sequence

1. Register the complete exact template specification.
2. Stage the original publication record bytes using `record_utf8`. The JSON
   record must contain `status: published` or `publication_status: published`.
   When both are present both must be exactly `published`; conflicts, nulls and
   candidate status are rejected. It must contain the external `template_id`
   (registered template key, not the database row UUID), exact integer `version`,
   an aware non-null `published_at` no
   later than database time, the registered `template_sha256` and the exact three
   `part_hashes` (`authoring`, `execution`, `skills`). Original bytes and their SHA
   remain retained separately from canonical subject identity. Duplicate JSON
   keys, nonfinite values and oversized/deep records are rejected.
3. Inspect the staged subject, original record SHA, publication date, exact
   template/part hashes and provenance. Staging returns accepted=false.
4. A current project Admin explicitly attests the displayed subject SHA with a
   rationale and future expiry. Upload, a chat reply, email and file metadata
   cannot perform this action. The existing authenticated session, CSRF and
   idempotency controls apply. The staged subject creator may self-approve only
   when the project has exactly one active Admin; the actual identity and
   self-approval fact are audited. Another active Admin can approve otherwise.
5. Request template qualification separately. All existing capability and actual
   runtime conformance checks still apply. Local publication acceptance alone
   cannot make a blocked environment qualified.

Routes below the existing project `/dataset-exports/generic` prefix:

* `GET /templates/{template}/offline-publications`
* `POST /templates/{template}/offline-publications`: `{record_utf8}`
* `POST /templates/{template}/offline-publications/{subject}/attest`:
  `{subject_sha256, rationale, expires_at}`
* `POST /templates/{template}/offline-publications/{subject}/revoke`: `{reason}`

The record cap is131072 UTF8 bytes, canonical subject cap262144 and HTTP request
cap1048576. No filesystem path, uploaded trust key or external credential is
accepted. Additional original record fields remain retained, without becoming
trusted API claims. Published status and date are necessary assertions to review,
not cryptographic proof of upstream publication.

## Current authority

Qualification lookup and original product-input, policy-qualification and trial
binding guards validate the exact immutable attestation and subject references.
Expiry, subject revocation or loss of the attesting Admin's current membership
invalidates the offline basis. Application, scheduler, grader and context-owner
reads use the same scoped SQL predicate; restricted qualifiers additionally need
their enrolled actual database login. Runtime roles cannot append attestations.

Revocation is append-only and permanently invalidates that staged subject and
all its attestations. Re-uploading identical bytes cannot undo it. A new original
publication record/version requires a new review; existing immutable bindings
are never silently replaced. Normal template qualification revocation remains
authoritative independently.

An unpublished candidate, missing/null publication date or mismatched hash stays
blocked. The local PO decides whether the unsigned offline evidence is acceptable
for their project; the interface states its provenance explicitly. This mechanism
does not establish upstream authenticity, legal acceptance or spending rights.
