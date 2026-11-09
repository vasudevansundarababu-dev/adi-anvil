# Staging backend/web build recipe — review only

No paid build, image resolution/pull, registry creation, IAM change or deployment was performed. `infra/gcp/staging_demo_build.py` validates explicit public inputs and prints a concrete Cloud Build config and literal argv. It has no executor. Missing/unapproved principal, registry, exact source/context hashes, absolute fresh context path or source-bound tag fails closed. The example JSON intentionally leaves those unknown inputs null; it is not a runnable build authorization.

Current native-qualified product source is `edcc0514c43ceb614b813566820ee0c2c7311463`, archive SHA256 `8564c5cd5fdd0795a6dc9e041befbce591781ccacd41182288c0fbdc1c7a6b28`, native-qualification source manifest SHA256 `cd9c2d44cd2106658923adc84307d6107ced87e9c33f6f6653d4325f65b536a6` covering402 tracked paths **including tests**. This is not a claim that every later test/evidence commit has the same manifest: f85 changed an integration test while product runtime remained unchanged. Bind the selected final source/archive/inventory explicitly before build; do not mislabel the402-path qualification inventory as the current entire runtime manifest. A product repair requires new bindings and warranted tests.

## Exact input and context preparation

Use a fresh owned build directory extracted only from the approved tracked public Git archive after archive/member validation; never submit a developer checkout with `.local`, credentials, private data or uncommitted changes. Verify all tracked runtime/inventory hashes and record the **actual sanitized submitted context hash**. Use reviewed allowlists in `.gcloudignore` and `.dockerignore`; inspect the final package inventory, including all fixtures being intentionally shipped. Exclude `.env`, private keys, ignored operator files, secret env/realm output, databases, native logs and all generated private artifacts. The renderer does not claim to perform that trusted inspection or compute the context hash itself.

The build identity must be an explicitly reviewed separately scoped staging build service account, not the runtime VM identity, default Compute account or production builder. The registry must be an explicitly approved separate `us-west1` staging repository in the Anvil project. Its existence, repository-scoped write access, Cloud Build service-agent/impersonation permissions and log permissions require review; no new grants are implied. No model/project secret material belongs in build envs or substitutions. Missing principal/registry values remain null rather than guessed.

## Review commands, not execution

First fill/review the example input contract, then render without making any cloud call:

```text
python3 infra/gcp/staging_demo_build.py --contract REVIEWED_PUBLIC_BUILD_INPUTS.json
```

The resulting config has **exactly two Docker build steps and two outputs: backend and web**, Linux/amd64, both bound to source labels and a unique reviewed source-prefixed tag. It does not build Harbor, golden-tools, native actors or legacy worker images. Existing production Cloud Build defaults are untouched. Save only the reviewed config object to `REVIEWED_STAGING_BACKEND_WEB_CONFIG.json`; verify its hash and exact paths before any separately approved manual submission.

Literal future submission shape, requiring every placeholder to be explicitly bound first:

```sh
: "${APPROVED_FRESH_CONTEXT_DIRECTORY:?missing approved public context}"
: "${APPROVED_STAGING_BUILD_IDENTITY:?missing reviewed separately scoped identity}"
: "${APPROVED_BUILD_CONFIG:?missing reviewed backend-web-only config}"
: "${EXPLICIT_PAID_BUILD_APPROVAL_RECEIPT:?missing independent build approval}"
test -d "$APPROVED_FRESH_CONTEXT_DIRECTORY"
test -f "$APPROVED_BUILD_CONFIG"
test -f "$EXPLICIT_PAID_BUILD_APPROVAL_RECEIPT"
# Before executing: independently verify receipt, source/context/config hashes,
# principal/registry scopes and unique tag. File presence is not approval proof.
env CLOUDSDK_CONFIG=/Users/vasudevansundarababu/Documents/Codex/anvil-tools/cloud-config \
  CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=true \
  /Users/vasudevansundarababu/Documents/Codex/anvil-tools/google-cloud-sdk/bin/gcloud \
  --project=adi-anvil-mvp-2026 --account=vasudevan.sundarababu@adi-labs.ai \
  builds submit "$APPROVED_FRESH_CONTEXT_DIRECTORY" --region=us-west1 \
  --config="$APPROVED_BUILD_CONFIG" \
  --service-account="projects/adi-anvil-mvp-2026/serviceAccounts/$APPROVED_STAGING_BUILD_IDENTITY"
```

This block is a review artifact, not a script run by the assistant. Variables must not be set from untrusted text/command substitution. The printed recipe always says `build_authorized=false`; completing an input contract never grants paid-build or deployment authority.

## Digest/provenance receipt and cost

After an approved build, use its **actual returned ID**, require SUCCESS and exactly the two expected images, and retain sanitized sourceProvenance, results.images digests, buildStepImages, selected service account/substitutions and timing. The renderer prints the exact read-only describe template. Missing or placeholder IDs must not be queried as if real results. Bind immutable backend/web digests plus source/archive/inventory/context/config hashes and actual builder/base manifests to the release; never promote a tag alone or overwrite an earlier source tag after mutable input drift.

The proposed `E2_HIGHCPU_8` build has2400s timeout. The official [Cloud Build pricing](https://cloud.google.com/build/pricing) page was verified on2026-11-08: e2-highcpu-8 default-pool rate0.0156USD/build-minute. Forty minutes therefore allocates0.624USD of compute for one job, **excluding** source/registry storage, transfer and logs. This is a planning allowance, not an enforced bill cap. It consumes the already proposed1,000-minute staging build allowance; no free-tier offset, extra budget or actual bill is claimed. A separately approved run count/cost limit and failed-build disposition are required before execution. No paid models/judges are involved.

Current limits remain explicit: backend Dockerfile's `python:3.12-slim-bookworm`, uv version tag and web Node version tags are mutable; Cloud Build's Docker builder tag is mutable; backend's hatchling build dependency is unversioned (Linux QA observed1.33.0). This preparation does not resolve/pull new bases or patch those Dockerfiles. Before release, either review explicit digest-pinning/build-dependency amendments or knowingly accept and record actual resolved provenance with its reproducibility limits. Do not claim identical source SHA guarantees identical output digests.

Three focused local recipe tests pass: backend/web-only config, separate target/identity/hash validation, isolated CLI path and print-only behavior. Actual Cloud Build, artifact publication, container boot and application deployment remain **not run** and require separate approval.
