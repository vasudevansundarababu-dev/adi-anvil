# KYC V8 — consolidated Authoring tool-binding correction

The QA runtime is deployed, the four-product software reference registered, and
the exact V8 template qualified. The approved authored ZIP is not yet importable.
The complete local decoder check found the nine procedure references below that
are outside V8's declared runtime tools. Do not ask SMEs to write interfaces.

Artifact checked: `kyc-v8-final-export/03-import-zips/praxis-b9a97d32f74db519950ca71d-p1.zip`.
Original SHA-256: `ced49fece4cc9d0ad46b7c3a3b1d3ab4f15ffbf2a33e03646e0bb74595674f60`.
This ZIP has 10 members and four tasks. Its original bytes have not been changed.
Template: `6d8f9cae-7c06-4c36-a207-522978d5486b`, V8,
SHA `8449adb008b6ecea7858b594dd5765f60b9b9596b57568d25f5e0598a334f7d5`.

## What Authoring should fix

Bind each of these authored procedure steps to the appropriate exact tool ID and
schema already declared in `template-spec.execution.tools`. Confirm semantic
equivalence; Gym must not guess aliases or admit arbitrary tool names. If no
declared capability supports a step, identify that capability gap explicitly.

Paths below are within each task's `private/<task-id>/reference.json`; JSON
pointers use zero-based indexes.

| Product / task ID | JSON pointer | Current undeclared tool |
| --- | --- | --- |
| Individual / bdbda764-eabc-40bf-82d8-cfd94277b9f8 | /authored/sections/S5/steps/0/tool | get_application_record |
| Individual / bdbda764-eabc-40bf-82d8-cfd94277b9f8 | /authored/sections/S5/steps/1/tool | verify_identity_documents |
| Individual / bdbda764-eabc-40bf-82d8-cfd94277b9f8 | /authored/sections/S5/steps/2/tool | lookup_identity_registry |
| Individual / bdbda764-eabc-40bf-82d8-cfd94277b9f8 | /authored/sections/S5/steps/3/tool | screen_watchlists_and_pep |
| Individual / bdbda764-eabc-40bf-82d8-cfd94277b9f8 | /authored/sections/S5/steps/4/tool | submit_kyc_assessment |
| Teen joint / 2291de2d-5d6c-41fe-9d8d-e95278f3f3e8 | /authored/sections/S5/steps/1/tool | document.verify |
| Teen joint / 2291de2d-5d6c-41fe-9d8d-e95278f3f3e8 | /authored/sections/S5/steps/2/tool | document.verify |
| Custodial / e63aee92-4f4f-4624-9ef2-d4fd0e9d6c5a | /authored/sections/S5/steps/1/tool | address_verification.check |
| Custodial / e63aee92-4f4f-4624-9ef2-d4fd0e9d6c5a | /authored/sections/S5/steps/2/tool | tin_verification.check |

The adult-joint task's tool references pass this check. The complete diagnostic
visited all four tasks and reported nine `PX_TOOL_CALL_MISSING` errors, with no
other conformance errors after the separate Gym optional-field correction.
This is not legal, case-review, rights or model-run approval.

The declared V8 IDs are:

`application.read`, `policy.read`, `documents.list`, `document.read`,
`document.compare`, `identity.check`, `document.check`, `address.check`,
`screening.check`, `authority.check`, `operation.lookup`, `operation.read`,
`information.request`, `information.read`, `finding.write`, `finding.resolve`,
`specialist.refer`, `specialist.read`, `search`, `search.read`, `recommend`.

Use their actual input/output/error schemas, not just similar names.

## Preserve approvals and immutable records

Retain the original approved task revisions, original ZIP and their hashes.
Do not edit approved records in place or manufacture approval receipts. Use the
existing owner-authorized correction/PO review process for any successor task
revision needed by a binding correction; this does not require SMEs to write
interfaces or re-author unchanged task intent. Recompute affected actor/private
asset hashes, manifest references, revision provenance and package fingerprint
consistently. Preserve private/public asset isolation.

No V8 template change is needed if existing declared tools cover the corrected
steps. A genuine new runtime capability requires a separately reviewed contract;
do not silently modify the published template or treat a guessed alias as one.

Return one corrected export folder/ZIP plus a change record mapping the nine
old references to exact declared IDs, semantic justification and genuine review
provenance. Validate all four tasks against the exact published form and tool
catalogue before exporting, including actor projection and all asset hashes.

## Separate Gym correction already in progress

All four tasks use an empty string for optional `S1.exampleGoverningState` and
omit optional coverage metadata. The published optional pick list permits this;
Gym's product decoder incorrectly treated that blank as a selected state. Gym is
fixing its metadata projection while preserving the approved source bytes. This
field does **not** need an Authoring task/template edit, invented state or dataset
binding. The changed Gym code needs fresh source-bound runtime qualification and
QA deployment; the old receipt does not qualify the new code.

## Prevent recurrence

Authoring should generate tool selection/bindings from the published template's
runtime catalogue and reject undeclared tool names before approval/export. SME
forms should expose meaningful choices while the system supplies exact IDs and
schemas. Offline export must run the same portable conformance checks used at
intake; live integration alone does not repair incompatible exports.
