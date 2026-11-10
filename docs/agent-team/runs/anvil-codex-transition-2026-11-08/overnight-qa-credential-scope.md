# Proposed exact QA credential resources

Status: prepared and tested; not provisioned. Automatic review rejected scheduled cleanup outside the existing VM/network-only cleanup authority. Owner approval to add the two resources below is pending.

- Secret: `anvil-qa-model-credentials`, in `adi-anvil-mvp-2026`, user-managed replication only in `us-west1`.
- Service account: `anvil-qa-20261110@adi-anvil-mvp-2026.iam.gserviceaccount.com`.
- Access: only `roles/secretmanager.secretAccessor` and `roles/secretmanager.secretVersionAdder` on that new secret. No project-level role, service-account key, production secret, operator credential mount or Praxis access.
- Qualification: immutable service-account ID, secret creation time, exact policy and project number must match fresh readback. Default VM admission continues to reject workload identities. A deliberate qualified-identity readback is required before attaching this identity to the exact owned QA VM; absolute stop, private networking and actor metadata denial remain required.
- Retention: no deletion before 2026-11-12 18:00 UTC. Delete only these newly owned resources after the QA VM is absent, verify immutable identities immediately before deletion, and verify absence afterward. Partial cleanup may resume only the same immutable identity.
- Boundaries: configuring credential storage grants no processing-rights review, source approval, model activation or spending authority. Paid paths remain disabled until all existing application controls pass.

Actual exact-name inventory found zero matching service accounts and zero matching secrets. Eight pure boundary tests pass, including refusal before retention and refusal of replacement identities. No secret versions were read and no resources were created. These tests are not cloud qualification receipts.
