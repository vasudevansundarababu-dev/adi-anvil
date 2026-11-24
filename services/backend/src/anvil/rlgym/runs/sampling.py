"""Case selection and episode expansion (SPEC 07.5 data plan, 07.5b; ARCHITECTURE 9.6).

A run never creates data: it selects cases from the bound environment version's case list (actor-visible dimensions
only) with the suite's data plan and sampling seed, so the same plan on the same catalog always picks the same cases.
Episodes = (cases + approved safety prompts) × models × attempts. Each case is matched to a ready task of its case
class; a safety prompt is played on one of the selected cases.
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
    if tasks:
        cases = [c for c in cases if match_task(c, tasks, seed) is not None]
    picked, used = [], set()
    by_cell = {}
    for case in cases:
        by_cell.setdefault(f"{case['application_type']}|{case['completeness']}", []).append(case)
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
            stratum = f"{case['application_type']}|{case['completeness']}"
            if counts.get(stratum, 0) >= quotas.get(stratum, 0):
                continue
            picked.append(case)
            used.add(case["case_id"])
            counts[stratum] = counts.get(stratum, 0) + 1
            have += 1
        counts[cell["cell_key"]] = have
        if have < cell["quota"]:
            short.append({"cell_key": cell["cell_key"], "quota": cell["quota"], "picked": have})
    for cell in sorted(
        (cl for cl in cells if not cl["cell_key"].startswith("edge:")), key=lambda c: c["cell_key"]
    ):
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


def match_task(case, tasks, seed):
    """The ready task of this case's class: same application type and completeness; a task focused on an edge tag is
    used only for cases carrying that tag, and preferred for them."""
    # A task without `completeness` (ADI Forge's exports name only the application type) takes either completeness.
    same = [
        t
        for t in tasks
        if t["case_selector"]["application_type"] == case["application_type"]
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
            if t["case_selector"]["application_type"] == case["application_type"]
            and t["case_selector"].get("edge_cases")
            and set(t["case_selector"]["edge_cases"]) <= set(case["edge_cases"])
        ]
    pool = focused or plain
    if not pool:
        return None
    pool = sorted(pool, key=lambda t: t["task_id"])
    return pool[int(_key(seed, "task", case["case_id"]), 16) % len(pool)]


def expand(plan, selected, tasks, prompts, members, attempts):
    """Episode specs in a stable order. `members` are (system_id, system_version); `prompts` approved safety prompts."""
    seed = plan["sampling_seed"]
    matched, unmatched = [], []
    for case in selected:
        task = match_task(case, tasks, seed)
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
