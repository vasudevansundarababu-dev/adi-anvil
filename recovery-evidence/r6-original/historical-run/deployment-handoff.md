# Handoff: DevOps deployment → user (deployed and verified)

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Repository / branch / source commit:
  - repository and branch: `vasudevansundarababu-dev/adi-anvil`,
    `codex/anvil-agent-team-2026-11-06`;
  - approved snapshot: base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` plus
    `finalization-evidence/code-manifest-r6.sha256`, tree `18fca788…`;
  - deployed as the local, never-pushed release commit
    `15e35f12725a89be6e507b2eb73d4433e666dd76`.
- From role / proposed next role: DevOps → user (release review). No next role is started.
- Authority: `approvals.md` §9 (relayed by the Codex coordinator on 2026-11-06). The GCP
  sign-in was done by the user in their own terminal.

## Deployed

- **URL:** https://anvil-34-36-217-66.sslip.io/workspace
- **Target:** project `adi-anvil-mvp-2026`, `us-west1-a`, VM `anvil-mvp-v1`, load balancer
  `34.36.217.66`.
- **Build:** tag `15e35f1-1794018124`, Cloud Build `1f2b1a68-44d3-44b5-bdc7-8acdf0be710e`.
- **Image digests:**
  - backend `0becacc8…`;
  - web `80e0a269…`;
  - harbor `efaa5c3d…`;
  - golden-tools `f5506d52…`.

  Full digests are in `deployment-report.md`.

## Input artifacts (SHA-256)

- `approvals.md` `bf49a298a1417cfcf11cb3b96e9f1545f03db41b26f7e1246987b1d556b3413d`
- `finalization-qa-handoff.md` `fa304258b1d3b6bd40f57fee1218200c367f3585bea0558fa1836d5f22d35f29`
- `finalization-evidence/code-manifest-r6.sha256` `5c15faf05331d58b26342ce7a40d8b0df5f4be62d2619a2840fbf0cdab3f7c7b`
- `deployment-evidence/release-r6.patch` `3e3552e21f37388aca0f7985c54e169f54ce02bc318b0368ec19e334b6389e66`

## Output artifacts (SHA-256)

- `deployment-report.md` `4c1b6f9382485d2bf3bab73e606d742e3273fe935cdbb0b093a85b3a7bdc3768`
- `deployment-evidence/rollback-record.txt` `d3597a8dbbddbb44e7a7bbba2951ce1a9d0535bf6ee5f98ba7fd3b6740822c4b`
- `deployment-evidence/deploy-attempt1.log` `bb8684c39cba86e36661e7e88d855e6f06e32cb56b696cdf2801453bacbbc9cf`
- `deployment-evidence/deploy-attempt2.log` `de2498a391e5ae6701d039e11be51e6c34bb38a0880e74844a1a8ffafcfeb46e`
- `deployment-evidence/deploy-attempt2-wrapper.sh` `75d96cd88f8cf4f69b4551ee3b765d8c30989d3cb31f0b11e8db94b8769029f6`
- `deployment-evidence/deployment-json-after-deploy.diff` `79cc2ca775eba0c208088f5e389b360082bba7d087674542ca7b877a66db9e73`
- `deployment-evidence/gcloud-setup.txt` `edeffee023850499622ab6e21912fde92f9d946288d98654dafa4a77a8e70030`
- `deployment-evidence/preflight.txt` `f674a083b17cb8a67b7313131ac71ebfde35f15d01f54040dd79a321e575c5f0`
- Superseded blocked-preflight copies:
  - `deployment-evidence/deployment-report-blocked-preflight.md` `e64b788c…`;
  - `deployment-evidence/deployment-handoff-blocked-preflight.md` `11779de6…`.

## Evidence (passed / failed / blocked / not run)

**Passed:**

- **Source binding:** the release commit tree equals the approved tree, and the r6
  manifest verifies inside the release worktree.
- **Running images:** the running image IDs equal the registry digests for build
  `1f2b1a68`.
- **Backend code:** the deployed `worker.py` hash equals the r6 manifest hash (`ec5afade…`).
- **Readiness text:** the live bundle contains the r6-only readiness strings.
- **Startup and migrations:** startup OK, and `migrate` exit 0 with no new migrations.
- **Health:** api and database `ready`; live inference `disabled`.
- **Edge:**
  - OIDC issuer unchanged;
  - public Keycloak admin 404;
  - TLS valid until 2026-12-30;
  - HSTS present.
- **Live providers:** off in the api and worker.
- **Feature settings:** carried over unchanged (import generation, generation secret
  reference, installation admins, support Vertex, OS Login).
- **Infra files:** identical to the previous VM metadata.
- **Data stores and edge:** not recreated.
- **Praxis:** read-only GETs unchanged (307 and 200).
- **Temporary SSH key:** removed.

**Failed, then recovered:** attempt 1. The agent shell's `umask 077` made the image's source
files unreadable to its non-root user, so `migrate` failed. The release was rolled back to
the recorded images and verified, the cause was fixed (file modes only; the tree was
unchanged), and attempt 2 succeeded.

**Not run:** an authenticated reviewer UI walkthrough on the deployed host, and a GCP
restore rehearsal.

## Open questions and material risks

1. **Harbor dispatch status.** `harbor_live_dispatch` changed from `gated` to `disabled`.
   - **Cause:** this is the documented redeploy behavior: `render_config.py` always writes
     the Harbor flag as false (`docs/runbooks/harbor-cloud-admission.md`).
   - **Action needed:** re-enabling requires the runbook's separate activation/launch
     authorization, step 5. It was not re-enabled.
2. **Outage during attempt 1:** about 4 minutes of API and worker downtime, about
   02:16–02:20Z.
3. **Uncommitted `deployment.json` change.** `infra/gcp/deployment.json` in the release
   worktree now records `last_deployment=15e35f1`, and the generation-secret reference was
   normalized to the project-ID form. It is uncommitted, and nothing is pushed.
   - **Decision needed:** whether to bring this record into the branch.
4. **Unused image.** The unused attempt-1 image tag `15e35f1-1794017439` remains in
   Artifact Registry.
5. **Credentials left on this runtime.** gcloud credentials remain in the runtime under
   `.local/gcloud-anvil`. Revoke them when done:

   ```sh
   . .local/gcloud-anvil.env && gcloud auth revoke --all
   ```

6. **Carried-over QA limits:** see `deployment-report.md`.

## Rollback

- **Code:** restore the 4 image metadata keys to the recorded rollback tags and re-run the
  startup script (exact commands are in `deployment-report.md`). This was tested during
  attempt 1.
- **Data safety net:** snapshot `anvil-data-pre-r6-202611070208`.

## Next steps

- **Proposed next allowed scope:** user release review. Optionally:
  - an authenticated reviewer walkthrough;
  - a decision on recording `deployment.json` and the release commit;
  - revoking the runtime credentials.
- **Prohibited actions:**
  - pushes, other branches or `main`;
  - Praxis operations or changes to the Mac checkout;
  - IAM grants, re-enabling Harbor admission or provider calls without separate
    authorization;
  - destructive database actions.

## Approval

- Decision: PENDING HUMAN APPROVAL (release review). The deployment itself was executed
  under §9.
- Human approver / actual approval message reference / timestamp:
