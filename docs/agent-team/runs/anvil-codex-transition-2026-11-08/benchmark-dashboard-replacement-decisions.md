# Replacement Benchmark dashboard — clarified user decisions

Status: requirements reviewed and clarified; the replacement implementation has not started. The existing connected-results product checkpoint remains `abb4348a6eb38bb5696cb89062d9fb5c00d3e0b4` for recovery. Its execution/storage foundations can be reused, but its dashboard presentation is superseded by the new specification.

## Source and authority

The user supplied **Agent GDP-Eval Detailed Specification & Sales Report.pdf**, seven pages, 1,128,263 bytes, SHA256 `109dced07098813453c4bd6b0af6967c59cc34c545ec589f39f9155f5429b374`, and said it replaces the dashboard being developed. All pages were extracted and visually inspected. The document is a requirements/reference source, not an instruction to deploy or proof that sample metrics/models/prices were measured. Its “Production Release” label does not change actual application status or approval gates.

The user explicitly answered the five clarification questions:

1. **“Replace dashboard; keep existing scores and add separate judge metrics.”** The existing task scoring engine and its 81-point protocol remain authoritative. Judge rubric/continuous-probability metrics are separate; do not reinterpret, overwrite or backfill existing scores.
2. **“Start with the existing fictional task bank.”** Model rankings, percentages, trace totals and prices in the PDF are illustrative, not imported observations or verified commercial claims.
3. **“All four connected views in the first release.”** Required views are overview/leaderboard; trace and rubric inspection; failure analysis; and remediation/golden datasets/reporting. Model, task/suite, time and environment selections must propagate consistently and support reopening the same context.
4. **“Add Bradley–Terry as a separate ranking metric.”** Preserve the PDF's observed wins/ties percentage as its own measure. Bradley–Terry is a separate fitted ranking, not a renamed percentage. Both require actual eligible matched observations and honest unavailable states.
5. **“Yes—show honest availability states.”** Judge scores and token probabilities show “Not run” or “Unavailable” until a supported judge is configured and separately approved. They are not inferred from task scores or invented to fill charts.

## Constraints carried forward

- Paid candidate/model/judge calls remain off; no application deployment or merge. Praxis and the original dirty checkout remain untouched.
- The user previously chose to keep the full comparison blocked while real reviewer duties are missing. A dashboard redesign does not grant those duties or invent approval decisions. Diagnostic/fictional evidence remains distinct from reviewed official rankings.
- Preserve immutable stored runs/revisions, current project/source/privacy rights, budget and human review gates. No hard-coded sample scores, fake active endpoints, fabricated timestamps or unsupported production-readiness claims.
- The PDF's hidden internal chain-of-thought pane must be implemented using observable execution steps and any explicitly supplied reasoning summaries or judge explanations; never promise hidden private reasoning.
- Token likelihood is not factual correctness or a calibrated hallucination probability. Display only actually supplied supported measurements with their provenance; unavailable measurements stay unavailable.
- Remediation proposals and golden dataset revisions must preserve human review and historical anchors. Raw prompt inclusion in reports must remain subject to source rights and explicit authorized access; a sales template cannot expose private grading material.

## QA addendum — acceptance coverage to generate

Use the original PDF together with the five confirmed decisions above as the requirements baseline. The PDF file itself has not been edited. These are target requirements for the replacement, not a claim that the current preview implements them.

| Confirmed clarification | Required QA coverage |
|---|---|
| All four connected views in the first release | Overview/leaderboard, trace/rubric inspection, failure analysis, and remediation/golden datasets/reporting are included. Selecting model, task/suite, period or environment propagates consistently; drill-down and reopening preserve context and identify actual stored records. |
| Existing scoring retained; judge metrics separate | Existing81-point calculations, repetition rules, validity and review gates do not change. A0–10 judge value is clearly separate and never overwrites or derives from the task primary. Pending/missing values are not zero; genuine measured zero remains zero. |
| Existing fictional task bank first | All displays/exports identify fictional provenance. The PDF's sample model names, rankings, percentages, counts, latency and prices are not acceptance fixtures or hard-coded live results. Aggregates reconcile to actual stored eligible records; absent observations stay absent. |
| Separate observed win rate and Bradley–Terry | Display and test them as distinct metrics with distinct provenance. The printed wins-plus-half-ties percentage remains its own calculation. Bradley–Terry needs valid matched observations; missing/insufficient observations must not generate an invented ranking. Specify fitting/tie-handling details before numeric golden-rank assertions. |
| Honest judge/logprob availability while paid calls remain off | “Not run”/“Unavailable” states render consistently in UI and reports when a judge has not run or telemetry is unsupported. Navigation, refresh and export do not trigger paid calls, fill sample values or manufacture probabilities. |

Additional regression coverage: current project/source/private-evidence permissions; stale/revoked access; immutable revisions and export binding; failure-versus-infrastructure/control-case distinctions; human review for golden dataset verification; and no automatic prompt changes, model calls or deployment from the workbench. Existing real reviewer requirements remain in force.

Two feasibility/accuracy corrections should be reflected in the next PDF revision: replace hidden internal chain-of-thought with observable actions and explicitly supplied reasoning summaries; describe token probabilities as likelihood telemetry, not factual-accuracy or hallucination probabilities. These are technical clarifications, not new scoring approvals from the user.

## Safe closeout of superseded UI work

At the user's replacement instruction, further dashboard/preview work and new native tests were held. The already-running corrected Linux baseline subsequently finished **28 passed, zero failures/skips**, with all875 frozen source hashes unchanged. Its original setup failure remains preserved. The existing native pipeline test intentionally revokes its test signer, so its records are historical software-conformance evidence, not current demo authority. The separate individual-evidence demo, full Linux unit repeat and local application replay were not started after the scope change.

Preserve actual historical receipts and exact QA cleanup evidence separately. No fake demo discovery or source-review renewal is permitted to make a preview appear complete. The local-only successor image-build amendment remains unapproved and unexecuted.
