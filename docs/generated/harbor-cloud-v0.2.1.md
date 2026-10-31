# Harbor cloud preparation v0.2.1

User authorized code and deployment preparation on the existing Anvil host, with paid
calls disabled throughout. No exact new model/budget authority or key has been supplied.
No IAM, credentials, approvers or account permissions are created by this increment.
Code checkpoint: `4693f00f0aec1eb54bd212ac27a658f918ec0867`.
Existing-host rollout: `4693f00-1793412536`, Cloud Build
`3c163d82-a103-4757-9683-7b1166c9734e` in us-west1, SUCCESS. Existing VM rollout completed.

Legacy cloud live dispatch/email stay forbidden. A separate Harbor-only admission flag
defaults false; the runtime renderer always resets it false. Only the API and dedicated
Harbor worker receive empty read-only private directory mounts. Authority and key values
remain absent. Unsafe/expired/missing files fail closed, and current pricing/budget/rights,
exact-version binding, independent owner and real distinct-Admin controls remain required.
The future operator handoff is [documented](../runbooks/harbor-cloud-admission.md).

## Verification

- 181 unit tests passed: disabled/missing/expired/unsafe-file paths, cloud flag separation,
  renderer forcing disabled, private-file SDK MockTransport stub with no network.
- 90 isolated integration tests passed,188.66s: cloud admission off/on with missing authority
  still rejects launch; existing role/project/rights/billing/version fences, exact cloud task
  reference/negative checks and explicit stub gateway/ledger behavior.
- Final production/types/lint/format/API contracts passed. No dependencies changed;
  backend/web versions0.2.1, schema025.
- Backend container built. API UID10001 and root-worker identities passed an empty read-only
  mount rehearsal: flag disabled, no key/authority, attempted private-mount write rejected.
- Compose normalized configuration verified private mounts read-only on API/Harbor only;
  ordinary worker/web/ops/migrate do not receive them, API has no Docker socket.
- Read-only security review reported no critical blocker. Pre-upgrade immutable-history and
  paid-ledger counts/checksums captured privately, without printing raw records or secrets.

All8 browser journeys passed (1.4m), including empty pricing/cost defaults and disabled
Harbor health. The legacy marketing test explicitly selects its historical fixture model;
the previous reliance on an auto-filled model was removed without restoring stale defaults.
Post-deployment API/database/TLS/OIDC/web/private-admin smoke passed. Read-only verification
passed via `python3 /private/tmp/anvil-v021-verify.py`; sanitized evidence is retained in
ignored `artifacts/test-runs/cloud-v021-disabled.json`:

- API version0.2.1 ready, legacy inference disabled, Harbor admission disabled.
- Key and authority files absent; no actual values provisioned or uploaded.
- API UID10001, Harbor worker UID0; private directories UID10001/mode0700.
- Both private mounts read-only on API/Harbor only; normal worker/web have none and API
  has no Docker socket. All verified services use release4693f00-1793412536.
- Historical immutable records, approvals and paid-ledger row counts/checksums match the
  pre-upgrade fingerprints exactly. Paid-call records remain0; no new paid approval or
  reservation was created.

The first final HTTPS probe encountered the local Python installation's missing CA store.
The OS curl client passed with certificate verification enabled; no TLS bypass was used.
Later activation remains blocked on exact fresh user authority/model/budget/current pricing,
private operator-supplied files, reviewed rights and real application approvals. The secure
handoff documents those steps; it does not grant permission to perform them now.

The first aggregate attempt detected a source edit through the existing harness code hash;
the stable-tree rerun passed. The guard was preserved. Mock/reference checks never count
as live model performance. Existing independent PO software-check acceptance remains blocked.
