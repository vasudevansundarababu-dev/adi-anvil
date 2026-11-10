# Isolated backend/web build resource proposal — NOT executed

Read-only inventory on2026-11-09 found only existing registry `anvil`, existing `anvil-vm`/default-compute accounts, and bucket `adi-anvil-mvp-2026_cloudbuild`. None of the new names below appeared. The ADI deploy principal has observed project `roles/owner`; this is not permission to expand scope or proof that organization policies permit creation. Fresh collision and policy checks remain mandatory. No APIs were enabled, resources/IAM created or builds submitted.

## Exact proposed diff

| New resource | Scope / control |
| --- | --- |
| Artifact Registry `anvil-staging-demo` | us-west1 Docker repository; immutable tags; no access to existing `anvil` repository |
| Service account `anvil-staging-build@adi-anvil-mvp-2026.iam.gserviceaccount.com` | Build only, no keys, VM or runtime use |
| Bucket `adi-anvil-mvp-2026-anvil-staging-build-source` | us-west1, uniform access, public access prevention,7-day object lifecycle; no default/shared bucket access |
| Repository IAM | New build account: `roles/artifactregistry.writer` on new repository only |
| Bucket IAM | New build account: `roles/storage.objectViewer` on new source bucket only; submitter uploads using existing authority |
| Logging IAM | New build account: project `roles/logging.logWriter` only; Cloud Logging-only output |
| Service-account IAM | Existing ADI submitter: `roles/iam.serviceAccountUser` on this new account only; no TokenCreator or project-wide impersonation grant |

Do not grant a broad builder/editor/storage-admin role to the build account. If service-agent/organization controls require additional access, stop and report the exact denial. Google documents user-specified build identities and their logging configuration [here](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts).

## Source and bounded job

Exact public native-qualified source edcc0514c43ceb614b813566820ee0c2c7311463; archive SHA2568564c5cd5fdd0795a6dc9e041befbce591781ccacd41182288c0fbdc1c7a6b28; native qualification402-path manifest SHA256cd9c2d44cd2106658923adc84307d6107ced87e9c33f6f6653d4325f65b536a6. Root independently verified all792 regular context files against that archive:10977981 bytes, no links/traversal/private local state. This **unfiltered** inventory SHA256 is57a7b64884aed1bebb114a89662fec8d417092f9b7ba1fe5cf160818c60ebed4. It includes the committed `.env.example` template, which is excluded from upload; no actual `.env` or key material is admitted. Local receipt `.local/staging-build-context-edcc051.json`; context `.local/staging-build-context-edcc051`.

The official local SDK upload selection is separately recorded in [staging-build-upload-source.json](staging-build-upload-source.json):381 files,5167729 bytes, inventory SHA256728a66918f33705f7a224ea0bbe98d2e73ac542f814499a6cdc7fe313a613a14. These are file-inventory hashes, not an uploaded tar/package hash. No object, generation, uploaded-package hash or build ID exists yet.

## Concrete review packet

- [staging-build-input-contract.json](staging-build-input-contract.json): exact edcc source/archive/native inventory,792-file context receipt and381-file upload receipt; exact new repository, builder and bucket only. No approval hash is supplied.
- [staging-cloudbuild-edcc051.json](staging-cloudbuild-edcc051.json): backend/web-only config; raw SHA25651b71b5722e2e21fbe3df1f9e759ac9377acc5f2c746580cf1d852458e63ffc5. Source/archive/native/prefilter/upload inventory bindings appear separately in substitutions and image labels.
- [staging-build-proposed-receipt.json](staging-build-proposed-receipt.json): configuration hashes plus separate input hashes, with all future object/generation/package/build/output facts null.
- [Exact lifecycle policy](../../../../infra/gcp/staging_build_lifecycle.json): one unconditional Delete rule at age7, SHA256e3ae995908d1537644653d392074bb59d5b5c979009c0cd6861d5c4b30689963.

The renderer verifies every local input and current context byte before emitting prospective argv. A missing or mismatched materialized config emits no mutation/submission argv. It remains a print-only renderer; local validation does not grant resource/IAM or build authorization. Fresh absence, enabled-API and organization-policy checks remain prerequisites to any later action.

Only backend/web outputs, Linuxamd64, one E2_HIGHCPU_8 job, timeout2400s. No Harbor/golden/native/app deployment. Proposed **USD5 build/storage allocation** within existingUSD500 allowance:40minutes compute≈0.624USD at verified0.0156/min, remaining4.376USD reserve for small artifact/source/log/transfer usage. This is an operator allocation, not a technical billing cap; retention/actual bytes and current storage prices must be checked before submission. Current mutable base/builder tags and unversioned hatchling remain explicit reproducibility limitations; capture resolved actual digests/build dependencies and two immutable output digests, never claim source pins make them deterministic. [Official build pricing](https://cloud.google.com/build/pricing), checked2026-11-08.

## Literal prospective commands

Proposed user approval covers only these three new build resources and four narrow permission bindings, the verified381-file public source upload, and one backend/web job with2400-second timeout under the USD5 preparation allocation. It also covers cleanup of only resources created by this operation if setup/build fails after its actual terminal state is known. Preserve evidence and abort cleanup if ownership or references differ. No application VM, public endpoint, DNS/TLS change, runtime identity, paid model call or application deployment is included. This paragraph is a proposal, not recorded approval.

The adjacent `staging-build-resource-commands.sh.txt` invokes only the print-only local renderer. It has no active cloud mutation command. Lifecycle/local-input validation occurs before any prospective resource argv is emitted, including exact policy semantics even if a changed policy's hash is supplied. User approval of the new builder identity/IAM/resource scope remains pending; no approval record has been invented. Submission additionally requires actual resource/IAM receipts, config/context revalidation and actual uploaded-object/generation/hash provenance. Exact isolated bucket and service-account flags prevent default/shared bucket or production repository selection. No account, permissions, credentials, cloud source or build was created here.
