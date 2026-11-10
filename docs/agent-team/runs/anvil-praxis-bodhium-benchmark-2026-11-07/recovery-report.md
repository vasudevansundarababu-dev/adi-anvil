# Recovery provenance and gaps

Status: **VERIFIED BUILD-SOURCE OVERLAY; FULL R6 GIT TREE UNRECOVERED**. No application tests or deployed-service checks executed. Date: 2026-11-07 UTC.

## Identities and custody

| Item | Identity / observation |
| --- | --- |
| Original checkout, left unchanged apart from user-added attachments | `/workspace/project/adi-anvil`, branch `codex/anvil-agent-team-2026-11-06` |
| Isolated recovery checkout | `/workspace/anvil-recovered`; local clone with independent Git objects, no commits made |
| Actual HEAD (base, NOT latest release) | `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` |
| Base Git tree | `37a37112875b794b59a1e4681f901063cf91184d` |
| Reported never-pushed r6 release commit | `15e35f12725a89be6e507b2eb73d4433e666dd76` — not locally present or verified |
| Expected complete r6 Git tree | `18fca788310f91a35a54df39392a37c026ae16b1` — NOT reproduced |
| Actual composite base + archive Git-style tree | `cc9925ec8380a56fa3fa988c157b2d5d7563cda2` — differs from expected r6; excludes new recovery/design files |
| Supplied archive | `anvil-r6-cloud-build-source.tgz`, 3,041,716 bytes |
| Independently computed archive SHA-256 | `5679da027619c50f4a2418514805c2b38730888ce45fa2ed3c7a4f42ec29d8fe` |
| Production source manifest SHA-256 | `cedfb20d5b3160dcfee2e91f729e237063e16c714eb70dbef52cc7c59e173031` (`production-source-manifest.jsonl`) |
| Extracted worker.py SHA-256 | `ec5afade0e41600fc3eb29d9a857d58887f94c7e49b5d9fc46979eef3c6ab113` — independently matches supplied deployed hash |
| Full original handoff TXT SHA-256 | `17f34a7831f029782ee3b28b5b6944ac7be82d1899ed29f476e5b7580d27b8ec` |
| Approved spec SHA-256 | `44196cae04b7a399fb70da8d4577345b2cf95ee6a14daa41f3d8c8f2b4921cbc` |

The composite tree is computed from base tracked entries overlaid with archive regular-file blobs and executable modes, using Git blob/tree hashing and Git ordering, without creating a commit. It is a reproducible composition identity, **not** proof of r6 identity. Base tracked inventory: 497 files. Overlay adds two paths, yielding 499 composition entries. Original input archive and TXT were copied without byte changes to `recovery-evidence/inputs/` in this isolated checkout, not into a served directory or external service. No secret-bearing files were searched for or copied.

Coordinator-supplied immutable provenance (not fetched independently here): project `adi-anvil-mvp-2026`, region `us-west1`, Cloud Build `1f2b1a68-44d3-44b5-bdc7-8acdf0be710e`, SUCCESS; source `gs://adi-anvil-mvp-2026_cloudbuild/source/1794018126.49446-d7c91742d24c4256b0d9a2aeee6f05fd.tgz`, generation `1794018127274663`; image tag `15e35f1-1794018124`.

Reported release image digests, NOT downloaded or inspected here:
- Backend: `sha256:0becacc8551d6910757c32cd6594b7194e6855b5d1e93889f3fa4c4e75472c7b`.
- Web: `sha256:80e0a269584abc35be799c9a0fbdd9a0557d6d09b71909a8b0ca8007f422da25`.

Reported missing artifacts:
- Release patch SHA-256 `3e3552e21f37388aca0f7985c54e169f54ce02bc318b0368ec19e334b6389e66` (old run folder `deployment-evidence/release-r6.patch`).
- Historical r6 manifest SHA-256 `5c15faf05331d58b26342ce7a40d8b0df5f4be62d2619a2840fbf0cdab3f7c7b`.
- Full commit/tree objects, current r6 changed tests/docs, prior approval/QA/security/deployment evidence.

## Independent archive validation and extraction

Read-only Python `tarfile` enumeration checked SHA-256 and exact byte size before extraction. All 318 members: 54 directories and 264 regular files, 4,421,541 expanded bytes. Denied absolute/traversal/backslash paths, duplicate normalized paths, symlink/hardlink/special types and known credential/runtime path components. Enforced 5,000 members, 50 MiB/file, 500 MiB expanded limits; supplied compressed size is well below 100 MiB. Only regular files were manually written under the new root; no archive command/hooks/imports executed. Member file SHA-256, Git blob ID and executable modes are retained in `recovery-inventory.json`. These checks are recovery validation, not application acceptance tests or a claim of comprehensive malware/secret scanning. Coordinator's content scan was reported clean; it was not independently reproduced here.

264 recovered regular files comprise 255 byte-identical base files, 7 modified files and 2 new files:
- Modified: `package.json`; `services/backend/src/anvil/worker.py`; `apps/web/src/components/WorkspaceTasks.tsx`, `WorkspaceExecutionGroups.tsx`, `WorkspacePreparation.tsx`; `apps/web/src/lib/workspace.ts`, `executionReadiness.ts`.
- New: `apps/web/src/components/ReasonList.tsx`, `apps/web/src/lib/readinessCatalog.ts`.

`worker.py` restores project fence → run → job/episode locking, transition-once finalization with `UPDATE ... RETURNING`, and error-path lock ordering. Readiness UI uses the server as authority and role-safe reason/action presentation. Preserve both during later work; no benchmark change was made to them.

## Exclusions: do not erase or misrepresent them

235 tracked base files are absent from the build archive. The complete path/blob inventory is in `recovery-inventory.json` under `base_files_absent_from_archive`; every one remains historical/unverified for r6. It includes all 57 `services/backend/tests/` files, root tests, contracts, runbooks, role skills, BUILD-STATUS/BUILD-DECISIONS and other excluded root/config files. Absence from upload is not evidence of release deletion. Conversely, a base file surviving locally is not evidence it existed unchanged at r6. The reported 30-file increment cannot be reconstructed by subtracting these nine observable path changes; omitted modifications/deletions/renames are unknown.

Retained base `.gcloudignore` excludes docs, tests, contracts and backend tests by allowlist. The archived `.dockerignore` excludes backend tests and many build-context paths. Their exact current roles and all omitted paths are preserved; no attempt was made to recover tests/docs from image-only evidence. `package.json` now refers to `tests/readiness_catalog.mjs`, which is absent from both the archive and base. This is a concrete missing r6 test, not permission to create a replacement now. Earlier finalization/deadlock regression additions are also not available. Historical BUILD-STATUS dates/evidence must not be presented as the latest release report.

## Access observations and limits

Before archive arrival: no `gcloud`/`gsutil`, no visible Anvil cloud config or GCP auth variable names; unauthenticated Cloud Build, GCS and Artifact Registry reads returned 401. Read-only GitHub lookups found the base branch; release commit returned 422, expected tree 404, no release/tag recovered. Old conversation metadata GET reported ERROR; no resume/reset/delete, runtime command or credentials read was attempted. Workspace inventory found no older r6 source artifact. Coordinator subsequently verified login/build and supplied the archive; therefore no CLI installation, authentication or credential transfer is needed here.

No GCP write, deployment, snapshot restore, container/volume deletion, live product call, source implementation, application test, commit or push occurred. No Mac/Praxis filesystem, services or conversations were operated on. All newly authored files are recovery evidence/design documents under this checkout; extracted existing production files are recovery only.

## Prerequisite before later coding

Obtain the full patch and manifest at their supplied hashes, or a full sanitized source archive/Git bundle of r6 with paths/modes and recorded deletions. Preserve raw supplied bytes outside any served path. Validate all paths/types/limits, verify patch/manifest hashes, apply only to a separate comparison copy/index, and compare the complete tree to `18fca788310f91a35a54df39392a37c026ae16b1`. Recover and inspect omitted tests/evidence, especially finalization/concurrency/readiness. Do not overwrite this recovery record or historical base files in place without recording new provenance. If historical recovery is impossible, require the Product Owner's explicit acceptance of a newly audited baseline and newly scoped regression work; never relabel it as recovered r6. This document does not grant that exception or permission to test/code.
