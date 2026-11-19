# Independent QA release phases

This additive workflow prepares builds; it does not deploy, migrate, run a Trial,
approve anything, reconcile application bindings or authorize provider spending.
The existing combined workflow remains available. No existing Dockerfile changes
are required to use these three configs.

| Phase | Config | Artifact/control boundary |
| --- | --- | --- |
| Core | `infra/gcp/cloudbuild.qa-core.json` | API and web builds; actual installed API source/policy check |
| Environments | `infra/gcp/cloudbuild.qa-environments.json` | Exact pinned SDK task-runtime build; installed native source and private source-custody software controls |
| Evaluation | `infra/gcp/cloudbuild.qa-evaluation.json` | KYC/Marketing identity images FROM an immutable task-runtime digest; installed-source and synthetic MCP/OPA/ZEN controls |

The current task-runtime Dockerfile copies backend, Harbor and evaluator source.
Consequently backend or Harbor changes invalidate both Core and Environments,
and Evaluation must wait for the newly built environment digest. This workflow
does not pretend that evaluator source can currently change independently of its
packaged runtime. A web-only change can reuse the other two phases. An identity
Dockerfile-only change can reuse Core and Environments. Input inventory is
conservative: some test changes can cause extra rebuilds. Ignored local runtime
directories are excluded, but missing declared inputs and input symlinks block.

## Prepare a plan

Use a clean, committed source revision. First make a Git archive of that exact
revision and extract it into a new empty directory. Do not copy a working tree,
private operator files, credentials, local dependencies or uncommitted overlays.
The new planner/config files must themselves be in that reviewed commit.

```sh
git archive --format=tar --output=/private/tmp/qa-release.tar ACTUAL_GIT_REVISION
mkdir /private/tmp/qa-release-COMMIT
tar -xf /private/tmp/qa-release.tar -C /private/tmp/qa-release-COMMIT
cd /private/tmp/qa-release-COMMIT
```

Retain and verify the archive SHA and commit alongside operator evidence. The
planner refuses a root containing `.git`, but that alone cannot authenticate an
archive's origin. The operator must verify this fresh extraction came from the
exact committed archive. Use `--root` pointing at that extraction, not the live
repository or a directory with private overlays.

Obtain the actual Golden source hash from the current installed/source verifier;
it is not the Git commit or a hash invented by the planner. Run locally:

```sh
python3 scripts/qa_release_phases.py \
  --root /private/tmp/qa-release-COMMIT \
  --project adi-anvil-mvp-2026 --region us-west1 --repository anvil-qa-v1 \
  --source-commit ACTUAL_GIT_REVISION --source-sha256 ACTUAL_GOLDEN_SOURCE_SHA256
```

The JSON plan includes an explicit archive context path and provenance warning,
exact content inventories, phase input hashes, stable
operation tokens, substitutions and command arrays. It executes none of those
commands. Submit commands pin both the absolute archive directory and its
absolute config path; execute them with the archive as the working directory.
Never replace the context with `.` from the dirty working tree. Only
`prepare_build` phases include a submit command. Submit each phase
independently after the normal operator review; retain its build ID immediately.
The build configs tag each build with its operation token for reconciliation.
Core and Environments have no artifact dependency on each other. Evaluation stays
blocked until an observed successful environment artifact is available by digest.

## Retain and reuse observed results

An operator may supply a prior results document using
`--receipts /private/observed-builds.json --receipts-sha256 EXACT_FILE_SHA256`.
The digest must come from independently retained operator evidence. A digest
checks integrity, not the truth of a receipt: the planner does not contact GCP
or authenticate build provenance. Before accepting the document, the operator
must verify actual Cloud Build SUCCESS, target, operation tag and Artifact
Registry image digests against retained service responses and check logs.
Never turn planned or failed work into a success receipt.

Receipt shape (values must be copied from actual observations and the plan):

```json
{
  "schema_version": "anvil.qa-build-receipts.v1",
  "target": {"project": "PROJECT", "region": "REGION", "repository": "REPOSITORY"},
  "phases": {
    "environments": {
      "status": "succeeded",
      "input_sha256": "EXACT_PLAN_INPUT_SHA256",
      "operation_token": "EXACT_PLAN_TOKEN",
      "dependencies": {},
      "build_id": "ACTUAL_BUILD_UUID",
      "evidence_sha256": "RETAINED_SERVICE_RESPONSES_AND_CHECK_LOG_DIGEST",
      "artifacts": {"task-runtime": "REGION-docker.pkg.dev/PROJECT/REPOSITORY/task-runtime@sha256:ACTUAL_DIGEST"}
    }
  }
}
```

Core requires both `backend` and `web` digest references. Evaluation requires
`kyc-runtime` and `marketing-runtime`, plus its exact plan dependencies including
the environment input hash and immutable environment image. Regenerate the plan
after retaining the environment result. Reuse requires the same phase inputs,
dependencies, target and operation token, plus observed success, a build ID and
evidence pin. Changed inputs invalidate downstream dependencies transitively.
Different Git labels alone do not invalidate byte-identical phase inputs; the
observed artifact keeps the provenance of its own build.

## Bounded retries and reconciliation

The plan publishes these ceilings. Evaluation's immutable-digest pull enforces
its ceiling in the Cloud Build step; other retry policies remain operator
requirements rather than an implemented background retry executor:

| Operation | Ceiling | Rule |
| --- | --- | --- |
| Read/poll | 4 attempts, delays 2/5/10 seconds, 60 seconds total | Stop and report the observed failure when exhausted |
| Pull immutable digest | 3 attempts, delays 2/5 seconds, 120 seconds total | Retry only an exact digest; never replace it with a tag |
| Submit build | 1 attempt | On lost acknowledgement, reconcile operation token/build ID before considering another submission |
| Migration, approval, Trial, binding reconciliation, payment | 1 attempt | Reconcile retained intent/state; never blindly repeat |

Evaluation validates the exact target/repository/digest before invoking Docker.
Its strict Bash step permits at most three pull attempts, waits 2 and 5 seconds,
uses GNU `timeout` for at most 35 seconds per attempt plus a two-second kill
grace, and checks remaining time against a 120-second wall deadline. It fails
closed if `timeout` is absent. These ceilings are fixed, not caller-controlled
retry substitutions. Tests execute the real shell text with a stub Docker,
timeout and sleep: initial failure then success, three failures, wrong target,
quoted digest and mutable tags. No SQL, Trace, migration or Trial execution is
retried by this step.

Each Cloud Build has a separate 1800-second deadline and no automatic whole-job
retry. A failed phase does not invalidate successful unchanged sibling phases.
Pending, running or unknown prior results produce a reconciliation action, not a
submit command. Use the plan's bounded `reconcile_command`, inspect the observed
build ID, and retain the authoritative result. An executed successful build is
reused when its evidence matches; the planner never reruns it itself.

Application runtime bindings are a separate explicit reconciliation after image,
source, role, qualification and policy checks. Software image checks are not
component qualification, legal acceptance or benchmark performance. No phase
writes approvals, qualification receipts, application bindings or paid runs.

## Validation and current limits

`test_qa_release_phases.py` verifies unchanged reuse, web-only and identity-only
two-phase reuse, backend/runtime coupling and downstream invalidation, unknown
acknowledgement handling, target/digest refusal and separate config boundaries.
Cloud build execution and actual registry receipts are not claimed by these
local tests. API/web are grouped in Core in this first increment; splitting
their receipts further is optional future work. No new image layering is claimed.
