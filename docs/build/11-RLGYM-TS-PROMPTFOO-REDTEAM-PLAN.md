# RL Gym: Trust & Safety prompts from Promptfoo's red-team generator (plan)

Status: plan, not built. Written 22 Nov 2026 at the owner's request ("Yes, plan it").

## Where we are

- A suite's Trust & Safety (T&S) prompts come from one of two generators today:
  - **Local template generator (default):** deterministic, synthetic, no model.
  - **Live model generator** (`live/generator.py`): one approved model writes each prompt through the RL Gym gateway,
    under an approval with use `generator`. It works in the API but is **not offered in the suite page**.
- Either way, a person reviews and approves the prompt set before the suite can be saved, and the set's hash is bound
  into the run.
- Promptfoo 0.125.1 is installed as a scoring plug-in (`promptfoo 1.1.0`, offline image). The same package already
  contains the red-team generator (`promptfoo redteam generate`, its plugins and strategies) and the switches
  `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION`, `PROMPTFOO_DISABLE_REMOTE_GENERATION` and
  `PROMPTFOO_DISABLE_TELEMETRY`. **No new download is needed for Promptfoo itself.**
- Each T&S category already names its Promptfoo red-team plugin:

  | RL Gym category | Promptfoo plugin |
  |---|---|
  | indirect_prompt_injection | indirect-prompt-injection |
  | system_prompt_extraction | prompt-extraction |
  | assigned_case_isolation | bola |
  | personal_data_leakage | pii |
  | decision_authority | rbac |
  | evidence_integrity | hallucination |
  | over_refusal | overreliance |
  | aml_tipping_off, sanctions_evasion, social_engineering_takeover | policy (with the category's policy text) |
  | structuring_advice | harmful:financial |

## What changes

A third generator choice, **Promptfoo red team**, that runs `promptfoo redteam generate` for the chosen categories and
strategies and stores the result as the suite's T&S prompt set. Everything after that is unchanged: placement, human
review, approval, the prompt-set hash, and how T&S episodes are scored.

## Design

1. **Model calls go through the RL Gym gateway, never from the container.** The generator runs in a sandbox container
   like the scoring plug-ins (`--network none`, read-only, non-root, limits). Promptfoo's provider inside it is a small
   custom provider (`file://broker.mjs`) that writes each model request as one JSON line to stdout and reads the answer
   from stdin. The RL Gym runner relays each request to the gateway under the owner's approval with use `generator`,
   records it in the live-call ledger, and writes the answer back. This is the same pattern as the OpenEnv
   `docker exec` bridge. No key and no network ever reach the container.
2. **Remote generation is off.** The container sets `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true`,
   `PROMPTFOO_DISABLE_REMOTE_GENERATION=true` and `PROMPTFOO_DISABLE_TELEMETRY=1`, so nothing goes to Promptfoo's cloud.
   Plugins that only work with Promptfoo's remote generator are refused in validation with a clear reason (likely the
   `harmful:*` family; `structuring_advice` then stays on the local or live-model generator).
3. **Spending gates are the existing ones.** One approval (provider, model, use `generator`, per-run and total caps,
   verified prices). The runner estimates the worst case before each call and stops at a cap. An unanswered call is
   recorded and never retried. No approval or no live flag: the generate request is refused; it never falls back
   silently.
4. **Strategies.** Only strategies that transform the generated text are used at generation time:

   | RL Gym strategy | Promptfoo strategy |
   |---|---|
   | plain | basic |
   | prompt-injection wrapper | prompt-injection |
   | encoding | base64 / rot13 (no model calls) |
   | multilingual | multilingual |
   | jailbreak | jailbreak templates only (no iterative attack) |
   | multi-turn escalation | not mapped: Promptfoo's version attacks a live target; keep the local template |

   Iterative strategies that attack a target model (`jailbreak` iterative, `crescendo`, `goat`) are out of scope: the
   agent under test is run by the RL Gym's episodes, not by Promptfoo.
5. **Purpose text.** Promptfoo needs a description of the system under test. It is built from the template's domain,
   the environment's tool names and the category's boundary text only, never from case references or private data.
6. **Provenance.** The prompt set records the generator as
   `promptfoo-redteam 0.125.1 via <provider>:<model>`, the image digest, the plugin and strategy per prompt, and the
   approval id. Prompts stay labelled synthetic.
7. **Qualification.** The new image is installed like a plug-in version: a manifest with pinned image and lockfile
   hash, and known cases that replay recorded model answers through the broker, so qualification needs no live call.

## Work steps

1. Fix first, from today's judge finding: `live/generator.py` caps model output at 300 tokens, and thinking models
   (Gemini 3.8 Flash, Claude 5.5) can use that up before the answer. Raise it as was done for the judge (1024).
2. Broker protocol in the plug-in runner: model-request lines out, answers in, the ledger, caps, no retry on an
   unanswered call. Unit tests with a fake container.
3. Image `promptfoo-redteam 1.0.0`: same base image and lockfile as the scoring plug-in, entry point that runs
   `redteam generate` with the broker provider and prints prompts as `adi.ts-prompts.v1`. Built offline from the
   vendored tree.
4. Category and strategy mapping, purpose text, and validation that refuses remote-only plugins.
5. `ts/generate` with `{"generator": {"kind": "promptfoo-redteam", "provider", "model_id"}}`; suite page offers the three
   generators, shows the approval and a cost estimate before generating.
6. Tests: unit (mapping, broker, caps, refusal), integration with recorded answers (stub mode), and one small live
   generation under an owner-approved `generator` approval, with the spend reported.
7. Record the decision in BUILD-DECISIONS (next RG number) and the evidence in BUILD-STATUS.

## Needs from the owner

- **Which model generates the prompts,** and an approval for it with use `generator` (caps, verified prices). None of
  the current approvals includes `generator`.
- **Whether red-team text for financial-crime categories may be generated by a live model at all.** Providers may
  refuse such requests. The plan treats a refusal as a blocked prompt, never as a pass.
- Nothing else: no new download is needed for Promptfoo, and the Node 22 base image is already pinned and present.

## Risks

- Call volume: Promptfoo generates several candidates per plugin and may call the model more than once per prompt.
  The cost estimate and caps bound this; a first live run should be one category and one strategy.
- Provider refusals for some categories (see above).
- Promptfoo internals: the broker relies on the custom-provider interface, which is stable, but the plugin list changes
  between Promptfoo versions. Pinning 0.125.1 and the known cases catch that.
