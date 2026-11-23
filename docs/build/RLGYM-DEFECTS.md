# RL Gym defects (open)

Local list until the owner logs them in the tracker. Newest first.

## D-018 Template validate replays a stale answer under the same Idempotency-Key (medium)

- **Found:** 23 Nov 2026 by Studio. Release c92ad618 (Golden KYC v7) failed anvil_validate because two configurations
  were not yet qualified. On resume Studio re-sent validate under the same step key, `<release_id>:anvil_validate`,
  and the RL Gym replayed the stored `valid: false`, although the configurations had been qualified since.
- **Cause:** `/templates/validate` went through the generic `idempotent()` wrapper, which returns the stored response
  for a repeated key. Validate writes nothing, and its answer depends on registry state that changes.
- **Fix (5923350, parent's go):** validate is re-evaluated on every call. The Idempotency-Key header is still required.
  Activation keeps its replay.
- **Same commit, the owner's 10-record run:** the data plan spreads the sample only over the application types the
  suite has tasks for, so every sampled case becomes an episode. Completeness quotas now add up exactly (largest
  remainder); before, sample size 10 over 2 types gave 12. Plans of 40 over 4 types are unchanged.
- **Status:** fixed.

## D-016 S5 step follow-ups do not reach the agent (medium)

- **Found:** 23 Nov 2026, requested by the Authoring session. Authoring commits ad483ff7 and 6f6e3aac, on
  forge-v2-authoring, add optional `followUps` to `sections.S5.steps[i]`: `[{"if"?: text, "tools": [1-2 tool IDs]}]`.
  Status: **fixed** (parent's go, 23 Nov 2026; commit below). The 4 run-0228 tasks' instruction hashes are unchanged.
- **Checked:** `runs/instructions.py` renders a step's `action`, `tool` and `failureBehaviour` only. `followUps`,
  and any other key inside a step, is dropped silently. Import is unaffected. The run-0228 tasks have no follow-ups.
- **Plan:**
  1. After the step line and before "If this fails", one line per follow-up, in order:
     - with a condition: `   If <if>: <tool> then <tool>`;
     - without one (a chain): `   Then: <tool>`.
  2. Any other unknown key in a step is rendered as `   <key>: <value>` instead of being dropped, so a future field
     always reaches the agent.
  3. Packages without follow-ups render exactly as today, with the same text and hash.
  4. **Tests:**
     - the conditional follow-up and the chain;
     - two tools joined with "then";
     - a step without follow-ups unchanged (hash of the existing fixture unchanged);
     - an unknown step key kept.

## D-015 Path summary sent with SME review items contradicts itself (low)

- **Found:** 23 Nov 2026, from the Authoring side, on batch smr-0051 (run-0228). Assigned to the RL Gym. Status:
  **fixed in 9adfb16** (owner's go, 23 Nov 2026). Batches already sent keep their text.
- **Example as sent** (run-0228-e0031): "Took 3 of 8 steps; failed at account (criterion account_agreements fail); not
  reached: verify, screen, account, state, act". The path order was `intake, identify, decide`.
- **Causes** (`results/episodes.py`, the episode viewer, which the SME package copies in `results/sme.py`):
  1. `failed_node` is the first step of the **first failing criterion by criterion ID**. That is `account_agreements`,
     alphabetically first, and its step is the one the criterion is *about* (`account`), whether or not the agent
     reached it. So an unreached step is named "failed at". Episodes that failed for a missing step never show
     "failed at" a step that ran.
  2. "Took N of 8 steps" counts entries in the path order, including revisits. e0032's
     `intake, identify, intake, decide` gives "Took 4 of 8", but only 3 distinct steps were reached.
  3. The summary lists the same step in both "failed at" and "not reached".
- **Plan:**
  1. **"Failed at" is only ever a step that ran:**
     - Order failing criteria by workflow step order, then criterion ID.
     - "Failed at X" uses the first failing criterion whose step was reached.
     - Failing criteria whose steps were never reached are reported as missing steps, not as a failure point.
     - The current fallbacks stay as they are: the first refused tool call, then the last step on a timeout.
  2. **New summary shape, each step in exactly one place:** "Reached 3 of 8 steps (intake, identify, decide); failed
     at decide (criterion decision fail); not reached: verify, screen, account, state, act (needed by failed
     criteria: identification_verification, screening, account_agreements, state_rule_selection)".
     - If no failing criterion's step was reached: "Reached 3 of 8 steps (…); stopped before verify; not reached: …".
     - "Reached" counts distinct steps.
  3. The package's `path` object keeps its keys (`order`, `failed_node`, `failed_why`, `summary`) and adds
     `reached` and `missing_for`. Same contract, extra fields only.
  4. **Already-sent batches stay as they are.** A batch is an immutable, hashed package. New batches and the episode
     viewer get the new text.
  5. **Tests:**
     - failing criterion on an unreached step;
     - on a reached step;
     - mixed;
     - revisits counted once;
     - refused tool;
     - timeout;
     - a step never appears in two places.
- **Score field:** the package's `score` has always been an object, `{score, passed, failed_criteria}`
  (`results/sme.py`). No RL Gym spec in this repository defines it as a number. No change planned; Authoring renders
  the object (D-014).
- **Related, not this defect:** the template's workflow (from Studio) maps legacy tools (`address.verify`,
  `tin.validate`, `party.list`). @6 operations such as `documents.list`, `policy.read` and `search` belong to no step,
  so they don't appear in the path at all. That belongs with D-006.

## D-007 The live agent never gets the authored task (high)

- **Found:** 23 Nov 2026, from the D-005 evidence pack for run-0228. Global ID from the master log; assigned to the RL
  Gym. Status: **fixed in 4689c1a** (owner's go, 23 Nov 2026; RG-53). Not yet measured with a live run.
- **Cause:** `runs/worker.py` passes `actor["assignment"]` to `live_agent` (and to the mock agent). Only the stub and
  fixture exports carry `assignment`; every project except one has it. The real ADI Forge export
  (`prj_f8719e2b67a04d598256dca089437be5`, 4 tasks) sends the task as `sections` S1 to S8 instead, with no
  `assignment`. `live/agent.py:140` then falls back to "Review the application and return a decision with findings."
  Import accepted the payload without noticing.
- **Plan:**
  1. One function, `runs/instructions.py: build(actor) -> (text, sha256)`, used by both the live and the mock agent.
     If `assignment` is present it is used as today, so existing projects don't change. Otherwise the text is rendered
     from `sections` in a fixed, deterministic order:
     - S1: title, scope, trigger, business context, deliverable, application type;
     - S2: input contract;
     - S3: failure behaviour (the operation list itself still comes from the environment);
     - S4: policy rule references (ID, version, hash; the rule text is not in the payload, and the text says so);
     - S5: numbered steps with their tool and failure behaviour;
     - S6: **output contract**, verbatim;
     - S8: sources used.

     Unknown section keys are appended under their own heading, never dropped. Nothing is read from the `private`
     part, so hidden-reference isolation is unchanged. A unit test asserts that no private value appears in the text.
  2. **Output contract:** the system protocol keeps the JSON envelope (`{"final": {...}}` with `decision` and
     `findings`). The user message adds S6 verbatim, so the model returns the structure the author asked for. The RL
     Gym does **not** add grader field names (`account_type` and so on) to the prompt: that would teach to the test.
     Fields a grader needs belong in the template's output contract (D-006, Studio).
  3. **No silent fallback:**
     - a task whose actor payload yields no instructions is imported as `blocked` ("no assignment or sections");
     - run admission refuses such a task;
     - the generic fallback text is removed for live runs.
  4. **Binding:** the instructions hash goes into the run manifest per task and into each sealed bundle. A run can
     then show exactly what the model was told, and re-runs of the same suite get the same text.
  5. **Tests:**
     - the renderer against a synthetic copy of the run-0228 actor payload (golden text and hash);
     - `assignment` still wins when present;
     - unknown sections kept;
     - no private keys in the text;
     - worker passes the built text to `live_agent` and the mock agent;
     - import blocks and admission refuses a payload with neither field.

     Then the full unit suite. Integration suites run in stub mode only with the owner's OK.
  6. Record the decision as RG-53 in BUILD-DECISIONS and the evidence in BUILD-STATUS.
- **Effect on past results:** run-0228's recorded scores stay as they are (they are the record). Its report should
  carry a note that the authored instructions were not delivered. Measuring again needs a new live run, which needs
  the owner's approval.

## D-008 Observations cut at 12,000 characters; prompts and raw responses not recorded (high)

- **Found:** 23 Nov 2026, D-005 evidence pack. Assigned to the RL Gym. Status: **fixed in a63ae67** (owner's go,
  23 Nov 2026). Bundles sealed before the fix stay as they were.
- **Cause:**
  - `live/agent.py` cuts each observation with `json.dumps(obs)[:MAX_OBS_CHARS]` (12,000). The cut is silent and
    leaves broken JSON. In run-0228, `application.read` returned about 75,600 characters, so the agent never saw its
    own application in 27 of 35 scored case episodes (every joint, custodial and teen case). The size itself is D-009 (Studio environment).
  - The live agent keeps its messages and the model's raw text in memory only. The sealed bundle keeps parsed actions
    and full observations; the ledger keeps tokens and cost. The reset response's `user_message` is used but not
    stored.
- **Plan:**
  1. **Visible, recorded cut:**
     - When an observation is longer than the limit, the model gets the first part plus an explicit line: "[cut:
       showing N of M characters; narrow the request]". No silent mid-JSON cut.
     - Each transcript step records `observation_chars` and `shown_chars`.
     - The run report shows "observations cut: K of S steps" and warns when K > 0, so a run like run-0228 is flagged.
  2. **Limit is part of the system version:**
     - `params.max_observation_chars`, default 12,000 (cost control: run-0228 already used about 154k input tokens per
       episode).
     - It is part of the version's config hash, so changing it makes a new system version (immutable binding).
     - The run projection uses it.
  3. **Record the conversation in the sealed bundle:** a new `agent_log` section.
     - `instructions` and `instructions_sha256` (the system and user messages sent first, once; links to D-007).
     - Per turn:
       - the model's raw text;
       - finish reason;
       - tokens in and out;
       - latency;
       - provider request ID;
       - how it was parsed (tool, final, or unreadable);
       - any nudge sent;
       - the observation text exactly as shown, which is the cut version, while the transcript keeps the full one.

       Messages are stored as deltas, not the whole history per turn, to keep the bundle size linear.
     - `reset`: the reset response's `user_message` and the reset fields the agent saw.
     - The bundle hash covers all of it. Keys never enter it: the gateway holds them.
  4. **Judge and generator:** the same recording for the judge's rubric prompt and raw answer, in the block line's
     receipt detail. Today only the parsed verdict is kept.
  5. **Mock runs:** produce the same `agent_log` shape, with their synthetic text labelled synthetic.
  6. **Evidence:** the D-005 pack exporter then shows prompts and responses instead of "not recorded".
  7. **Tests:**
     - cut marker and counts;
     - `agent_log` contents and hash;
     - no key or private value in the bundle;
     - the limit is in the config hash;
     - report warning.
- **Effect on past results:** none changes. Past bundles stay as sealed.

## D-010 `golden-kyc-openenv@v6` reference rows (low): closed, not a defect

- **Reported:** 23 Nov 2026 from my D-005 evidence pack, which said stale `@v6` reference rows contradict the @6 case
  data. **That reading was mine and it was wrong.**
- **What the data shows:**
  - `golden-kyc-openenv@v6` is a separate environment version from the Studio *stub* registry (`127.0.0.1:8211`, seed
    `kyc_cases-20261122`). It is not an older copy of `golden-kyc-openenv@6`, which comes from Studio at
    `127.0.0.1:8060`, seed `synthetic-kyc-cases@1.0.0:20261119`.
  - Its 360 reference rows sit in 9 integration-test workspaces, used by 9 controlled-mock runs (run-0168 to
    run-0217). The owner's workspace has **no** `@v6` rows.
  - `scoring.case_references` is unique on (workspace, environment version, case), and every reader filters by all
    three. Run-0228 could only read its own @6 rows. The pack's `raw/case-references.json` files contain only @6.
  - My ad-hoc query had no workspace filter.
- **Plan:**
  - No scoring change and no deletion. Test workspaces are separate by design, and deleting them is a destructive
    reset outside this task.
  - The pack README is corrected.
  - The only real issue is the look-alike version IDs (`@6` real, `@v6` stub). Proposed: the environment list labels
    stub-registry versions "stub registry". That is a UI wording change, if the owner wants it.
- **Status:** **closed, not a defect** (owner accepted, 23 Nov 2026). No code change.

## D-006 note (Studio)

The legacy `golden-kyc:*` criteria came from the template, not from an RL Gym binding.

- `catalog/templates.py` `activate()` stores exactly the `criteria` list Studio sends.
- Template `tpl_x5rwt6d5eu@6` (key `golden-kyc-v8`) was activated by `studio` on 23 Nov 01:22.
- The `golden-kyc:*` evaluator configurations were registered by `studio`, from `tpl_kyc_01@8`.
- Run-0228's suite has 20 criterion bindings, all `project_default`; the RL Gym added none.

D-006 stays with Studio.

## D-002 Inbox (header bell / To do) not working, reported in all three apps, RL Gym first

- **Found:** 23 Nov 2026, reported by the owner ("the inbox on any of the application is not working. Especially RL
  GYM"). Exact symptom not yet captured (panel does not open, opens empty, items do nothing, or links fail).
- **Checked so far (RL Gym):**
  - The data side works: `GET /todo` returns 52 items for admin-1 and admin-2 (ready_to_run 1, bindings 25, review
    12, import_export 2, studio_inbox 12); `/home` reports the same count. No server errors in the API log.
  - The bell (`RLGym.tsx`, `Bell` / `TodoPanel`) toggles a panel `#notif` positioned under the header
    (`gym.css`, header is `position: relative`). Not yet seen in a signed-in browser.
  - Suspects to check first: the app-wide `nav { overflow: auto }` rule (the bell sits inside the header `<nav>`, so
    its count badge and anything anchored to it can be clipped); the panel's outside-click handler; the item links
    (`item.link`) for the 52 items, many of which come from older stub projects.
- **Studio and Authoring inboxes:** not investigated here (other repositories); to be logged with their sessions.
- **Cause found (RL Gym, from the owner's screenshot):** the panel's groups used the class `stack`, and a later
  `gym.css` rule makes `.stack` the Runs episode bar (flex, 14 px high, overflow hidden). Each group was squashed into
  a clipped strip with its cards side by side. Header link and title styles also leaked into the panel (it sits inside
  the navy header).
- **Fix:** groups use their own class `todo-group`; the panel sets its own link and title colours. Type-check passes.
  The owner confirmed the panel looks right after a reload (23 Nov 2026).
- **Severity:** medium (the to-do list is how people find work waiting on them).
- **Status:** fixed in the RL Gym (dd23fc0), confirmed by the owner. Studio and Authoring inboxes not covered.

## D-001 Safety grader label still says "Promptfoo grader not installed"

- **Found:** 23 Nov 2026, run-0228 (Claude Haiku 5.5 on "KYC Customer onboarding for US bank").
- **Where:** `services/backend/src/anvil/rlgym/scoring/service.py:24`, `SAFETY_GRADER`.
- **What:** every safety episode's result names its grader as
  `rlgym-local-safety-oracle@1.0.0 (tool effects and output fields; Promptfoo grader not installed)`.
  Promptfoo 0.125.1 is installed (as a scoring plug-in, `promptfoo 1.1.0`), so the note is out of date and misleading.
  Same kind of stale text as the Trust & Safety generator note fixed in ad1a84d.
- **Actual behaviour is correct:** safety episodes are graded by the RL Gym's local oracle (tool effects and output
  fields); Promptfoo's red-team grader is not used for them.
- **Fix:** reword to say the local oracle grades safety episodes and Promptfoo's red-team grader is not used (Promptfoo
  runs only as a scoring plug-in). New results carry the new label; results already recorded keep theirs, because the
  grader label is part of the record of how an episode was graded.
- **Severity:** low (wording; scores unaffected).
- **Status:** **fixed in 615122d** (owner's go, 23 Nov 2026). The report and package "limits" lines had the same
  stale text and were fixed too. Results already recorded keep their label.
