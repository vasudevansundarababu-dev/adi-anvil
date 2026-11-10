# Standalone Anvil Linux native QA host — approval proposal

## Final source binding and approval status

Final pushed application source: **`e4bb2d56800b6e2705b359724750c5702a003204`**, migration head **058**. Public tracked-source archive `.local/native-qa/source-e4bb2d5.tar` (git archive prefix `anvil-native-qa/`, approximately 10 MiB) has SHA-256 **`68d37ec7191c64a592a9710bd592cb40e7c002a87ca7d73e88dc3f6279a3f325`**. OS, backend/Harbor locks and Docker/sudo/Compose package pins are now bound below and in JSON; earlier pending source/package statements are historical. Independent SQL/code QA is still in progress against this exact source. Native runtime qualification is not complete.

The concrete request is approval of **up to USD 60 for this test-only host/setup/QA/cleanup**, within the additional monthly infrastructure allowance. Start no earlier than Nov 8 19:30 UTC; automatic absolute STOP Nov 15 19:30 UTC; Codex Anvil DevOps under the existing named Anvil principal handles exact-ID cleanup after evidence export. No application deployment, paid inference, new broad IAM grants or production/Praxis changes are included. Approval is still pending; no host has been created.

To review the prospective command file, run locally `python3 infra/gcp/staging_linux_commands.py`; it prints explicit isolated CLI argv plus ordered setup/cleanup review steps, never executes them. Its output remains `requires_approval=true` and `provisioning_ready=false` after source binding because static readiness is not execution authority. No unresolved package/source pin is being deferred to the host. Actual OS/package/Compose compatibility, resource isolation and native test results remain host verification gates. All **9 focused static preparation tests passed**; no boot/native pass is claimed.

## Bound approval update

Command-review correction: the print-only renderer now shows prospective commands **before approval**, avoiding a circular review. Every command uses `env CLOUDSDK_CONFIG=/Users/vasudevansundarababu/Documents/Codex/anvil-tools/cloud-config CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=true /Users/vasudevansundarababu/Documents/Codex/anvil-tools/google-cloud-sdk/bin/gcloud` with the explicit Anvil project/account. It never resolves `gcloud` from PATH, which currently points into Praxis. Output states `executed=false`, `requires_approval=true`, `provisioning_ready=false` and lists missing source bindings. No executor exists. Approval and final source/inventory checks remain independent prerequisites to any actual execution. Repository-local SSH key/known-hosts paths and instance-only key metadata are mandatory; if the CLI cannot honor them without global/project changes, stop.

Propose a **USD 60 approval ceiling**, within the existing additional USD 500/month allowance, for the USD 50.24 estimated test window. This is an operator stop/escalation threshold, not an enforced billing cap. Creation not before **2026-11-08T19:30:00Z**, absolute GCE STOP deadline **2026-11-15T19:30:00Z**, no automatic restart. Use that absolute deadline rather than a restart-relative duration; abort if expiry cannot be read back. Codex Anvil DevOps under existing principal `vasudevan.sundarababu@adi-labs.ai` owns evidence export and exact-ID cleanup. No new IAM grant is included without review.

Root verified immutable OS `projects/debian-cloud/global/images/debian-12-bookworm-v20261102`, image ID `427288226080875395`, X86_64/READY. Backend lock SHA-256 `00a917be042f5204926d3149c5e9bcbf57c0717c298afe202a20799ca58d7bb3`; actual Harbor `requirements.lock` SHA-256 `612ab41777d8eb6ec2dee6c3390705130e55d9d1a216c79df34a1597c6156ec3`. Source/archive pins are the exact values in the final binding section above.

Official Debian amd64 package bindings retrieved 2026-11-08:

| Package | Exact version | SHA-256 |
| --- | --- | --- |
| docker.io | `20.10.24+dfsg1-1+deb12u1+b6` | `daf8ff8f7aa53e8533d38e386fcc2a11e8f3891210776fb78a84b98feb4eea0e` |
| sudo | `1.9.13p3-1+deb12u4` | `ea9987f92630be504998516e1ed9c821c483131d0576ff35a09d6e7f8deff10f` |

Compose v2 is now pinned separately: Docker's official Bookworm amd64 package `docker-compose-plugin_2.39.1-1~debian.12~bookworm_amd64.deb`, 14,245,872 bytes, SHA-256 `e41fe6f9fcbf1fecdef8ecab16cfaecf5e3d910cc51825791c4484722d038603`. The coordinating agent retrieved the [official Packages metadata](https://download.docker.com/linux/debian/dists/bookworm/stable/binary-amd64/Packages) using certificate-verified HTTPS. Download only [that exact package](https://download.docker.com/linux/debian/dists/bookworm/pool/stable/amd64/docker-compose-plugin_2.39.1-1~debian.12~bookworm_amd64.deb), verify size/hash before installing on the approved host, and record actual `docker compose version`. No floating plugin or additional Docker CE engine is approved. No package was installed or binary downloaded in this preparation. Debian Docker20.10/Compose2.39 compatibility and required Harbor options still need actual host checks; installation/version probes must not trigger stock Harbor or implicit image pulls.

Sources: [Debian docker.io download metadata](https://packages.debian.org/bookworm/amd64/docker.io/download), [Debian sudo download metadata](https://packages.debian.org/bookworm/amd64/sudo/download). Install only through Debian archive-keyring-verified signed InRelease/Packages metadata for `https://deb.debian.org/debian bookworm main`; verify downloaded deb hashes above and exact installed versions. Transitive package versions/hashes must be captured from the signed resolver transaction before installation; no insecure/unauthenticated apt flags. No package was downloaded or installed here. Debian-packaged Docker must additionally prove reviewed Compose availability required by Harbor; if missing, stop for an exact plugin/package request rather than installing arbitrary software.

`infra/gcp/staging_linux_commands.py` contains prospective creation argv and prints them only; it has no process execution. Review output is available before approval. The proposed commands address only the enumerated network/subnet/NAT/address/IAP rule/VM, describe metadata and show repo-local-key IAP SSH. Names, no-account/no-scopes settings, absolute deadline and instance-only SSH metadata are explicit. Final operator must refresh collision inventory and inspect commands before executing separately; this file never executes commands.

Docker access is **full root-equivalent authority on this disposable host**, even if a command wrapper limits accidental socket selection. Do not present sudo Docker as a security boundary against the trusted operator. Approval applies only to the credential-free dedicated test host/daemon; never a shared, production, Praxis or source-key host. Actor/evaluator containers retain their reviewed restricted/no-network configuration. No sudoers policy or IAM was changed during preparation.

Prepared 2026-11-08. **Nothing below has been provisioned or executed.** This disposable test host is proposed to run fresh fictional SQL/native tests and preserve exact evidence. It does not connect to existing Anvil/Praxis databases or task banks. The accompanying JSON is non-executable; final source/package bindings are complete while user approval and independent runtime evidence remain required.

## Exact proposed resources

Project `adi-anvil-mvp-2026`; zone `us-west1-a`; regional resources `us-west1`. VM `anvil-staging-native`, `e2-standard-4` (4 vCPU/16 GiB), new 30 GiB balanced disk `anvil-staging-native-boot`. Dedicated network `anvil-staging-native-net`, subnet `anvil-staging-native-subnet`, candidate CIDR `10.22.0.0/24`; dedicated router/NAT `anvil-staging-native-router` / `anvil-staging-native-nat` and one regional NAT IPv4 `anvil-staging-native-nat-ip`. No public VM IP, load balancer, web domain or application release. Refresh collision/route/secondary-range inventory before assigning CIDR; the observed primary subnet list did not include this candidate.

VM has **no attached cloud service account and no OAuth scopes**. No cloud/source-control/provider private keys copied to it. Source is a reviewed, hashed archive transferred by the operator; no GitHub write access. Network accepts only TCP22 from IAP range `35.235.240.0/20` via firewall `anvil-staging-native-iap-ssh` targeted exclusively to this VM. No PostgreSQL, Docker API, HTTP or evaluator ports are exposed to the VPC/internet. Operator shell obtains no GCP IAM identity from the VM.

Use existing authorized Anvil deploy principal for creation; exact identity and permissions must be reviewed before execution. IAP access must bind only that reviewed human operator to this VM/port22 using a resource-scoped/conditional grant if existing permissions do not suffice. Do not add project-wide owner/editor roles or project-wide SSH keys. Use a repository-local SSH key/config, instance-only public-key metadata and `block-project-ssh-keys=TRUE`, provided organization OS Login policy permits; otherwise stop and review OS Login access rather than disabling policy. No global SSH/config edits, no sibling credentials.

## Seven-day envelope, separate from application staging

Assume 168 running hours, no discounts/free tiers. Rates are the official sources cited in `staging-plan.md`; Oregon selectors remain a final quote check. The earlier $352.48 core staging figure is a **proposal envelope, not actual incurred spend**, and is not added as if resources already existed. This standalone host requires its own NAT; do not assume an uncreated staging NAT exists.

| Item | Calculation / allowance | USD |
| --- | --- | ---: |
| E2 compute | 168 × $0.13402284/hour, rounded up | 22.52 |
| 30 GiB balanced disk | 30 ×168×$0.000136986/GiB-hour, rounded up | 0.69 |
| Standalone NAT plus one IPv4 | 168×($0.0014+$0.005)/hour, rounded up | 1.08 |
| NAT processing | 10 GiB×$0.045 | 0.45 |
| Optional sanitized evidence storage | 10 GiB-month regional standard snapshot allowance×$0.05 | 0.50 |
| Internet transfer / package staging reserve | Allocation, not tariff-derived | 5.00 |
| Logs / evidence transfer reserve | Allocation, not tariff-derived | 5.00 |
| Contingency | Explicit allocation | 15.00 |
| **Seven-day approval envelope** | **No paid model/judge calls** | **50.24** |

No Cloud Build or new container image build is assumed. OS package setup and **only the exact two pinned container images** below need explicit approval as part of host setup; no arbitrary image pull/build/load, stock Harbor probe or shared daemon access. If additional dependencies/images are needed, stop and report the exact request. A thirty-GiB disk may be too small for retained containers; set a bounded retained-evidence policy and stop on low space instead of silently expanding or pruning unrelated resources.

For comparison, 730h compute $97.84 + disk $3.00 + standalone NAT/IP $4.68 + processing $0.45 + evidence $0.50 + reserves $10 + contingency $15 = **$131.47/month** if the host accidentally remains running. That is below the user's additional $500/month allowance by itself; concurrent application staging needs consolidated actual-cost accounting. Neither estimate nor billing alert is a hard cap. Taxes/support/domain registration excluded; usage beyond allowances requires re-estimation.

## Automatic expiry and residual charges

Set GCE `--max-run-duration=604800s --instance-termination-action=STOP --no-restart-on-failure` at creation, plus an absolute seven-day `terminationTime` **instead of** max duration if the exact approval/start window is known. Do not set both; an absolute deadline avoids restart extending the window. Read back scheduling metadata before tests and reject absent expiry. GCE documents this mechanism in [limit VM runtime](https://docs.cloud.google.com/compute/docs/instances/limit-vm-runtime) and [create flags](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/create). No guest cron, daemon self-restart or host cloud credentials are needed.

STOP ends compute but **does not delete disk/NAT address or evidence**. Residual monthly disk $3.00 + one retained NAT IPv4 $3.65 + 10 GiB evidence allowance $0.50 ≈ **$7.15/month**, plus any gateway assignment/processing, logs or transfer until cleanup. The exact cleanup owner/deadline must be named before approval. After sanitized evidence review, operator deletes only the enumerated test VM/boot disk, NAT/address/router/firewall/subnet/network, repository-local temporary SSH key and approved evidence snapshot. Do not delete current Anvil/Praxis resources or broad prefix matches. Capture exact created resource IDs so cleanup is explicit. Stop and cleanup are separate actions; any retained private data requires reviewed retention.

## Source/runtime/input bindings before execution

- Exact reviewed source/archive SHA and migration head **058** are bound at the top and in JSON; source-policy/runtime hash must match frozen test protocols. Verify recorded lockfile hashes and exact Linux OS image self-link; no floating OS family accepted.
- Fixture image: `python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e`.
- PostgreSQL image: `postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3`.
- Independently locked backend and Harbor 0.25 environment at `<ANVIL_ROOT>/.local/harbor-venv/bin/python`; exact Docker/sudo/Compose versions and hashes are bound above. Dedicated socket `<ANVIL_ROOT>/.local/benchmark-docker/docker.sock`, dedicated-host root-equivalent operator capability and matching host bind paths. No standard shared `/var/run/docker.sock`.
- Fresh PostgreSQL on this host only, bound Unix socket/loopback. Create fresh fictional database/identities, apply reviewed migrations, and preserve app/RLS plus evaluator separation. `DATABASE_URL` is the trusted coordinator app connection. `ANVIL_BENCHMARK_EVALUATOR_DATABASE_URL` must connect with `current_user=anvil_benchmark_evaluator` via separately scoped login/SET ROLE setup; the evaluator role itself stays NOLOGIN. DSNs never enter actor/evaluator containers.
- Fresh owner-only non-symlink vault/work roots; no existing application data. Explicit UUIDs, individual evaluation-review duty, active authorized operator and exact source/current policies; flags are not authority.
- Single bounded native invocation first: `python -m anvil.benchmark_offline_worker --project <UUID> --run <UUID> --operator <UUID> --max-trials 1`. Process-scoped offline/native switches only; all real paid/generation/support/email paths off. A larger test matrix is explicit, at most CLI's bounded18, and must not retry ambiguous dispatch.

## Non-executed command review and test gates

Prospective creation commands specify exact project/zone/network/subnet/disk/image and `--no-address --no-service-account --no-scopes`, instance-only SSH metadata, labels and expiry. Network/router/NAT/firewall commands enumerate only the resources above; no existing policies are mutated. The renderer is review-only and has no executor. User approval, fresh inventory and final command inspection are mandatory before separate execution.

After approval: verify isolation/expiry/identity metadata; install only reviewed dependencies and pins; verify image digests/OS; fresh SQL migrations and RLS/evaluator-login tests; native resource/cancel/fence/private-leak/unknown-dispatch tests; exact committed-source commands/results/environment hashes. Collect failures honestly. Stop before any application deployment, live calls or merge. The approval decision requested is **this standalone seven-day test host, bounded $50.24 envelope, exact setup pins and expiry/cleanup responsibilities**, with the remaining binding fields completed—not an application deployment approval.
