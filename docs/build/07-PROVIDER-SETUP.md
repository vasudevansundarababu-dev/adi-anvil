# Enable models in ADI Anvil — user setup guide

Checked against official documentation on 27 September 2026. This guide does not create accounts, accept terms, purchase credit, issue keys or run inference. Model availability and access must be verified in your own account.

## What you need

Anvil runs locally; model requests can go to remote provider APIs. Those are separate choices. You do not need to deploy the application to AWS/GCP to test APIs. A chat/coding-app login should not be assumed to supply an API credential or API budget.

For each desired provider: sign in to its developer console yourself → create a dedicated development project/workspace where offered → review data-use terms and available billing/free allowances → create a project-scoped API key → save it locally without pasting it into chat → choose an exact model ID from that account's available catalog. Start with one provider, validate a single case, then expand; no need to buy every service before the application can be built.

| Provider | Where and what to do | Anvil secret name |
| --- | --- | --- |
| OpenAI | Create an API project/key in the OpenAI Platform dashboard; review billing and account model access. Use server-side API access, not the Codex sign-in as a substitute. [Official quickstart](https://developers.openai.com/api/docs/quickstart) | `OPENAI_API_KEY` |
| Claude | Create a Claude Console account/workspace and API key; check account billing/limits and available model IDs. Anvil uses the Messages API, not Claude web-chat automation. [Official API setup](https://platform.claude.com/docs/en/api/overview) | `ANTHROPIC_API_KEY` |
| Gemini | Create/manage a Gemini API key through Google AI Studio, linked to the intended project; check model tier, quotas, data terms and any billing requirement. [Key setup](https://ai.google.dev/gemini-api/docs/api-key), [billing](https://ai.google.dev/gemini-api/docs/billing) | `GEMINI_API_KEY` |
| Mistral | Open Mistral Studio → API keys → create a key; confirm available models and your account's free/paid limits. [Official first-request guide](https://docs.mistral.ai/getting-started/quickstarts/developer/first-api-request) | `MISTRAL_API_KEY` |
| Meta Muse | Create a Model API account/key through Meta's developer dashboard. Current quickstart documents Muse Spark, compatible Responses at `https://api.meta.ai/v1`, and example ID `muse-spark-1.3`; verify availability before selecting it. Muse Code installation is not required for Anvil API calls. [Official Meta quickstart](https://dev.meta.ai/docs/quickstart) | `META_MODEL_API_KEY` |
| Other open-weight models | Choose a specific model, license and serving host. Either get a hosted service key, or use an already running private inference endpoint on suitable hardware. API compatibility and model licensing are separate checks. [vLLM server documentation](https://docs.vllm.ai/en/latest/serving/openai_compatible_server/) | `ANVIL_COMPATIBLE_API_KEY` plus approved endpoint/model |

Open-weight does not necessarily mean permissively licensed, free to host or small enough for your laptop. A remote API removes local GPU requirements, but has its own terms/costs. Do not assume Muse is an open-weight Llama model or silently replace it with Llama. Select the exact intended family/version.

## Store keys safely

During the build, Codex must create a local, ignored `.secrets/` directory and document the expected file names in `.env.example`. You enter values using your editor or a secure credential prompt; do not put real secrets in this document, terminal commands saved in history, screenshots, Git, frontend environment variables or the Codex chat. Restrict local file access to your user. The backend reads approved secret references; the browser never receives a key.

You may enable providers one at a time. A missing key should show “Not configured,” not cause the application to crash. Revoke/rotate any accidentally disclosed key at its provider. Do not extract credentials from unrelated tools or other ADI applications.

## Before your first paid run

1. Choose exact model IDs for the first comparison; provider names alone are insufficient.
2. Set a maximum total USD ceiling and per-model token/time limits. No amount has been approved yet. Check current pricing for the selected IDs; do not treat illustrative pricing as a quote.
3. Configure credentials and pricing in Anvil; verify permissions and provider capability without an automatic inference ping.
4. Complete the existing two-person provider/paid-run approvals and explicit launch action. Seeded demo accounts are not a replacement for real approvals.
5. Run one permitted original synthetic case first. Inspect response, usage and billed/estimated cost. Expand to three cases across selected models within the same cumulative cap.

These few cases test wiring and reporting, not which frontier model is universally best. Preserve unsuccessful/blocked attempts and report limitations. No automatic retries after an uncertain paid request.

## Still needed from you

- Exact first model IDs (we can select them together after you can see your account access).
- Total live-test budget in USD.
- Confirmation that the required credentials are present locally, not their values.
- Who will supply the two required real Admin approvals before paid execution.

GitHub owner is not needed until you approve publication. The application can be built overnight without these keys; live verification cannot be truthfully completed without them.
