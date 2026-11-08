# Independent verification — e4bb2d5

Application/test checkpoint: `e4bb2d56800b6e2705b359724750c5702a003204`, pushed to the existing Anvil branch. Staging preparation `88bcb5d` is a separate plan-only descendant, not evidence of a deployed release. The 409-path candidate manifest is `qa-candidate-source.json`, SHA256 `b1e36b28e1f13a8c1de88b1c35ab188bae258eeecbc192d871132a8a07abaa66`. All manifested bytes were unchanged after the checks below. Next's production build rewrote two generated route-import lines in `next-env.d.ts`; Testing restored only those exact lines to the committed contents and rechecked the manifest.

## Actual local results

| Check | Result |
| --- | --- |
| Fresh isolated database migration001–058 | Passed; `anvil_finalqa_e4bb2d5`, new owner-only vault/artifacts and dedicated graph |
| Full backend unit suite | 778 passed |
| Full benchmark SQL/API/security suite | 168 passed,28 skipped |
| TypeScript, Ruff, Prettier, tracked-source secret scan | Passed; secret scan747 files,zero findings |
| Node provider/readiness checks | 12 passed |
| Separately locked Harbor adapter guards | Seven passed |
| Production Next build | Passed compilation, types and generated pages |
| Actual authenticated production-preview browser journey | Two passed: real Keycloak login, persisted quarantined fictional import, header/CSRF checks, no fabricated scores; retry key survives reload and separates changed bodies/projects |
| First clean standard integration run | **One failed,189 passed,19 skipped**; retained as failure evidence |
| Clean standard integration repeat | 190 passed,19 skipped;89.28 seconds, source unchanged |

Each `qa-e4bb2d5-*.json` receipt records command, UTC time, duration, exit status, private raw-log SHA256, explicit skips and manifest verification. Counts overlap: independent security/evidence cases are included in168, not additional passes. SQL qualification/capture fixtures deliberately manufacture trusted metadata solely to exercise contracts; they are not native qualification evidence. Actual native/resource/SDK/Harbor and authentic Praxis integration skips remain unrun requirements.

## Remaining finding

The initial integration failure was `test_manifest_dryrun_atomic_commit_dedup_and_quarantine`, reading `data` from a task-create error response after choosing the first UUID-ordered task as a template. A bounded rerun returned201 and passed. No failure response was captured in the original run, so neither a template-selection root cause nor a product repair is established. No application guard or test has been weakened. An external diagnostic wrapper subsequently introduced16 failures because it mishandled `json=None`; that diagnostic is invalid for application qualification and is preserved separately, not counted as new product failures. The corrected diagnostic was stopped at the parent's request in favor of a clean uninstrumented repeat. That repeat passed all190 runnable tests with19 explicit skips; the original intermittent failure was not reproduced and remains an open test-reliability caveat. Its failed receipt is retained. The clean-repeat raw-log SHA256 is `3c5f44e0aa0b4e47f98f99ff988c5b9d6213cf1107fbc4cb0c10ad1d40ad8e50`.

## Limits and handoff

These checks verify the offline application slice and migration058's typed output/absence evidence and scoring rules. They do not establish Linux native actor isolation, real model performance, authentic Praxis data integration, live dispatch or deployment readiness. Missing/empty mapped outputs affect their own criteria; missing unmapped required reports remain unresolved with raw diagnostics retained. Whole-task zero requires an explicitly frozen hard constraint.

The application preview uses only newly owned loopback services, synthetic identities and fictional import data. Live-provider/email/tracing flags remained false; native opt-in was absent. No paid calls, cloud provisioning, deployment, Praxis access or original checkout changes occurred. Dedicated Linux test-host approval remains pending. A release verdict must retain the original intermittent integration failure and obtain the remaining native evidence; green unit counts alone are not completion of the full benchmark plan.
