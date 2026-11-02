# YC release verification — 1 November 2026 (America/Chicago)

## Deployed applications

| Application | Release                                                      | Existing destination                                                 |
| ----------- | ------------------------------------------------------------ | -------------------------------------------------------------------- |
| Anvil       | Application commit `ec210a9`, image tag `ec210a9-1793593400` | `adi-anvil-mvp-2026/us-west1-a/anvil-mvp-v1`                         |
| Praxis      | Commit `ddc8446b`, build `yc-ddc8446b-20261101`              | `adi-praxis-test-0928/us-central1`, four existing Cloud Run services |

[Anvil](https://anvil-34-36-217-66.sslip.io/workspace) ·
[Praxis console](https://praxis-web-yu2jtyqhea-uc.a.run.app) ·
[Praxis candidate](https://praxis-candidate-yu2jtyqhea-uc.a.run.app)

Both repositories are public. Anvil release branch: `codex/anvil-modern-workspace`;
Praxis release branch: `codex/praxis-anvil-harbor`. Praxis main received documentation
only; its application history/default branch was not replaced. Only explicit reviewed
branches were pushed; no Codex snapshot refs, SDK archives, credentials or raw logs.

## Deployment checks

- Cloud Build succeeded for both applications. Anvil API/web/Harbor containers were
  independently inspected and match the expected new image tag, all running.
- Anvil root redirects to the modern workspace. Legacy task bookmarks redirect to
  modern task pages; no classic comparison link remains. OIDC discovery, TLS and the
  real Keycloak login form passed; public Keycloak administration returns404.
- Praxis version endpoint reports the new build/commit. Console login and candidate
  endpoints return200. `/readyz` reports PostgreSQL and Redis healthy. The attempted
  `/api/v1/health` and `/healthz` paths returned404; they are not counted as passing checks.
- Anvil generation key transferred directly from the saved local credential to the
  designated Secret Manager resource and verified by bound readback; no value was
  printed, committed, or supplied to candidate containers. Cloud cap is exactly$10
  per whole import. Local settings were left unchanged. Runtime flags verify generation
  enabled and paid evaluation disabled.
- Cloud-native software checks passed for Marketing, KYC/AML and Fraud: each passed
  seven generated fixtures, seven held-out QA fixtures, actual supplied-image MCP/tool
  probes and a real Harbor nop smoke. Total21 generated +21 source QA cases,3 Harbor
  smokes, zero model calls. These are software conformance, not live model quality.
- Cloud golden v1.1.0 successors pin the real registry OCI digest. Original local
  sources/versions and run bindings remain unchanged.
- Backups completed before migrations: Praxis SQL backup1793593073237 SUCCESSFUL;
  Anvil disk snapshot `anvil-pre-yc-20261101` READY. No volumes/databases/users deleted
  or reseeded. Praxis rollout explicitly skipped demo setup.

The first Anvil startup attempt failed during image pulls. A direct retry succeeded;
the nested read-only authority mount point was prepared and startup rerun successfully.
Deployment checks now assert running image identity, so a healthy old release cannot
be mistaken for a successful new rollout. Follow-up infrastructure/docs commits do not
change the application images listed above.

## Local evidence and limits

301 Anvil unit tests, production `pnpm check`, TypeScript and focused modern browser
journeys passed. Two full-suite browser selectors initially matched both generation and
evaluation model inputs; selectors were scoped to the evaluation editor and rerun.
The final complete modern browser suite passed14 tests in1.0m. Praxis typechecks,121 shared tests
and452 API tests passed. Earlier isolated three-golden acceptance passed18 native Harbor
evaluation trials and3 notebook roundtrips using controlled providers.

Existing invited accounts are retained; no password is published. Authenticate with
your assigned account, import a cloud golden, and use Import & generate. New generation
requires the Admin's exact source/configuration permission within the shown cap. Paid
evaluation remains off by the user's release choice. No live generation/evaluation was
triggered as a deployment smoke test; authenticated cloud user journeys need the user's
own sign-in. Notebook support is manual Colab/Jupyter roundtrip, not hosted provisioning.
Praxis remains the existing test/demo mode with real Vertex and simulated candidate
identity/sign-in/email; it is not represented as the private Terraform production target.
