# Provider readiness and authority

Six adapter contracts are implemented and tested with mocked official-SDK transports: OpenAI Responses, Anthropic Messages, Gemini generateContent, Mistral chat, Meta Model API Responses, and one fixed compatible-chat endpoint. Mock tests do not qualify a live model. The current transport entry point rejects real transports and the application does not offer a live dispatch path.

An Admin can save an exact model ID, maximum output tokens, pricing revision and conservative integer-micro-USD bound on the Providers screen. Saving configuration performs no inference. Secrets remain server-side: use exactly one of the named environment variable or owner-only `.secrets/<lowercase-variable-name>`. Supported names are `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `META_MODEL_API_KEY`, and `ANVIL_COMPATIBLE_API_KEY`. Readiness exposes only presence/errors, never values. Do not paste credentials into a prompt or UI field.

`pnpm test:live` currently exits blocked with missing authority/model/budget/rights/independent-approval reasons. This is an expected non-pass. Runtime approval submissions from seeded synthetic identities are rejected. Neither a flag nor two seed accounts grant live authority. A future qualified live path requires explicitly approved provider/model/budget, reviewed processing terms and actor-data rights, frozen protocol, current real distinct-Admin activation and paid-scope approvals, and an explicit run launch.

The integer budget ledger is independently tested for concurrent shared ceilings, idempotent reservations and unknown-cost retention. It is not yet integrated with real dispatch. Actual provider cost stays unknown when not returned/reconciled. SDK inference retries are disabled in mock contracts; ambiguous dispatch must not be retried automatically.

No provider credentials were supplied and no model requests were made during this build. The fixture harness reads registered predetermined responses separately from hidden references and expected scores. Its outcomes test application mechanics and cannot be promoted to measured model performance.
