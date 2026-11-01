"""Anvil Support Bot help pack: the business process behind each area, in plain language.

Sources: docs/product (00, 01, 14, 15, 18), docs/build/05-LIVE-EVALUATION.md and the D-SIMPLE
decision (docs/product/DECISIONS.md F-D22). Keep in step with them when behaviour changes.
Paragraphs are separated by blank lines.
"""

HELP_VERSION = "anvil-help/1 (1 Oct 2026)"

HELP = """ADI Anvil is ADI's Frontier Evaluation & Diagnostics Platform. Research teams define what they want to learn about a model's capability, assemble tasks and rubrics, run an evaluation, grade the outputs with people, and turn reviewed evidence into diagnostics, findings and reports. People make every decision; the assistant only explains.

SYNTHETIC AND ILLUSTRATIVE. Built-in task sets are original ADI synthetic cases. Fixture candidates are scripted answers, so their results are illustrative and never measured model performance. Live model calls and real email are switched off in this environment.

ROLES. Only Admin and RL Engineer are active access roles. Admin includes engineering and administration and can authorize an exact run and budget with Run. RL Engineers prepare tasks, run authorized evaluations, inspect dashboards and perform individually assigned grading duties. Grading assignments are duties, not additional roles. Historical role and approval records remain audit history.

MENU. The top row has areas: Home (Evaluations), Build (Research objectives, Tasks & data, Qualification, Rubrics, Benchmarks), Run & review (Runs, Review inbox), Insights (Diagnostics, Findings, Reports, Sales Kit) and Settings (Providers, Admins only). The second row shows the pages of the chosen area. You only see what your role can use.

EVALUATION WIZARD (Home → Evaluations → New evaluation). Five steps. 1 Research objective: a title, a hypothesis (what you expect to observe) and what success looks like (for example a minimum score with no critical violation). 2 Research: background notes and sources for reviewers; they never block you. Benchmark research (Benchmark Factory) helps compare catalog benchmarks; its recommendations pin exact task versions, so they are not attached to the wizard's new tasks automatically. 3 Tasks & data: choose built-in task sets; each has hidden reference answers that only graders see. 4 Rubric: starts from the ADI template; each criterion has an ID, a label, a weight (all weights must total 100%) and anchors describing scores 0 to 4; set the pass mark (0 to 100) and optional extra critical rules. 5 Benchmark & run: choose the fixture candidates and up to two graders, then Submit to Admin. After approval, press Run evaluation.

SCORING. Each criterion is scored 0 to 4. Score = sum of (weight × score ÷ 4), giving 0 to 100. Any critical rule violation means fail regardless of the score. A missing judgment is pending, never zero.

APPROVAL. One Admin approval covers the whole evaluation plan: objective, rubric, tasks, data rights, suite and protocol. Approving freezes exact versions and prepares the run; editing afterwards needs a new approval. Request changes sends the plan back to the author with your rationale. If a project has only one Admin, they may approve their own work and the audit log marks it self-approved; otherwise another Admin must approve it. Other people's sign-offs are optional recommendations.

GRADING (Run & review → Review inbox). The first grader grades every output. A second grader checks results with a critical violation, scores within 5 points of the pass mark, and a fixed 10% sample. If the two disagree (different pass/fail, different critical rules, or any criterion 2+ points apart), the adjudicator decides; graders' scores are never averaged. Every criterion needs a verbatim quote from the output as evidence. Raise a review issue for an ambiguous reference answer instead of failing the candidate.

RUNS (Run & review → Runs). Runs are launched explicitly and run in a durable background queue. States move from draft to queued, executing, awaiting review and reviewed. A provisional Sales Kit appears while human review is incomplete; it is labelled provisional and is not for external use.

TASKS & DATA (Build → Tasks & data). Upload CSV or JSONL task files, map their columns to the TaskSpec fields (external_id, instruction, input; references stay in a separate reference field), validate in the background, then publish an immutable dataset version. Imported tasks can be attached to suites and pinned to runs but cannot execute against fixture candidates yet. Uploaded files stay quarantined until a qualified scanner is available.

DIAGNOSTICS AND FINDINGS (Insights). Diagnostics shows observable evidence and relationships between cases, capabilities and episodes; it never claims to know a model's internal reasoning. A finding links a reviewed output quote to a rubric criterion and capability, with an explicit confidence and alternatives. Findings are approved when submitted and are covered by the report's approval.

REPORTS AND SALES KIT (Insights). A report summarises a reviewed run with honest denominators. After the Admin approves it, Anvil builds a one-page Sales Kit (PDF and HTML), an evidence ZIP and an internal brief for download. Nothing is emailed automatically.

PROVIDERS (Settings, Admins). Configuring a provider never authorises a model call. Paid runs need reviewed data rights, an exact model and budget, and the required paid-run approvals; live calls are disabled in this environment.

SIGN-IN. Accounts are invitation-only. New accounts get a temporary password that must be changed at first sign-in. Ask an Admin to invite a colleague or change roles."""
