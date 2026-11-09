# Local evaluator runtimes

Anvil ships restricted adapter code and independent dependency locks. Installation belongs to deployment/setup, never a policy document or a Run. The application has no install-package command. These are bounded capability integrations, not blanket claims that every feature of an upstream toolkit is safe or deterministic.

## Installed and tested capabilities

| Integration | Pin | Actual capability | Custom policy verdict |
| --- | --- | --- | --- |
| GoRules ZEN | 2.1.3 in backend uv.lock | Generated structured JDM numeric, equality, required field and allowlist decisions | Yes for supported rules |
| OPA local | 1.22.2 | Generated Rego boolean decisions using checksum-qualified binary | Yes for supported rules |
| NeMo Guardrails | 0.24.1 in nemo/uv.lock | Literal-only forbidden-text detection using the actual upstream regex action | Yes for that capability |
| Promptfoo | 0.125.1 in promptfoo/package-lock.json | Actual standalone equals/contains/not-contains assertions on captured text | Yes for supported literal assertions |
| TruLens feedback | 2.16.0 in trulens/uv.lock | Actual ground-truth precision/calibration with undefined values preserved | Calibration metric only |
| Arthur Engine API | API v2 contract | Existing Task prompt validation; capability is per returned rule type | Keyword rule only; other rails remain separate |
| Openlayer API | v1 existing-test evaluation contract | Queue one exact existing pipeline/window without overwriting history | No verdict from queue acceptance |

The local libraries were tested independently in owned environments on macOS. This is not Linux/native isolation qualification, live-account verification, or completion of the Run integration. API contract tests use HTTPX MockTransport and never call a vendor.

## Reproducible setup

Backend setup uses its own `uv.lock` including ZEN. NeMo and TruLens use `uv sync --locked --project integrations/evaluators/nemo` and the corresponding `trulens` directory, with separate `UV_PROJECT_ENVIRONMENT` values. Promptfoo uses `npm ci --ignore-scripts --prefix integrations/evaluators/promptfoo`. No sibling environment, copied node_modules or global installation is needed.

OPA binary installation must pin the exact upstream release, platform asset and SHA-256. Never silently substitute a Linux binary for macOS qualification. The tested macOS arm64 v1.22.2 asset SHA-256 is `c7767cb68c21c3ea9866a76a2d6703d132a25ddad3cd1c1213925e2802ed1dce` from the official OPA release. The binary is not committed. A Linux asset/checksum and native checks remain release preparation.

For the new API process, operator configuration points `ANVIL_OPA_BINARY` and `ANVIL_OPA_SHA256` to that qualified binary, `ANVIL_NEMO_PYTHON` to its isolated interpreter, and `ANVIL_EVALUATOR_NODE` to Node. Secrets are not passed to local worker environments. Missing/incompatible runtimes cannot become Ready. Remote origins must be provisioned in `ANVIL_EVALUATOR_ALLOWED_ORIGINS`; keys are encrypted with the existing secret store. Saving does not call an API. Live API validation remains disabled until bounded dispatch is implemented and explicitly authorized.

## Restricted execution

Local workers accept bounded data, fixed templates and literal checks only. They reject arbitrary package names, module paths, code assertions, function nodes, loaders and file references. Promptfoo cannot receive an arbitrary configuration or model grader; its worker allows only literal assertion types and disables telemetry/update checks. NeMo receives no models and no embedding initialization. OPA uses only Anvil-generated policies, not uploaded Rego with HTTP builtins. Imported documents cannot enable engines or network access.

## Not qualified for base activation

Phoenix Evals3.9.5 and Fiddler Auditor0.0.5 are Elastic-licensed source-available packages. Fiddler Auditor also pins older Jinja/OpenAI/LangChain dependencies incompatible with this backend. Do not install those into the API or call them permissive open source. Pramaana integration needs a verified API/artifact contract. Archived LLM Guard is unavailable for new activation. These constraints remain explicit; names must not appear as Ready Run options.

Primary references: [OPA API](https://www.openpolicyagent.org/docs/rest-api), [ZEN Python SDK](https://github.com/gorules/zen/blob/master/bindings/python/README.md), [NeMo regex action](https://github.com/NVIDIA-NeMo/Guardrails/blob/develop/nemoguardrails/library/regex/actions.py), [Promptfoo standalone assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/), [TruLens ground truth API](https://www.trulens.org/reference/trulens/feedback/groundtruth/), [Arthur validation](https://docs.arthur.ai/docs/guardrails-quickstart), [Openlayer official SDK](https://github.com/openlayer-ai/openlayer-python/blob/main/src/openlayer/resources/tests.py).
