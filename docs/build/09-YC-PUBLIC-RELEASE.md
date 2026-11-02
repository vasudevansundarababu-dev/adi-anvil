# YC public repository and existing-host release

User authorized this scope on 1 November 2026. It supersedes earlier no-push,
no-cloud-deployment, Anvil-only and classic-UI-retention restrictions for this release.
Preserve unrelated edits, all application data and the classic Git comparison branch.

## Confirmed decisions

- Create public `vasudevansundarababu-dev/adi-anvil`; publish reviewed code there.
- Update `vasudevansundarababu-dev/adi-praxis` and make it public.
- Reuse existing GCP targets, budgets, users, databases and URLs. Anvil's target is
  `adi-anvil-mvp-2026/us-west1-a/anvil-mvp-v1`, infrastructure budget $150/month.
  Praxis CLI is configured for `adi-praxis-test-0928`; verify existing service resources
  and budget before rollout. Do not create replacement projects.
- Anvil application should expose only the modern workspace. Retire classic navigation
  and redirect supported legacy bookmarks; retain data/API compatibility where required.
- Enable code generation only: OpenAI `gpt-6.1-sol`, existing whole-import cap $10.
  User authorizes secure transfer of the saved generation key into cloud secret storage.
  Do not expose values in docs/chat/build output/Git. Paid evaluation stays disabled.
- README and linked architecture, source map, tests, local setup, deployed login and
  limitations documentation must be clear, concise and verified for both repositories.

## Completed readiness

Both public GitHub repositories now exist with the reviewed release branches and
updated READMEs. Both GCP logins were refreshed and verified. Anvil uses
`.local/gcloud-anvil` / configuration `anvil-mvp-v1`; Praxis uses its existing CLI login.
Do not substitute sibling credential stores. Existing CLI binary can be shared;
credentials must remain separately selected.

Anvil's managed-secret adapter and registry image were deployed and independently
verified. All three cloud golden successors passed actual tool probes, isolated grading
and native Harbor software smoke checks without model calls. Both applications' exact
deployed images/versions, backups and limitations are recorded in
[the release report](../generated/yc-release-2026-11-01.md). Reviewer documentation has
been reconciled with this evidence. Existing assigned accounts/data remain intact.
This requested rollout is complete; do not automatically repeat it at later checkpoints.

## Delivery gates

Read durable state and repository instructions first. Coordinate writers. Preserve
unrelated changes and untracked SDK/video artifacts. Review both working trees AND the
history to be published for secrets/private material before changing visibility or
pushing; exclude local credentials, raw/private logs, recordings and archives. Do not
rewrite or discard existing history without a concrete reviewed need and authorization.
Run meaningful regression/build/access tests, repair failures, document actual gaps.
Prepare backups and rollback, then deploy only confirmed services with data-preserving
migrations. Verify deployed commit, TLS, OIDC/login, source import, generation settings,
supplied image/worker health and disabled paid evaluations. Do not automatically send
paid model requests as smoke tests. Never mark blocked/live-not-run checks as passed.

Night window remains22:00–06:00 America/Chicago. Do safe local work while credentials
are pending; do not infer successful reauthentication. Once deployed, record verified
URLs, versions, results and safe login steps without passwords, then report completion.
