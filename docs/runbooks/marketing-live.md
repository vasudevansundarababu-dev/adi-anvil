# Twelve-week marketing workflow

This adds the registered Northstar Flow interactive task to Anvil. It is separate
from CSV/JSONL static task import. Twelve simulated weeks run sequentially; they do
not require twelve calendar weeks. The candidate supplies 12 decisions and a final
memo. No real campaigns, email or advertising purchases occur.

**Current launch status: blocked, as requested.** The user confirmed that no API key
is configured and two real Admin approvers are not yet available. No paid model
requests or real approvals were made. Mocked software tests are not model results.

## Prepare the task in Anvil

1. Open <http://127.0.0.1:3202>. Use your existing project and approved research objective.
2. As **Data Engineer**, open **Case bank** and select **Import 12-week marketing task**.
   This creates a case, rubric and task as drafts, with registered actor-input hashes.
3. Have the designated **rights reviewer** inspect the case and record two separate
   scopes under **Review or revoke permitted use**: local evaluation and external
   actor-input processing by OpenAI. Enter genuine reviewed evidence; the synthetic
   source label alone is not an approval. Rights can be revoked in the same control.
4. Review and calibrate the rubric, then submit it. Its assigned Reviewer records
   the content review and Advisor the calibration review. The supplied anchors are
   proposed, not evidence of independent calibration. Do the task's content and
   research reviews, then publish the qualified task as Data Engineer.
5. As **Researcher**, create a suite containing only this published task and the
   exact approved objective. State that it is one original synthetic development
   task, with descriptive findings only. Obtain technical review and freeze it.
6. As **Admin**, open **Providers**, expand OpenAI configuration, and review the
   marketing defaults: `gpt-6-sol`, 8,192 output tokens, pricing revision
   `openai-gpt-6-sol-2026-09-28-standard-text-v1`, request bound `1000000` micro-USD.
   Check the processing-terms box only after reviewing those terms. Save configuration.
   Saving does not contact OpenAI or require a key.
7. As **Researcher**, create a protocol with **12-week marketing · OpenAI gpt-6-sol**,
   that exact connection, the frozen suite, and the existing independent review
   assignments. Replace the fixture comparison text with a one-task descriptive
   plan; retain the independent rubric review and disclose simulation limitations.
   Obtain the Advisor's technical review.
8. Select **Prepare marketing run**, then open **Run console**. The marketing card
   lists missing gates and keeps **Launch paid 12-week run** disabled until resolved.

You can complete this preparation and inspect blockers now. Do not use the older
three-case fixture suite or upload the operator source as candidate input.

## Store the API key locally when ready

From the repository terminal, create the private file without overwriting any existing key:

```sh
mkdir -p .secrets
chmod 700 .secrets
touch .secrets/openai_api_key
chmod 600 .secrets/openai_api_key
```

Open `.secrets/openai_api_key` in your local editor and put only your API key in it.
Do not put it in chat, task inputs, screenshots, Git or frontend variables. This
directory is ignored. In your existing local `.env`, set:

```dotenv
OPENAI_API_KEY_FILE=.secrets/openai_api_key
```

Leave `OPENAI_API_KEY` unset or empty, including inherited shell configuration.
Anvil rejects conflicting sources. Restart only Anvil with `pnpm stop`, then
`pnpm dev`; refresh readiness. The UI reports presence, never the key value.
Presence does not verify account billing or access to the selected model.

## Real approval and explicit launch

Two distinct, authorized, non-synthetic Admin identities must each record provider
activation and exact-run paid-scope approval. In Run console, use **Record real Admin
approval**, enter reviewed authority evidence and an expiry, and sign in again if
the session is older than ten minutes. Both approvals bind hashes; changing the
provider or protocol requires a new scope. Seeded demo identities are rejected.

**Real-person identity onboarding is not implemented in the UI.** Do not relabel demo
accounts or insert approval records to bypass this. Once the two people are available,
their local identity provisioning needs to be completed and verified separately.
Until then paid launch stays blocked even if a key is supplied.

The user-selected cumulative API cap is $100, shared by all runs under this authority.
It is not the $120,000 simulated marketing budget. One run allows at most 13 calls,
with a $1 reservation per call and a $13 run cap. The server bounds each prompt to
100,000 UTF-8 bytes plus a fixed message wrapper, 8,192 output/reasoning tokens,
standard processing, no tools and no hidden SDK retries. The $1 bound conservatively
covers uncached input/cache writes and output at the reviewed rates. Pricing must
be reviewed again after **2026-10-05 00:00 UTC**. See the
[official model pricing](https://developers.openai.com/api/docs/models/gpt-6-sol).

Reservations remain held even when a response includes token usage; reported usage
is not an independently verified bill. No automated billing reconciliation or
reservation-release UI is claimed. A second project cannot create another window
under the same authority to reset the ceiling.

After all gates are satisfied, a Researcher explicitly selects **Launch paid 12-week
run**. This implementation session does not perform that action.

## Progress, interruption and review

The run saves each request intent, observed input hash, response, usage, action,
receipt and state hashes. Only actor instructions, generated inputs and past/current
observations reach the provider. Future simulation state and operator references
stay server-side. Model output is parsed as JSON data; no code or tools are executed.

A malformed action is retained for review and ends the decision sequence; the
harness does not repair it or spend another call. Infrastructure errors are marked
separately. A lost response or crash after committed dispatch intent becomes
`execution_unknown`; its reservation stays held and it is never automatically sent
again. Local resume after a captured response applies that response once. Cancel
stops future dispatch; it cannot retract an in-flight request, whose cost may remain
unknown. Manual incident reconciliation remains a later operational step.

After the final memo, the existing independent review inbox receives the full
observable decision trail and controlled operator rubric. Provider identity metadata
is omitted from the review artifact. Business results and qualitative strategy are
reviewed separately; no automatic model-performance score is fabricated.
This known single-model development task is not a blinded comparison: its original
operator brief names the selected model. Other unfinished reviewers' grades remain hidden.

The simulation is a development task with fixed integer funnels, two-week conversion
delay, channel-priority capacity and scripted disruptions. Copy and positioning do
not directly change conversion rates. Results do not establish causal marketing
effectiveness, protected-benchmark performance or faculty validation.
