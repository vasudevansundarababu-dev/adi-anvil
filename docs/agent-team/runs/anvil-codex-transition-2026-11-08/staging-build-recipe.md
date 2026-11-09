# Staging backend/web build recipe — review only

No paid build, image resolution/pull, registry creation, IAM change or deployment was performed. `infra/gcp/staging_demo_build.py` validates the [complete review contract](staging-build-input-contract.json), local lifecycle/inventory/context bytes and [materialized Cloud Build config](staging-cloudbuild-edcc051.json), then prints prospective argv only. It has no executor. The exact new builder, repository and source bucket are bound; new cloud identity/IAM/resource approval remains pending. Completing this local packet does not grant authorization.

Current native-qualified product source is `edcc0514c43ceb614b813566820ee0c2c7311463`, archive SHA256 `8564c5cd5fdd0795a6dc9e041befbce591781ccacd41182288c0fbdc1c7a6b28`, native-qualification source manifest SHA256 `cd9c2d44cd2106658923adc84307d6107ced87e9c33f6f6653d4325f65b536a6` covering402 tracked paths **including tests**. This is not a claim that every later test/evidence commit has the same manifest: f85 changed an integration test while product runtime remained unchanged. Bind the selected final source/archive/inventory explicitly before build; do not mislabel the402-path qualification inventory as the current entire runtime manifest. A product repair requires new bindings and warranted tests.

## Exact input and context preparation

Use only the fresh owned context extracted from the approved tracked archive, never the developer checkout. The unfiltered792-file context inventory hash is57a7b64884aed1bebb114a89662fec8d417092f9b7ba1fe5cf160818c60ebed4. The official SDK selection in [staging-build-upload-source.json](staging-build-upload-source.json) is381 files/5167729 bytes, hash728a66918f33705f7a224ea0bbe98d2e73ac542f814499a6cdc7fe313a613a14. The renderer rehashes the complete current context, confirms the exact native manifest and selected-file subset, and separately binds these two inventory hashes. `.env.example` is an approved tracked template in the unfiltered source only; no `.env*` file is uploaded. These hashes are not the as-yet nonexistent uploaded package hash or GCS generation.

The build identity must be an explicitly reviewed separately scoped staging build service account, not the runtime VM identity, default Compute account or production builder. The registry must be an explicitly approved separate `us-west1` staging repository in the Anvil project. Its existence, repository-scoped write access, Cloud Build service-agent/impersonation permissions and log permissions require review; no new grants are implied. No model/project secret material belongs in build envs or substitutions. Missing principal/registry values remain null rather than guessed.

## Review commands, not execution

Review the concrete packet, then revalidate/render without any cloud call:

```text
python3 infra/gcp/staging_demo_build.py --contract docs/agent-team/runs/anvil-codex-transition-2026-11-08/staging-build-input-contract.json
```

The resulting config has **exactly two Docker build steps and two outputs: backend and web**, Linux/amd64, with separate source/archive/native/prefilter/upload inventory labels and substitutions. It does not build Harbor, golden-tools, native actors or legacy worker images. The materialized config SHA256 is51b71b5722e2e21fbe3df1f9e759ac9377acc5f2c746580cf1d852458e63ffc5. Missing or changed local inputs, lifecycle semantics or config bytes prevent prospective mutation/submission argv from being emitted.

The [command review document](staging-build-resource-commands.sh.txt) invokes only this print-only validator. Prospective resource and submission argv are JSON data, not automatically executed. The submission explicitly names `gs://adi-anvil-mvp-2026-anvil-staging-build-source/source` and the exact new `anvil-staging-build` account; no default/shared bucket is selected. Before any later mutation, obtain the user's explicit new builder identity/IAM/resource approval and fresh absence, enabled-API and organization-policy receipts. No API-enablement command is included. Actual resource/IAM receipts are reviewed before the single build submission. `build_authorized=false` remains explicit.

## Digest/provenance receipt and cost

After an approved build, use its **actual returned ID**, require SUCCESS and exactly the two expected images, and retain sanitized sourceProvenance, results.images digests, buildStepImages, selected service account/substitutions and timing. The renderer prints the exact read-only describe template. Missing or placeholder IDs must not be queried as if real results. Bind immutable backend/web digests plus source/archive/inventory/context/config hashes and actual builder/base manifests to the release; never promote a tag alone or overwrite an earlier source tag after mutable input drift.

The proposed `E2_HIGHCPU_8` build has2400s timeout. The official [Cloud Build pricing](https://cloud.google.com/build/pricing) page was verified on2026-11-08: e2-highcpu-8 default-pool rate0.0156USD/build-minute. Forty minutes therefore allocates0.624USD of compute for one job. The reviewed proposal allocatesUSD5 for this single job plus small source/registry/log/transfer usage inside the existingUSD500 preparation allowance. This is an operator allocation, not an enforced billing cap. No free-tier offset or actual bill is claimed. No paid models/judges are involved.

Current limits remain explicit: backend Dockerfile's `python:3.12-slim-bookworm`, uv version tag and web Node version tags are mutable; Cloud Build's Docker builder tag is mutable; backend's hatchling build dependency is unversioned (Linux QA observed1.33.0). This preparation does not resolve/pull new bases or patch those Dockerfiles. Before release, either review explicit digest-pinning/build-dependency amendments or knowingly accept and record actual resolved provenance with its reproducibility limits. Do not claim identical source SHA guarantees identical output digests.

Seven focused local recipe tests pass, including exact-target rejection, lifecycle semantic checks even with a matching changed-file hash, source/config drift, distinct upload binding, absent post-upload observations and print-only behavior. Actual Cloud Build, artifact publication, container boot and application deployment remain **not run**.
