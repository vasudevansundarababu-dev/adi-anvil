"""Case selection and episode expansion (SPEC 07.5 data plan, 07.5b; ARCHITECTURE 9.6).

A run never creates data: it selects cases from the bound environment version's case list (actor-visible dimensions
only) with the suite's data plan and sampling seed, so the same plan on the same catalog always picks the same cases.
Episodes = (cases + approved safety prompts) × models × attempts. Each case is matched to a ready task of its case
class; a safety prompt is played on one of the selected cases.

D-059: the plan's `untagged_cases` option (off by default) lets an edge-focused task also take the untagged cases of
its application type (clean or problem), never another task's tags. Each untagged case then needs a reference answer
from Studio's scorer (`select_checked`); one without is excluded and counted, never guessed.
"""

import hashlib


def _key(seed, *parts):
    return hashlib.sha256(":".join([str(seed), *map(str, parts)]).encode()).hexdigest()


def select_cases(plan, cells, cases, tasks=None):
    """Pick cases for every cell of the plan. Edge-case minimums are filled first (they count toward their stratum
    cell); then each stratum × completeness cell up to its (possibly lowered) quota, never more than exists.
    `tasks`: the suite's tasks; when given, only cases one of them takes are sampled (an edge-focused task takes only
    cases with its tag, so a type-only sample could pick cases no task runs). Without tasks, every case is eligible.
    Returns (selected cases in a stable order, per-cell picks, short cells)."""
    seed = plan["sampling_seed"]
    untagged = bool(plan.get("untagged_cases"))
    if tasks:
        cases = [c for c in cases if match_task(c, tasks, seed, untagged) is not None]
    strata = [cl for cl in cells if not cl["cell_key"].startswith("edge:")]

    def stratum_of(case):
        return _stratum(case, strata)

    picked, used = [], set()
    by_cell = {}
    for case in cases:
        key = stratum_of(case)
        if key:
            by_cell.setdefault(key, []).append(case)
    quotas = {cl["cell_key"]: cl["quota"] for cl in cells}
    counts = {k: 0 for k in quotas}
    short = []
    for cell in sorted(
        (cl for cl in cells if cl["cell_key"].startswith("edge:")), key=lambda c: c["cell_key"]
    ):
        tag = cell["cell_key"][5:]
        pool = sorted(
            (c for c in cases if tag in c["edge_cases"] and c["case_id"] not in used),
            key=lambda c: _key(seed, cell["cell_key"], c["case_id"]),
        )
        have = sum(1 for c in picked if tag in c["edge_cases"])
        for case in pool:
            if have >= cell["quota"]:
                break
            stratum = stratum_of(case)
            if stratum is None or counts.get(stratum, 0) >= quotas.get(stratum, 0):
                continue
            picked.append(case)
            used.add(case["case_id"])
            counts[stratum] = counts.get(stratum, 0) + 1
            have += 1
        counts[cell["cell_key"]] = have
        if have < cell["quota"]:
            short.append({"cell_key": cell["cell_key"], "quota": cell["quota"], "picked": have})
    for cell in sorted(strata, key=lambda c: c["cell_key"]):
        key = cell["cell_key"]
        pool = sorted(
            (c for c in by_cell.get(key, []) if c["case_id"] not in used),
            key=lambda c: _key(seed, key, c["case_id"]),
        )
        for case in pool:
            if counts[key] >= cell["quota"]:
                break
            picked.append(case)
            used.add(case["case_id"])
            counts[key] += 1
        if counts[key] < cell["quota"]:
            short.append({"cell_key": key, "quota": cell["quota"], "picked": counts[key]})
    picked.sort(key=lambda c: c["case_id"])
    return picked, counts, short


def _stratum(case, strata):
    """The stratum cell whose dimension values the case has (default: "<application_type>|<completeness>")."""
    from anvil.rlgym.suites.service import case_value

    for cl in strata:
        if all(case_value(case, k) == v for k, v in (cl["dimension_values"] or {}).items()):
            return cl["cell_key"]
    return None


def select_checked(plan, cells, cases, tasks, references_for, gradable_for=None, skipped=None):
    """`select_cases`, then, with the plan's `untagged_cases` on, a reference check of every selected untagged case:
    `references_for(ids)` returns the ids Studio's scorer has a (hash-valid) reference for. A case without one is
    excluded and the selection made again without it, until every selected untagged case has one. `gradable_for(ids)`
    (optional) returns the ids whose reference can be graded: any selected case (tagged or not) that can't (awaiting
    the SME, or the PM in a real project) is skipped the same way and its id appended to `skipped`. Each case is asked
    about once per check. Returns (selected, per-cell picks, short cells, excluded case ids in the order found)."""
    excluded, checked, graded = [], set(), set()
    awaiting = []
    pool = cases
    while True:
        selected, counts, short = select_cases(plan, cells, pool, tasks)
        out = []
        if plan.get("untagged_cases"):
            need = [
                c["case_id"]
                for c in selected
                if not c.get("edge_cases") and c["case_id"] not in checked
            ]
            if need:
                have = set(references_for(need))
                checked |= set(need)
                out = [i for i in need if i not in have]
                excluded += out
        if gradable_for:
            need = [
                c["case_id"]
                for c in selected
                if c["case_id"] not in graded and c["case_id"] not in out
            ]
            if need:
                ok = set(gradable_for(need))
                graded |= set(need)
                not_ok = [i for i in need if i not in ok]
                awaiting += not_ok
                out += not_ok
        if not out:
            if skipped is not None:
                skipped.extend(sorted(awaiting))
            return selected, counts, short, excluded
        gone = set(excluded) | set(awaiting)
        pool = [c for c in cases if c["case_id"] not in gone]


def takeable_counts(cells, cases, tasks, seed):
    """{cell_key: {"tagged": n, "untagged": m}}: per cell, the tagged cases a suite task takes and the untagged cases a
    task would take with the `untagged_cases` option on (the data plan table shows both)."""
    strata = [cl for cl in cells if not cl["cell_key"].startswith("edge:")]
    out = {cl["cell_key"]: {"tagged": 0, "untagged": 0} for cl in cells}
    for case in cases:
        tagged = bool(case.get("edge_cases"))
        if match_task(case, tasks, seed, untagged=not tagged) is None:
            continue
        kind = "tagged" if tagged else "untagged"
        key = _stratum(case, strata)
        if key:
            out[key][kind] += 1
        for tag in case.get("edge_cases") or []:
            if f"edge:{tag}" in out:
                out[f"edge:{tag}"][kind] += 1
    return out


def selector_types(sel):
    """The application types a task's case_selector names: one (golden KYC v8) or a list (KYC Judgment v1, spec §16:
    one task covers all four account types)."""
    sel = sel or {}
    # Authoring's one-task export: `application_types` (a list, from coveredApplicationTypes).
    v = (
        sel.get("application_types")
        if sel.get("application_types")
        else sel.get("application_type")
    )
    if isinstance(v, list):
        return {x for x in v if x}
    return {v} if v else set()


def match_task(case, tasks, seed, untagged=False):
    """The ready task of this case's class: same application type and completeness; a task focused on an edge tag is
    used only for cases carrying that tag, and preferred for them. `untagged` (the plan's D-059 option): an untagged
    case no plain task takes goes to an edge-focused task of its application type."""
    # A task without `completeness` (ADI Forge's exports name only the application type) takes either completeness.
    same = [
        t
        for t in tasks
        if case["application_type"] in selector_types(t["case_selector"])
        and t["case_selector"].get("completeness") in (None, case["completeness"])
    ]
    focused = [
        t
        for t in same
        if t["case_selector"].get("edge_cases")
        and set(t["case_selector"]["edge_cases"]) <= set(case["edge_cases"])
    ]
    plain = [t for t in same if not t["case_selector"].get("edge_cases")]
    if not focused:
        # An edge-focused task can also take a complete case of its type with that tag regardless of completeness.
        focused = [
            t
            for t in tasks
            if case["application_type"] in selector_types(t["case_selector"])
            and t["case_selector"].get("edge_cases")
            and set(t["case_selector"]["edge_cases"]) <= set(case["edge_cases"])
        ]
    pool = focused or plain
    if not pool and untagged and not case.get("edge_cases"):
        pool = [
            t
            for t in tasks
            if case["application_type"] in selector_types(t["case_selector"])
            and t["case_selector"].get("completeness") in (None, case["completeness"])
        ]
    if not pool:
        return None
    pool = sorted(pool, key=lambda t: t["task_id"])
    return pool[int(_key(seed, "task", case["case_id"]), 16) % len(pool)]


def expand(plan, selected, tasks, prompts, members, attempts):
    """Episode specs in a stable order. `members` are (system_id, system_version); `prompts` approved safety prompts."""
    seed = plan["sampling_seed"]
    untagged = bool(plan.get("untagged_cases"))
    matched, unmatched = [], []
    for case in selected:
        task = match_task(case, tasks, seed, untagged)
        (matched if task else unmatched).append((case, task))
    work = [("case", case, task, None) for case, task in matched]
    for i, prompt in enumerate(sorted(prompts, key=lambda p: p["id"])):
        if not matched:
            break
        ordered = sorted(matched, key=lambda ct: _key(seed, "ts", prompt["id"], ct[0]["case_id"]))
        case, task = ordered[i % len(ordered)] if len(ordered) > 1 else ordered[0]
        work.append(("safety", case, task, prompt))
    specs = []
    for system_id, system_version in members:
        for attempt in range(1, attempts + 1):
            for kind, case, task, prompt in work:
                specs.append(
                    {
                        "kind": kind,
                        "case": case,
                        "task": task,
                        "prompt": prompt,
                        "system_id": system_id,
                        "system_version": system_version,
                        "attempt": attempt,
                    }
                )
    return specs, [c["case_id"] for c, _ in unmatched]
