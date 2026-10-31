# Harbor cloud preparation — disabled

Version0.2.1 prepares the existing Anvil host for a later, separately authorized bounded
OpenAI Harbor run. This deployment supplies no provider key, no authority values, no paid
activation and no new identity or IAM access. Legacy marketing authority is not reused.

`ANVIL_LIVE_PROVIDERS_ENABLED=false` and real email remain mandatory in cloud mode.
Only Harbor recognizes the separate `ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED` flag. The renderer
always writes it as `false`, even if its parent environment says true; every standard
redeployment therefore returns admission to disabled. Health reports `harbor_live_dispatch`
separately. A future `gated` value means only the runtime admission switch is on, not that
any plan is ready or a call is authorized.

## Fixed private locations

| Existing VM path                                        | Read-only container path            | Required owner/mode                        |
| ------------------------------------------------------- | ----------------------------------- | ------------------------------------------ |
| `/var/lib/anvil/harbor-private/`                        | `/app/.secrets/`                    | directory UID10001,0700                    |
| `/var/lib/anvil/harbor-private/openai_api_key`          | `/app/.secrets/openai_api_key`      | later operator-supplied file UID10001,0600 |
| `/var/lib/anvil/harbor-authority/`                      | `/app/.local/`                      | directory UID10001,0700                    |
| `/var/lib/anvil/harbor-authority/harbor-authority.json` | `/app/.local/harbor-authority.json` | later operator-supplied file UID10001,0600 |

Startup prepares empty directories only and refuses symlinked private directories. Mounts
reach the API (UID10001) and dedicated Docker-host Harbor worker (root) only. The normal
worker, web, ops and candidate containers receive neither mount. The root Harbor worker
can read the same API-owned private files; group/world-readable files and symlinked files
are rejected. Cloud OpenAI environment-value keys are rejected; use the fixed private file.
Only the trusted server mediator reads a key. The candidate gateway has an ephemeral
socket/token and no key, authority, cloud identity or database credentials.

## Later handoff, after exact authorization

These are preparation instructions, not permission to execute them now:

1. Obtain explicit user approval of the exact OpenAI model, one-trial task/package hashes,
   total API ceiling, current input/output token rates, pricing revision and both authority
   and pricing expiries. Rates are integer micro-USD per million tokens; the cap is integer
   micro-USD. No amounts or dates in historical marketing configuration count as authority.
2. A trusted operator creates the two files at the fixed existing-VM paths above using an
   approved private channel. Never place the key in chat, repository files, command arguments,
   process environment, logs or task uploads. Apply UID10001/mode0600 and verify only file
   metadata and secret-present booleans. No new Secret Manager resource or IAM grant is needed
   by this file-based preparation. The current deployment leaves both files absent.
   These paths are on the existing data disk, whose retained snapshots may preserve copies.
   Future rotation must revoke the old provider key; deleting a file alone is not revocation.
3. Authority JSON must validate the `Authority` schema in `anvil.harbor_agents`: unique
   `harbor:` reference, exact `project_id`, `provider="openai"`, exact `model`,
   `total_cap_micro_usd`, `input_micro_usd_per_million_tokens`,
   `output_micro_usd_per_million_tokens`, `pricing_revision`, `expires_at`,
   `pricing_expires_at`. Malformed, missing, expired or publicly readable authority blocks
   readiness. It is operator-held exact user authority, never a task-author declaration.
4. Keep admission disabled while configuring the reviewed provider/model connection and
   creating a fresh exact-package plan. Every adapter/code, connection and authority change
   requires a fresh plan binding. The Product Owner reviews external-processing rights and
   the exact run, with clean evidence and expiry; existing independent-owner rules apply.
   Two real distinct Admins must each approve activation and exact paid scope. Do not create
   substitute approvers, switch seeded accounts, alter memberships or fabricate decisions.
5. Only after a separate explicit activation/launch authorization may the operator edit
   `/var/lib/anvil/config/harbor.env` to set the Harbor-only flag true, retaining
   `OPENAI_API_KEY_FILE=.secrets/openai_api_key`; legacy live/email flags stay false. Recreate
   only API and Harbor-worker via the existing `/opt/anvil/compose.yaml` and `harbor` profile.
   Verify exact-plan readiness before any explicit launch. A flag, key or authority file
   alone cannot pass readiness. Reverting the flag false stops admission at every stage;
   use the application's cancel/reconcile path for an already dispatched or unknown call.

One call per admitted stage, maximum32768 prompt bytes and2048 output tokens; full run
ceiling is reserved durably before launch. No automatic SDK retries; ambiguous dispatch
retains its reservation. Source references and future evidence remain isolated. Runtime
failures cannot silently release held spending or grant new authority.

## Verify preparation without activation

Read `/api/v1/health`: expect version0.2.1 and `harbor_live_dispatch="disabled"`.
On the existing VM, inspect container UID, mount targets/read-only booleans and file-existence
booleans only. Expect absent key/authority files, false Harbor admission, false legacy live
flag and no new paid calls, approvals or spending reservations. Do not print environment
files or credential contents. Application plan readiness remains blocked.

Local tests cover disabled/missing/expired/unsafe-file paths, enabled admission with missing
authority still rejecting API launch, and explicit network-free private-file SDK/gateway
stubs. These are software qualification, not live model verification.
