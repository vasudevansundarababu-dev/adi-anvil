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

## D-041 next_action never checked whose request it is (high)

- **Found:** 24 Nov 2026 (E-007's KYC.REQUEST_PARTY example). next_action's template block only checks that an
  information request of the reference type exists, so a minor-without-TIN episode that asks the *adult* for the
  minor's TIN scored full marks.
- **Fix (RL Gym, D20 fix version; template unchanged):** runner version 2 runs the template's blocks plus RL Gym checks
  carried in the configuration (`extra_blocks`). The new `request_party` check reads, from the case's start state, which
  party lacks the requested item, using the rules of Studio's edge-case recipes (a TIN marked missing on a party's
  document, else a minor with no TIN; a government ID that expired before submission, else no ID at all; a party whose
  only documents are passports for proof of address) and fails unless a request of that type names that party. A type
  with no rule (street_address) is not checked; a start state that names no such party makes the check blocked.
- **Qualification:** the configuration carries regression fixtures (request to the minor: pass; to the adult: fail with
  STATE_MUTATION_ERROR; no start state: blocked), which its known-case tests now run beside allowed / disallowed /
  missing evidence. Dry run on the real v1 configuration, rolled back: all six checks pass, state qualified.
- **Shipping:** a person creates it: Admin → Evaluators → golden-kyc-blocks:next_action v1 → Create fix version → "Use
  suggested fix" → Create. On qualifying, projects following "Latest qualified" bind v2 at once (owner default), and
  Studio receives evaluator.registered with the reason ("fold into the next template version"). Not created yet.
- **Also fixed:** a fix version of a verifier-blocks configuration was refused (its known cases are generated, so the
  name-based check didn't fit).
- **Tests:** `tests/unit/test_rlgym_d041_request_party_unit.py`. **Status:** code on forge-v2-rlgym; version waits for a
  person.

## D-036 Scoring uses S7's published points and threshold (owner decision, E-007 §7.1)

- **Was:** pass 1 / fail 0 per criterion, decision's only partial = 0.8 (rationale judge 20%), pass at 90%. Authoring's
  S7 asks SMEs for 5/2/0 points with a pass threshold (22.5 of 25 on the v8 tasks) and marks identity, screening and
  decision critical; none of that was used. Under the old scale 24/25 passed; under S7 the next score below 25 is 22.
- **Now:** at admission each task's S7 (private part, as published; no template change) is read into a profile:
  anchors, maximum, threshold, weights, critical criteria and the rule text's hash (never the text). The profile is
  frozen per task in the manifest. Scoring gives each criterion its anchor (pass 5, partial 2, fail 0 of 5), passes at
  the threshold (the same share of the points that count; a blocked criterion earns 0 for the pass decision; a
  clause-excluded criterion lowers the maximum and threshold in proportion), and a fail on a critical criterion fails
  the task. The report header and PDF state the scale used.
- **S7 not in points:** v6's tasks allocate 100 points across dimensions with no 5/2/0 anchors. Those tasks keep the
  RL Gym scale, and admission ("S7 read for N of M tasks") and the report say which (default; the owner may change it).
  Tasks without S7 (fixtures, stub exports) are unchanged; runs admitted before D-036 are unchanged (no profile).
- **Checked:** the four 23 Nov v8 tasks all read as 5/2/0, 22.5 of 25, critical identity/screening/decision.
- **Tests:** `tests/unit/test_rlgym_d036_s7_unit.py`. **Status:** fixed on forge-v2-rlgym.

## D-040 Attacks reported as "tool result" were delivered in the user message (high; label fix)

- **Found:** 24 Nov 2026 (E-006 planning). Studio's OpenEnv simulator has no injection point, so the RL Gym sends every
  attack with the user message (`openenv.py`, "rlgym_user_message"), but the manifest, run page, report and suite said
  "tool result". Past runs overstate resistance to hidden instructions.
- **Fix (label only):** the manifest records `delivered_as` (user_message on OpenEnv); episode bundles record the
  delivered `placement` and the `requested_placement`; the report and run page say where attacks were delivered and,
  when that differs from the suite, that hidden instructions in documents or tool output were not tested. Older runs'
  reports work it out from the environment version. Real tool-response injection is E-006.
- **Tests:** `tests/unit/test_rlgym_d038_d040_unit.py`. **Status:** fixed on forge-v2-rlgym (backend needs a restart).

## D-038 Required edge cases list was hard-coded (medium)

- **Found:** 24 Nov 2026. Suites → Data plan offered minor_without_tin, expired_id, screening_hit, address_mismatch
  whatever the environment; on @8 three of those can never be met and three real tags couldn't be required. The suite
  page also flagged every edge-focused task "unmatched", because @6-@8's mirrored summaries list no edge cases.
- **Fix:** the bound environment's edge cases are counted from its case rows (registry, once per immutable version;
  the summary is used if the registry is down, never cached), filling the catalog used for quota cells, availability
  and the "unmatched" check. The page lists each tag with its case count and application types; a tag the saved plan
  requires but the version lacks shows "not in this environment version".
- **Tests:** same file. **Status:** fixed on forge-v2-rlgym (backend needs a restart; the page falls back to an empty
  list until then).

## D-033 Leaderboard counts every completed run (enhancement; small part built)

- **Raised:** 24 Nov 2026 by the owner: the leaderboard should be by domain, not project or cohort, and not every run
  should count; the person starting a run chooses. Domain leaderboard is E-003 (design repo), later. Built now: the
  opt-in tick.
- **New run:** checkbox "Count this run on the leaderboard", unticked by default. The request field `leaderboard`
  counts only when it is JSON `true`.
- **Frozen:** the value is written into the run manifest (`"leaderboard": true|false`), so it is inside
  `manifest_sha256` and cannot change after admission. No database column, no migration.
- **Leaderboard and Home:** only completed benchmark runs whose manifest says `true` are ranked; Project and Cohort
  pickers unchanged. Runs admitted before D-033 have no flag and are not counted (no backfill), so the leaderboard is
  empty until a ticked run completes: "No leaderboard runs yet. Tick 'Count this run on the leaderboard' when you
  start a run."
- **Markers:** "Leaderboard run" badge on the Runs list and the run page; the run page shows "View on leaderboard" only
  for leaderboard runs. Runs list and run API gain a read-only `leaderboard` field.
- **Tests:** `tests/unit/test_rlgym_d033_leaderboard_unit.py` (3); unit suite 585 passed; web `tsc --noEmit` passes.
  The integration runs that expect a ranked leaderboard now start with `leaderboard: true`
  (`test_rlgym_v2_runs.py` `finished`, `test_rlgym_v2_sme.py`); integration suites not run (they need the services
  restarted on this code).
- **Status:** built on `forge-v2-rlgym-next`, not deployed.

## D-032 "New run" is link text, not a button (P3)

- **Found:** 24 Nov 2026 by the owner on the Runs page: "Compare (0)" and "Package (0)" are buttons, "New run" next to
  them is plain green link text.
- **Cause:** `New run` (and `Export PDF` on the report, `Download PDF` on the PDF preview) are links with
  `className="primary"`, but `gym.css` styled `.primary` only on `<button>`, so they fell back to the link colour.
- **Fix:** `gym.css` gives `a.primary` the primary button's look (blue, same padding, border and radius as
  `button.primary`) and `a.button` the secondary button's look. The Runs banner's "Download package" link uses
  `a.button`. Navigation links (Back to report, Open a failing case, table links) stay links.
- **Other list pages checked:** Projects, Suites, Models and Admin already use real buttons for their actions; no
  change there.
- **Tests:** `tsc --noEmit` passes; the new CSS checked on a static copy of the Runs toolbar (New run, Download PDF
  and Start run render the same).
- **Severity:** P3. **Status:** fixed on `forge-v2-rlgym-next`, not deployed.

## D-030 (master log: D-031) Edge-case suite admitted with 0 episodes (high)

- **Found:** 23 Nov 2026, run-0229 ("KYC onboarding for US Bank with Edgecase", Haiku 5.5 live, $0.30/episode),
  suite "SUite Name For KYC Edgecases" v1 on `golden-kyc-openenv@8`. Reported by the owner: Overview shows Failed,
  "No episodes (refused)".
- **What happened:** admission passed and the manifest said 53 episodes ($15.90 projected), but the `run.admitted`
  event had 0 episodes and no episode rows were created; the worker started the environment and marked the run failed
  3 seconds later. No model calls were made and nothing was spent (`systems.live_calls` empty, instance cost $0).
- **Cause 1 (sampling):** all four tasks are edge-focused (individual + passport_only, custodial +
  sanctions_dob_mismatch, adult_joint + expired_document, teen_joint + minor_without_tin). An edge-focused task takes
  only cases with its tag (`sampling.match_task`). The data plan (no edge minimums) sampled 20 cases by application
  type × completeness without regard to the tasks, so all 20 were cases no task takes. @8 has 10–20 cases for each
  task's type and tag, so the data was never the problem.
- **Cause 2 (admission):** the episode count and spend projection came from the sample size, not from the cases that
  matched a task, and no check failed when none matched.
- **Fix:** `sampling.select_cases` takes the suite's tasks and samples only cases one of them takes (no tasks given:
  unchanged; suites whose tasks take every case of their type pick exactly the same cases as before). Admission counts
  only matched cases (and safety prompts only when at least one case matched) and adds a `task_match` check that blocks
  when no sampled case matches a task and lists unmatched cases otherwise.
- **Replay of run-0229's inputs (offline):** before, 20 sampled, 20 unmatched; after, 8 sampled, 0 unmatched. Only 8
  because on @8 every edge-tagged case is "incomplete", so the plan's four "complete" cells (3 each) can't be filled;
  with `use_available` the run goes ahead on the 8 and admission shows the shortfall. Setting the plan's completeness
  quotas to 100 % incomplete would give 20.
- **Tests:** `test_d030_*` in `tests/unit/test_rlgym_v2_runs_unit.py`: edge-only suite samples only
  cases its tasks take; plain tasks sample exactly as before; admission blocks when none match. Unit suite 582 passed.
- **Not done:** the data plan editor's "available" counts are still per application type, not per task; run-0229
  stays failed (a new run is needed; the owner starts live runs).
- **Severity:** high (an edge-case suite could not run). **Status:** fixed on forge-v2-rlgym, not pushed.

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
