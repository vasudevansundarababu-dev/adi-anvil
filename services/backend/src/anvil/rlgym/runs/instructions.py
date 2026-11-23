"""The agent's task instructions, built from the task's actor payload only (D-007).

Two payload shapes reach the RL Gym:
- `assignment`: one text (the RL Gym's own fixtures and Studio stub exports). Used as it is.
- `sections`: ADI Forge's authored task, S1 to S8 (scope, input contract, tools and failure behaviour, policy rules,
  steps, output contract, sources). Rendered to one text in a fixed order, so the same payload always gives the same
  text and hash. Unknown sections are kept under their own heading, never dropped.

Only the actor part is read: the private part (reference answers, rubric) never reaches this text. A payload with
neither field has no instructions; the task is blocked at import and refused at run admission, and an episode never
runs on a generic fallback.
"""

import hashlib
import json

from anvil.rlgym.common import GymError

ORDER = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")
TITLES = {
    "S1": "Task",
    "S2": "Input",
    "S3": "Tools and failure behaviour",
    "S4": "Policy rules",
    "S5": "Steps",
    "S6": "Output contract",
    "S7": "Notes",
    "S8": "Sources",
}
S1_FIELDS = (
    ("title", "Title"),
    ("applicationType", "Application type"),
    ("scope", "Scope"),
    ("trigger", "Trigger"),
    ("businessContext", "Business context"),
    ("deliverable", "Deliverable"),
    ("exampleGoverningState", "Example governing state"),
    ("language", "Language"),
)


def _text(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _fields(sec, known):
    """Known fields in order with their labels, then any other fields (sorted) with their own key as the label."""
    lines, seen = [], set()
    for key, label in known:
        if _text(sec.get(key)):
            lines.append(f"{label}: {_text(sec[key])}")
            seen.add(key)
    for key in sorted(k for k in sec if k not in seen):
        if _text(sec[key]):
            lines.append(f"{key}: {_text(sec[key])}")
    return lines


def _section(key, sec):
    if not isinstance(sec, dict):
        return [_text(sec)] if _text(sec) else []
    if key == "S1":
        return _fields(sec, S1_FIELDS)
    if key == "S2":
        return _fields(sec, (("inputContract", "Input contract"),))
    if key == "S3":
        # The operation list comes from the environment (system message); the task's failure behaviour is kept here.
        return _fields(
            {k: v for k, v in sec.items() if k != "tools"},
            (("environment", "Environment"), ("failureBehaviour", "If a tool fails")),
        )
    if key == "S4":
        rules = sec.get("statePolicies") or []
        lines = [
            f"- Rule {r.get('ruleId')} ({r.get('locator')}, version {r.get('ruleVersion')}, sha256 {r.get('contentSha256')})"
            for r in rules
            if isinstance(r, dict)
        ]
        if lines:
            lines.insert(
                0,
                "The project's published policy rules apply (their text is available through the policy operations):",
            )
        return lines + _fields({k: v for k, v in sec.items() if k != "statePolicies"}, ())
    if key == "S5":
        lines = []
        for i, s in enumerate(sec.get("steps") or [], 1):
            if not isinstance(s, dict):
                lines.append(f"{i}. {_text(s)}")
                continue
            line = f"{i}. {_text(s.get('action'))}"
            if s.get("tool"):
                line += f" (record with {s['tool']})"
            lines.append(line)
            if _text(s.get("failureBehaviour")):
                lines.append(f"   If this fails: {_text(s['failureBehaviour'])}")
        return lines + _fields({k: v for k, v in sec.items() if k != "steps"}, ())
    if key == "S6":
        return _fields(sec, (("outputContract", "Output contract"),))
    if key == "S8":
        return _fields(sec, (("sourcesUsed", "Sources"),))
    return _fields(sec, ())


def from_sections(sections):
    parts = []
    keys = [k for k in ORDER if k in sections] + sorted(k for k in sections if k not in ORDER)
    for key in keys:
        body = _section(key, sections[key])
        if body:
            parts.append(f"## {TITLES.get(key, key)}\n" + "\n".join(body))
    return "\n\n".join(parts)


def build(actor):
    """{"text", "sha256", "source"} for the actor payload, or GymError TASK_NO_INSTRUCTIONS."""
    actor = actor or {}
    if isinstance(actor.get("assignment"), str) and actor["assignment"].strip():
        text, source = actor["assignment"].strip(), "assignment"
    elif isinstance(actor.get("sections"), dict) and actor["sections"]:
        text, source = from_sections(actor["sections"]), "sections"
    else:
        text, source = "", None
    if not text:
        raise GymError(
            "TASK_NO_INSTRUCTIONS",
            "The task's actor payload has no assignment and no sections; it cannot be given to an agent",
        )
    return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest(), "source": source}


def problem(actor):
    """None if the payload yields instructions, else the reason (for import and admission checks)."""
    try:
        build(actor)
        return None
    except GymError as exc:
        return exc.message
