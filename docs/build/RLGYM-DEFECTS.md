# RL Gym defects (open)

Local list until the owner logs them in the tracker. Newest first.

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
- **Status:** open, not fixed.
