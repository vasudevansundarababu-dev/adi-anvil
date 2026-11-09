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

Exact public native-qualified source edcc0514c43ceb614b813566820ee0c2c7311463; archive SHA2568564c5cd5fdd0795a6dc9e041befbce591781ccacd41182288c0fbdc1c7a6b28; native qualification402-path manifest SHA256cd9c2d44cd2106658923adc84307d6107ced87e9c33f6f6653d4325f65b536a6. A fresh local sanitized context was derived only from this verified archive:792 regular files,10977981 bytes, no links, absolute/traversal paths or `.git`/`.local`/`.env`/key artifacts. Its inventory SHA256 is57a7b64884aed1bebb114a89662fec8d417092f9b7ba1fe5cf160818c60ebed4 (UTF8 compact sorted-key JSON array sorted by path; each row path/sha256/size). Private local receipt `.local/staging-build-context-edcc051.json`; context `.local/staging-build-context-edcc051`.

Only backend/web outputs, Linuxamd64, one E2_HIGHCPU_8 job, timeout2400s. No Harbor/golden/native/app deployment. Proposed **USD5 build/storage allocation** within existingUSD500 allowance:40minutes compute≈0.624USD at verified0.0156/min, remaining4.376USD reserve for small artifact/source/log/transfer usage. This is an operator allocation, not a technical billing cap; retention/actual bytes and current storage prices must be checked before submission. Current mutable base/builder tags and unversioned hatchling remain explicit reproducibility limitations; capture resolved actual digests/build dependencies and two immutable output digests, never claim source pins make them deterministic. [Official build pricing](https://cloud.google.com/build/pricing), checked2026-11-08.

## Literal prospective commands

The adjacent `staging-build-resource-commands.sh.txt` is a reviewable non-executable command file. It immediately exits unless a future separately reviewed approval hash is supplied; that variable is an operator guard, not independent evidence of approval. It contains no deployment. Root must review the exact resource/IAM diff before any command is used. Submission additionally requires approved materialized build config and exact context revalidation. The renderer now requires `staging_source_bucket` and explicit `--gcs-source-staging-dir`; the default production/shared bucket cannot be selected. No new account, credentials or cloud source were created by this preparation.
