# RL Gym defects (open)

Local list until the owner logs them in the tracker. Newest first.

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
- **Next step:** reproduce signed in (screenshot or the owner's description of what happens on click), then fix.
- **Severity:** medium (the to-do list is how people find work waiting on them).
- **Status:** open.

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
