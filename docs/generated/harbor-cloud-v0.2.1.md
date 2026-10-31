# Harbor cloud preparation v0.2.1

User authorized code and deployment preparation on the existing Anvil host, with paid
calls disabled throughout. No exact new model/budget authority or key has been supplied.
No IAM, credentials, approvers or account permissions are created by this increment.

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
Existing-host disabled rollout remains pending. Post-upgrade
verification must confirm unchanged fingerprints, both live flags disabled, absent key and
authority files, correct UID/mount modes and zero new paid calls/approvals/reservations.

The first aggregate attempt detected a source edit through the existing harness code hash;
the stable-tree rerun passed. The guard was preserved. Mock/reference checks never count
as live model performance. Existing independent PO software-check acceptance remains blocked.
