# Anvil and Praxis document review — 2 November 2026

Start with each product's module guide: module definitions, distinctive features and
implementation boundaries. Then review the 30-day roadmap and YC evidence summary.

## Anvil

- [Module definitions and distinctive features](product/MODULE-GUIDE.md)
- [YC review and verification evidence](generated/yc-review-2026-11-02.md)
- [30-day roadmap: 3 November–2 December](build/11-30-DAY-ROADMAP.md)
- [Verified hosted URLs and login steps for both apps](runbooks/reviewer-sign-in.md)
- [5 PM Chicago demo recording plan](build/12-YC-DEMO-PLAN.md)

## Praxis

The companion repository contains `docs/MODULE-GUIDE.md`, `docs/YC-REVIEW.md`,
`docs/30-DAY-ROADMAP.md` and `docs/REVIEWER-SIGN-IN.md`. The downloadable review bundle
includes these under `Praxis/`, alongside the Anvil documents under `Anvil/`.

## Decisions to review

1. Module descriptions distinguish implemented behavior from planned functionality.
2. Benchmarks is an explicitly labeled two-page UI mockup; displayed scores/counts
   are illustrative. Full functionality is deferred; GDPVal remains Planned.
3. The 30-day roadmap includes Anvil completed run → Praxis SME assignment → review
   returned and logged in Anvil. This API integration is not implemented yet.
4. Marketing, Banking and Commerce target 200–500 independently expert-authored samples
   per taskbank, each professor/guide verified before publication. Banking KYC/AML and
   fraud are reference use cases. Wharton/Harvard through Bodhium and Banking-network
   recruiting are proposed channels, not confirmed partnerships or endorsements.
5. The bounded Gemini diagnostic succeeded with one real call costing $0.008462; all
   six previous unknown requests and their reservations were preserved. The user
   subsequently reported that all models are working; that broader report is not a
   new independent verification of every run by this task.

Code and documents are committed locally on the existing codex branches. GitHub
publication remains separate from this review bundle. Unrelated working-tree edits,
credentials, raw logs, SDK downloads and private videos are excluded.
