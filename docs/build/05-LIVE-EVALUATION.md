# Live evaluation implementation and activation

The user wants multiple providers but currently has no API keys. Build integrations without keys using mocked transports. No real inference, model-list calls with credentials or paid “connection test” runs are automatically permitted by missing-secret checks. Production credentials must never be requested in chat or committed.

## Adapter matrix

| Registry key | Integration to build | Initial scope |
| --- | --- | --- |
| `fixture_static_v1` | Predetermined fixture response with network denied | Pipeline correctness only |
| `openai_responses_static_v1` | OpenAI official Python SDK / Responses | Single bounded text response, `store=false` where supported, no tools/background/hosted files |
| `anthropic_messages_static_v1` | Anthropic official Python SDK / Messages | Single bounded text response, normalized refusal/usage/stop reason |
| `gemini_generate_static_v1` | Google Gen AI Python SDK / generateContent | Single bounded text response, blocked-content and finish reason handling |
| `mistral_chat_static_v1` | Mistral official SDK / chat completion | Single bounded text response, explicit model/usage |
| `meta_responses_static_v1` | Meta Model API via documented compatible Responses transport | Fixed Meta endpoint, own credential and per-model capabilities |
| `compatible_chat_static_v1` | Explicitly approved OpenAI-compatible chat endpoint | Hosted open-weight service or already running private/local inference service; capability-tested, not universal compatibility |
| `external_result_import_v1` | Existing result files + source manifest | Preserve partner/customer execution origin, never invent traces |

Resolve official SDK APIs and compatible package versions when building. Test each request/response contract independently. Documentation API examples are not a promise that every listed model/account accepts all parameters. Do not substitute models or use a catch-all fallback to a different provider.

## Provider UI and secret references

Admin configures provider key, adapter/version, fixed endpoint identity, exact model ID, expected capabilities, context/output bounds, pricing version/source/date, secret reference, permitted destination, data-use terms review and connection state. UI only reports secret present/missing; no read-back or key display endpoint.

Local secret resolver supports allowlisted server environment variables or owner-only files under `.secrets/`. Each provider has a distinct name; no reading arbitrary user paths. Variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `META_MODEL_API_KEY`, `ANVIL_COMPATIBLE_API_KEY`. These are Anvil resolver names; the adapter passes the resolved value to the SDK and does not rely on every SDK using the same default variable.

The included `.env.example` uses the corresponding `_FILE` suffix for file-backed secrets. Define precedence explicitly (reject both env-value and file values rather than accidentally use the wrong key), redact values, and validate only presence/permissions during ordinary preflight.

Remote base URLs require HTTPS and a fixed provider/destination allowlist. User-submitted arbitrary URLs, redirects to another host, metadata addresses and DNS rebinding are denied. For a local inference service, support an explicit local-development endpoint record limited to the approved host/port/path; Docker host addressing must be documented rather than broad private-network access. API-key protection does not make every endpoint on an inference server safe to expose. No local model download, server installation, GPU provisioning or license acceptance is authorized by creating the adapter.

## Activation and budget guards

Before real inference all must be true:

1. User has chosen exact IDs, eligible account/access and total USD cap. Null budget blocks; zero is a no-paid-spend cap, not permission for arbitrary calls to presumed-free models.
2. Keys are stored locally by the user. No billing/account purchases by the coding agent.
3. The uploaded actor inputs and provider processing rights are reviewed. Use only the original synthetic sample cases initially, with explicit processing scope. Internal fixture labels are not rights evidence for unrelated partner content.
4. Protocol pins adapter/model/settings/input/rubric versions; no tools/retrieval/private references. Three cases × one attempt × N chosen models = at most 3N initial evaluation calls; even a preliminary inference “ping” counts against the approved total.
5. Pricing and a conservative all-billable-token upper bound are known. Include reasoning/cached/other billable categories applicable to the provider. Anvil reserves a global session cap and per-provider/run caps atomically before dispatch. If a bound cannot be defended, block that adapter.
6. Required distinct-Admin provider and paid-scope approvals are recorded by authorized people, tied to exact config/destination/ceiling. The coding agent must not manufacture live approvals with seeded accounts. Confirm an explicit launch separately.

An account's displayed budget/alert is additional defense, not an assumed immediate hard cap. Display estimated/reserved/actual/reconciled values separately; unknown cost stays unknown. No automatic purchase, top-up or quota upgrade.

## Comparative validity

### Required contract extensions

Extend the candidate adapter registry/capability schema rather than create provider-specific parallel run tables. Existing `candidate_revisions` pins provider ID, exact model, adapter version, parameter schema/version and destination. Extend setup APIs with authorized provider-readiness responses that expose no secret values. Add one live-readiness checklist per run; do not treat a green connection check as paid authorization.

Add `evaluation_spend_windows(id, org_id, project_id, start_at, end_at, cap_micro_usd, reserved_micro_usd, settled_micro_usd, status, authority_reference, row_version)` using integer micro-USD and normal composite-scope/audit rules. All overnight live runs link to one authorized window; reservations link window/run/provider-call IDs. Lock the window and run-budget rows in a fixed order in the same transaction before dispatch so concurrent providers cannot each consume the full session cap. Unknown paid calls retain their conservative reservation. No duplicate refund/release on replay. Enforce per-provider subcaps if configured; no cross-window reclassification to evade the ceiling. A source product JSON money field is not permission to spend.

Expose an explicit authenticated readiness/dry-run endpoint and spending-window status to the assigned Researcher/Admin; exact creation/approval follows the existing paid-scope model. Tests must prove two concurrent provider requests cannot exceed the single window ceiling. Pricing unavailable, exhausted window or expired approval blocks dispatch.

Partner workbook `external_model_processing` is mapped by the intake adapter to the canonical `external_processing` operation used in product/15; preserve the original declaration and scope. Never treat a terminology mapping as permission approval.

### Comparison rules

Use the same actor content and deliverable constraints across systems; record any provider-specific formatting or unsupported setting. Record exact requested/returned IDs, endpoint, adapter/harness version, reasoning settings, token limits, refusal/finish reason, usage and timestamp. Equal token counts across vendors are not equal compute; choose and disclose a comparison policy. Mutable `latest` aliases must be disclosed with returned identity and date; prefer a stable snapshot when available.

Real outputs on synthetic inputs are **real execution on synthetic cases**. Preserve `run.origin=adi_executed` and source synthetic provenance independently; do not call them fixture execution. Canned outputs use illustrative origin. Neither establishes Bodhium/Harvard/Wharton benchmark performance. Do not pool these strata or grade live outputs by matching a canned answer string. Expert-style rubric review handles valid alternatives.

## Error and retry tests

For every adapter mock success, refusal/safety block, malformed or empty output, truncated output, missing usage, 401/403, inaccessible model, 429, 5xx and ambiguous timeout after dispatch. No SDK hidden automatic inference retries; explicitly configure/verify that behavior. Lost response → `execution_unknown`, conservative reservation retained and manual reconciliation. Retry only operations proven safe, not ambiguous generation. Credentials never appear in transport logs/errors/screenshots.

Test candidate payload excludes private rubric/reference and expected fixture files. No private chain-of-thought requested or exposed; ordinary final answer and observable metadata suffice. Validate exact capability/parameter support before dispatch; reject silently ignored tools or settings.

## Completion reporting

Create one readiness row per adapter: implementation status, mock test result, configured key boolean, exact selected model, pricing validation, approval status, live timestamp/result or reason blocked. No keys now means all live tests are blocked. That does not prevent completion of local coding or deterministic integration tests.
