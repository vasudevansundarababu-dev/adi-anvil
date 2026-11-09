# Linux QA execution record

## Final exact-resource cleanup complete

After the user explicitly approved **“Delete these temporary test resources”**, automatic approval review accepted the same bounded cleanup. Fresh exact-ID/status/reference checks preceded deletion. All eight reviewed QA resources/configurations are now verified absent: VM4723949448594237365, bootdisk8660101875172681653, firewall9051667802961520580, NATchild `anvil-staging-native-nat` in router8927032357452294091, that router, reservedIP7265975432424237005, subnet159611463170566136 and network8017050090191235044. NAT absence was verified in its parent before that parent was deleted; all other resources returned NOT_FOUND after deletion. No unexpected references or ID mismatches occurred.

All exported evidence and local private/public receipts remain preserved. The exact temporary OS Login key was already removed. No listed QA resources remain to incur ongoing resource charges; prior usage and logging retention may still appear on the bill, which is not reconciled here. No unrelated project resource, IAM/setting, Praxis, original local changes or application deployment was touched. Receipt: `linux-qa-provenance/qa-resources-deleted.json`. Earlier blocked/stopped sections below are preserved history, superseded by this explicit-authorized successful cleanup.

## Cleanup approval review blocked — current update

The exact-ID deletion attempt was rejected **before execution** by automatic approval review because the trusted user messages authorize creation/testing but do not explicitly authorize irreversible resource deletion. No deletion was executed and no final-cleanup receipt was created. The VM remains stopped, the temporary key remains removed, and retained disk/network/NAT resources continue to incur the residual costs below. Explicit user cleanup approval is required before retrying; the rejection will not be bypassed.

Read-only Cloud DNS zone discovery also returned `SERVICE_DISABLED` for `dns.googleapis.com`. The API was not enabled and no records/settings were changed; authority over the proposed `adi-labs.ai` staging hostnames remains unverified.

## Current compute/access state — stopped after evidence export

After Testing confirmed all28 native evidence, prior failures,402-file source checks and final focused results were exported, no active tests/actors or further SSH were needed. The exact temporary OS Login fingerprint `290de06f1812c7115b087f4e1923b17801a03bdf8f7e51c9f12bbacbe404f838` was removed and verified absent; other account keys were untouched. No further extension occurred.

Fresh VM metadata verified ID `4723949448594237365` before stopping only `anvil-staging-native` in `adi-anvil-mvp-2026/us-west1-a`. Follow-up metadata confirmed **TERMINATED**, last stop **2026-11-09T02:07:31.726Z**. Boot disk8660101875172681653 and NAT/network/subnet/router/address/IAP firewall remain intentionally retained pending the final exact-ID cleanup handoff. No application deployment or current environment change occurred.

Compute is stopped, but charges are not zero:30GiB balanced disk≈3USD/month plus reserved NAT IPv4≈3.65USD/month, with possible retained gateway assignment up to≈1.02USD/month and processing/log/retention usage. Conservative fixed reserve≈7.67USD/month while retained; this is a planning estimate, not a reconciled invoice. No evidence snapshot was created by DevOps. Receipt: `linux-qa-provenance/qa-compute-stopped.json`.

## Preserved setup/source/test history

## Fourth reviewed successor and explicit access extension — edcc051

User explicitly selected the first offered access option, permitting one extension of the **same** temporary public OS Login key until **2026-11-09T02:51:10Z**. The official isolated Anvil SDK updated only `expirationTimeUsec`; the returned exact timestamp was asserted and verified. Fingerprint/account unchanged; no IAM/project setting, private-key read, new resource or automatic further renewal. Earlier01:51 expiry statements below are historical. Remove the exact key after testing, and do not extend beyond the new deadline without fresh authority.

Testing retained a further549 native failure: the non-root evaluator could not read its projected public program leaf. A reviewed source-only correction preserves private-parent ownership and makes only the bounded evaluator program projection usable. Pushed source `edcc0514c43ceb614b813566820ee0c2c7311463` has archive SHA256 `8564c5cd5fdd0795a6dc9e041befbce591781ccacd41182288c0fbdc1c7a6b28` and402-file manifest SHA256 `cd9c2d44cd2106658923adc84307d6107ced87e9c33f6f6653d4325f65b536a6`.

With Testing paused, all401 prior549 files matched. Only `services/backend/src/anvil/benchmark_evaluator_native.py` was atomically replaced (old copy `.local/source-before-edcc`), and new `services/backend/tests/unit/test_benchmark_evaluator_projection.py` was created without overwrite. All402 successor files matched. Existing owner-only `.local/t06` prerequisite, environment, packages, images and host/private-parent permissions were unchanged.

Actual-host **48 evaluator/projection/contract units passed** without SQL credentials/writes (one existing Authlib warning), plus **9 adapter guards passed**. Testing received the exact successor for a fresh full28 native suite; this is not yet a native pass. All prior failures/stopped containers and source backups remain preserved. Receipt: `linux-qa-provenance/host-successor-edcc051.json`. No application deployment or paid calls.

## Third reviewed successor — 5496458

Independent native Testing exposed a public-input leaf that the non-root actor could not read. No global/private chmod workaround was applied. Reviewed source `54964583dd18cdec512a96c7a0068f743dd3da55` validates the compiled actor hash, exact public membership and bytes before creating only its bounded read-only public projection; separate new unit tests cover that boundary.

Exact archive SHA256 `117e5bfc80b7dfcaa643fab5b803f332c74364ad6e582be75c83fc249f54bb07` and source manifest SHA256 `7e9c3da11f6d9c5fb0ddf57b786a248bd3e65a4c2b9611d23bfc3984a42e21a3` were verified. With Testing paused, all400 prior8e5 files matched. Only `services/backend/src/anvil/benchmark_qualification.py` was atomically replaced (backup `.local/source-before-549`); new `services/backend/tests/unit/test_benchmark_public_projection.py` was created fresh without overwrite. All401 successor hashes matched. No packages/images/environment or host permissions changed.

Actual-host **25 compiler/public-projection units passed** under explicit local paid-disabled configuration without SQL credentials/writes, plus **9 adapter guards passed**. Independent Testing received the exact successor for the full28 fresh native suite; no native pass is inferred. Prior stopped actors/logs remain retained and are not reused. Receipt: `linux-qa-provenance/host-successor-5496458.json`. Key expiry remains01:51:10Z; no automatic extension. No application deployment or paid calls.

## Second reviewed successor — 8e5e0a9

Independent Testing preserved a further057 failure: Harbor's helper merged Compose stderr warnings with valid configuration JSON. The reviewed fix separates only the configuration subprocess stdout/stderr while preserving restricted profile validation. It does not suppress a failed command or loosen native controls.

Pushed source `8e5e0a988e154c96bb2293af050c29cf68d44318`, archive SHA256 `8b1ccd33233336973a35252ea62437d99b307aa22b8aeb0e60f1a7a020046089`, source manifest SHA256 `cd123c57ccab863e2c7cf97829dcc11e69aa5605740d4f5d32e7ab8472549978` were verified. With Testing explicitly paused, all400 prior057 files matched, only the same two reviewed adapter/test files were atomically replaced, old copies were preserved under `.local/source-before-8e5`, and all400 successor files matched. No packages/images/configuration/permissions changed.

Actual-host adapter guards **9 passed**, including the added complete-start subcases. Independent Testing was released for a fresh full28 native suite against this exact source; a native pass remains unclaimed. Receipt: `linux-qa-provenance/host-successor-8e5e0a9.json`. Prior e4/057 failures and evidence remain preserved. No application deployment or paid calls.

## Reviewed source successor — 0574c68

Independent native testing of e4 found a real adapter defect: privileged Compose `config --output` created a root0600 file that the non-root Harbor process could not read. Testing paused before actor creation; old failure evidence was preserved. No chmod, broadened socket policy or host permission workaround was applied.

Reviewed successor `0574c68fcdd889e7fa1c4ec8b0bcdff47c06195e` was pushed, with archive SHA256 `392251dff7349828aa8ff5294c2e31f0520de8fb6ef1562946af96a09c98f432` and400-file source manifest SHA256 `701f75ec7fe0771f79a45282537d5a1c029b26c7dc0e6fecc4bbd974aa8e2461`. While Testing was paused, all400 prior hashes were verified, only reviewed `services/harbor/src/anvil_harbor/sme.py` and `services/harbor/tests/test_sme.py` were atomically replaced as the owning operator, and all400 successor hashes were verified. Original two files remain under `.local/source-before-0574c68`. No package, image, system configuration or permissions changed.

Actual-host adapter safety guards **9 passed**. Independent Testing has been handed the new exact source for the full28 native suite; no native pass is inferred from adapter guards. `linux-qa-provenance/host-successor-0574c68.json` records old/new hashes and command evidence. Earlier host-readiness metadata is historical e4 pre-test evidence, not the current source verdict. Application deployment and paid calls remain unauthorized.

## Current milestone — host ready for independent native QA, 2026-11-09T01:06Z

The exact source/runtime setup is complete and independently verifiable; Testing has received the private SSH/runner interface. **Host readiness is not a native test pass.** No application deployment or paid calls occurred.

VM `4723949448594237365`, boot disk `8660101875172681653` (30GiB balanced), private10.22.0.2, no public IP/cloud identity, automatic restart false and absolute STOP Nov15 19:30Z verified. Temporary user-approved OS Login key expires **Nov9 01:51:10.698714Z**; remove its exact fingerprint after testing. No IAM or project SSH setting was changed.

Exact e4 source/archive hashes and runtime3.12.14 verified. Backend85 packages installed from frozen uv lock into `.local/backend-venv`; separate Harbor0.25 runtime91 exact versions installed using a derived distribution-hash manifest. Original Harbor requirements are version-pinned **without** distribution hashes; canonical name/version map was checked unchanged before install. Derived SHA256 `def0d8440bcd7f67254ef890329e1b4dfafddf119fe087263158136de0151c0c`. Unversioned backend build dependency resolved hatchling1.33.0; metadata hash recorded, so fully locked build-system reproducibility is not claimed.

Dedicated Docker20.10.24/cgroupv2 uses only `.local/benchmark-docker` socket/data/exec/PID roots; default socket absent. Only the two approved Python/PostgreSQL images were pulled and Linux/amd64 repository digests verified. Fresh PostgreSQL17.6 binds **127.0.0.1:55482 only**, database `anvil_local`, migrations1–58 (58 rows). App/worker roles NOSUPERUSER/NOBYPASSRLS; evaluator remains NOLOGIN/NOSUPERUSER/NOBYPASSRLS. Vault and generic artifact roots are disjoint, owner-only0700 and non-symlink. Credentials remain host-local0600 and were not exported.

Public dependency/hash/readiness receipts are under `linux-qa-provenance/`; no environment file, private key, raw private data or raw diagnostic log belongs in that export. No system/package/image changes will occur while Testing runs.

Preserved setup failures and bounded fixes: Debian3.11 lacks tarfile data_filter; exact-hash manual bootstrap approved instead. Initial manual bootstrap omitted implicit directories and stopped before first file; empty tree preserved under `/opt/anvil.bootstrap-failed-20261109`, then corrected fresh extraction passed. Source root directory normalization was handled explicitly after pre-write validation stopped. Already-installed sudo required explicit download/reinstall mode for package hash verification. uv stdout included a valid architecture suffix; exact version/architecture accepted. Harbor source lacked hashes; strict hash mode blocked before install until the unchanged91-package hash manifest was derived. Docker20.10 rejects simultaneous bridge-name/bip flags; failed unit retained, corrected dedicated unit-v2 with explicit subnet passed. These are setup failures, not hidden native failures or skipped safety checks.

## Earlier state and preserved preflight history

## Current actual state — 2026-11-09T00:56Z

User explicitly superseded the earlier hold: “Create the isolated Anvil Linux test VM, disk, network, NAT and IAP firewall within $60. Continue Linux testing and fix issues.” That later authorization resolved the earlier automatic-review rejection. The exact approved resources have now been created in `adi-anvil-mvp-2026/us-west1-a`:

| Resource | Actual ID |
| --- | --- |
| VM `anvil-staging-native` | `4723949448594237365` |
| Network `anvil-staging-native-net` | `8017050090191235044` |
| Subnet `anvil-staging-native-subnet` | `159611463170566136` |
| Regional NAT address `anvil-staging-native-nat-ip` | `7265975432424237005` |
| Router `anvil-staging-native-router`, containing `anvil-staging-native-nat` | `8927032357452294091` |
| IAP-only firewall `anvil-staging-native-iap-ssh` | `9051667802961520580` |

VM RUNNING, private IP `10.22.0.2`, **no public access configuration, no attached cloud service account/scopes**, automatic restart false, absolute STOP **2026-11-15T19:30:00Z**, all verified from returned metadata. Creation Nov9 around00:52Z occurred after the not-before boundary. Dedicated 30GiB boot disk was specified; exact disk ID remains to be captured before final handoff.

IAP initially returned transient4047 immediately after VM creation; one delayed retry succeeded without policy changes. A loopback-only IAP tunnel and raw SSH use repository-local private key/known-hosts, avoiding global SSH files or automatic gcloud key renewal. OS Login UID2057588071/x86_64/Python3.11.2 and existing `sudo -n` operator access verified. Same user-approved temporary OS Login key received one bounded one-hour refresh for this resumed task; remove exact fingerprint after testing, with no unbounded renewal.

Public source/runtime/setup transferred to `/tmp/anvil-native-inputs`; directory owner/mode0700 verified after SCP initially created it744 (no credentials/private inputs were present). Preflight correctly stopped because Debian3.11.2 lacks tarfile data_filter; **no partial /opt tree or package install occurred**. A fully validated manual bootstrap is under coordinating-agent review, followed by source extraction using verified Python3.12's data filter. Native tests remain **not run**; the Testing agent is waiting for actual runtime/SQL/daemon readiness. No application deployment or paid calls.

## Historical events and preserved failures

## Provisioning blocked by automatic review

At19:30:10Z the clock passed the approved not-before time. The resource-creation tool request was rejected **before execution** by automatic approval review: it cited the earlier “Hold cloud provisioning” instruction and did not recognize later authorization as sufficient trusted approval for persistent network/NAT/firewall resources. No resource command ran and no QA VM/network/NAT/firewall/address was created. Do not work around this rejection with another execution path; the coordinating agent must resolve the explicit authorization conflict. Native testing remains not run. Temporary OS Login key expiry/removal remains tracked separately above.

## Access/runtime preflight update

User explicitly approved a temporary OS Login public key on the existing account. Dedicated repository-local key registered with one-hour expiry20:28:50Z on Nov8; fingerprint `290de06f1812c7115b087f4e1923b17801a03bdf8f7e51c9f12bbacbe404f838`. Remove only this fingerprint after testing; no automatic renewal. No IAM/project metadata was changed and no private-key bytes were read or printed.

Approved exact Python archive downloaded for inspection only. SHA matches the bound publisher value; manifest4533 members/1048 internal relative symlinks validated: all resolved inside `python/`, no cycles, missing targets, special members or writes beneath symlink paths. Manifest SHA256 `833d11ca26f6a175fd374b76a669b401a39887bf28896fea7384e8e39c35b506`. No extraction/execution yet; coordinating-agent review of manifest precedes installation. No cloud resources existed at this preflight update.

User subsequently authorized cloud hosting and Linux testing within the published standalone QA-host plan, USD 60 ceiling; application deployment remains excluded. Source `e4bb2d56800b6e2705b359724750c5702a003204`, migration058, archive SHA256 `68d37ec7191c64a592a9710bd592cb40e7c002a87ca7d73e88dc3f6279a3f325`. Creation not before 2026-11-08T19:30Z; absolute STOP 2026-11-15T19:30Z.

## Fresh read-only preflight

Read-only metadata verified using independent Anvil CLI/config/account. One existing VM `anvil-mvp-v1`; no proposed native names among networks, disks, routers, addresses or firewall rules. Candidate10.22.0.0/24 does not overlap observed primary subnet/routes; no secondary subnet ranges returned. Existing project metadata has `enable-oslogin=true`. No cloud resources created at this checkpoint.

Existing deploy principal has `roles/owner`; no new IAM grant is needed or proposed. Its supported OS Login username is `vasudevan_sundarababu_adi_labs_a`. Instance-only metadata SSH keys would not follow enabled OS Login. Supported login needs a short-lived public-key registration in the existing account's OS Login profile (with explicit removal afterward), or an already registered user-provided key. That is an account-profile mutation, distinct from project IAM/metadata. It has not been performed; coordinating-agent review requested. Never disable OS Login or silently add project/global SSH metadata.

Additional preflight gap: Debian12's system Python is3.11 while locked backend requires3.12. The pinned Python3.12 OCI fixture does not supply a host interpreter. Resolve an exact reviewed host Python3.12/installer version and hash before environment installation; do not silently install a floating interpreter/tool. Current image/package bindings otherwise remain as approved. No packages, images or credentials have been transferred or installed.

Native result status: **not run**. These preflight findings are not application/native test results.

## Exact dependency amendment under review

Primary versioned Python runtime: Astral release20260901 `cpython-3.12.14+20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`; [artifact](https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.12.14%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz), [publisher checksum manifest](https://github.com/astral-sh/python-build-standalone/releases/download/20260901/SHA256SUMS). TLS-verified checksum manifest read only; exact SHA256 `72748da13197c1fb161e3afeef20a6a385ff24f2165e6e2758e47008e7faba4c`. This is a publisher checksum, not independently verified signature. No binary downloaded yet.

Exact uv0.12.19 manylinux2.17/x86_64 wheel from [primary PyPI metadata](https://pypi.org/pypi/uv/0.12.19/json): SHA256 `a63d18a0aa38ee9f21a5406afbbaeb41303bcd954be9d6b7c1b95ac275e53958`, 20,478,749 bytes. No floating installer, curl-pipe-shell or system Python change. Extract reviewed tool into an isolated0700 operator directory, verify architecture/version and use direct binary. Backend installs from verified lock with frozen resolution and explicit Python path/no interpreter downloads; Harbor uses its separate hash-locked requirements, never sibling environments.

Archive installation must validate exact hashes before parsing, reject absolute/traversal paths, device/FIFO members and unsafe links, then extract into a fresh0700 owned destination without overwriting existing paths. PBS may require internal relative symlinks: permit only after full manifest validation proves link targets stay inside the owned root and no subsequent writes traverse links; otherwise stop. Verify interpreter3.12.14, Linux/x86_64 and executable prefix under the owned root. No credentials in archives/envs. Root must review this necessary dependency amendment before binary download/install.

## Dedicated daemon/operator contract

Only this disposable no-cloud-identity/no-credential host may grant the trusted QA operator root-equivalent Docker capability. Run a dedicated daemon with socket `/opt/anvil/.local/benchmark-docker/docker.sock`, separate `/opt/anvil/.local/benchmark-docker/data`, exec root and PID file, bridge/network configuration isolated from any default daemon. Do not use or chmod `/var/run/docker.sock`; do not add broad docker-group membership or weaken socket modes. Preserve owner-only source/vault directories. Avoid starting the distro's default Docker service during package setup; verify no current daemon/containers exist before dedicated initialization.

The host-only sudo policy may allow the approved operator to invoke `/usr/bin/docker` against this exact daemon; this remains full root-equivalent power on the host, not a security boundary. Review the literal sudoers command and `visudo -cf` result, capture hash and test `sudo -n` against only the intended socket. No project/global/shared-host sudoers change. Source checkout uses `/opt/anvil`, so exact ROOT, daemon path, Harbor interpreter and host bind paths match. All actor/evaluator restrictions remain enforced by reviewed adapter; no stock Harbor environment initialization.

Host-ready handoff requires verified source/archive/lock hashes, interpreter/tool versions, exact image digests, fresh private SQL head058 with app/worker/evaluator roles and evaluatorNOLOGIN separation, owner-only non-symlink vault, actual daemon/socket ownership and expiry/no-SA/no-IP metadata. Until those exist, Testing must report native checks not run.
