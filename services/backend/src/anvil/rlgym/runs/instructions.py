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
    if key == "S4" and sec.get("policyLibrary"):
        # KYC Judgment C4: the agent sees the policy library in force (documents), never a list of rules and never the
        # private expectedRules or notes, even if an export carried them into the actor part. Which rules apply is
        # the agent's to work out from policy.read.
        lines = ["The policy library in force (read its rules with policy.read):"]
        for d in sec["policyLibrary"]:
            if isinstance(d, dict):
                lines.append(
                    f"- {_text(d.get('title'))} (document {_text(d.get('documentId'))}, version "
                    f"{_text(d.get('documentVersion'))})"
                )
        return lines
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
        # E-002 §4.3.6: selected clause versions, as the agent reads them: the clause text (or quote) and its
        # identity. Conditions, exceptions and the criteria that test them are for the RL Gym, not the agent.
        lines += clause_lines(sec.get("policyBindings"))
        return lines + _fields(
            {k: v for k, v in sec.items() if k not in ("statePolicies", "policyBindings")}, ()
        )
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
            # D-016: conditional follow-ups, in order ("If <condition>: a then b"; no condition = a chain, "Then: a").
            for f in s.get("followUps") or []:
                if not isinstance(f, dict):
                    lines.append(f"   Then: {_text(f)}")
                    continue
                tools = " then ".join(_text(t) for t in (f.get("tools") or []) if _text(t))
                cond = _text(f.get("if"))
                extra = _fields({k: v for k, v in f.items() if k not in ("if", "tools")}, ())
                lines.append(f"   If {cond}: {tools}" if cond else f"   Then: {tools}")
                lines += [f"     {x}" for x in extra]
            if _text(s.get("failureBehaviour")):
                lines.append(f"   If this fails: {_text(s['failureBehaviour'])}")
            # Any other key in a step reaches the agent too; nothing is dropped silently.
            known = ("action", "tool", "failureBehaviour", "followUps")
            lines += [
                f"   {x}" for x in _fields({k: v for k, v in s.items() if k not in known}, ())
            ]
        rights = sec.get("decisionRights")
        if isinstance(rights, list) and rights:
            # KYC Judgment C4: who may take each action, as a table.
            lines += [
                "",
                "Decision rights:",
                "| Action | Who may | Needs approval from | Escalate to |",
                "|---|---|---|---|",
            ]
            for r in rights:
                if isinstance(r, dict):
                    cells = [
                        _text(r.get(k)) or "—"
                        for k in ("action", "whoMay", "needsApprovalFrom", "escalateTo")
                    ]
                    lines.append("| " + " | ".join(cells) + " |")
        return lines + _fields(
            {k: v for k, v in sec.items() if k not in ("steps", "decisionRights")}, ()
        )
    if key == "S6":
        return _fields(sec, (("outputContract", "Output contract"),))
    if key == "S8":
        return _fields(sec, (("sourcesUsed", "Sources"),))
    return _fields(sec, ())


def clause_lines(selected):
    """The selected clause versions as the agent reads them: identity, locator, the obligation (or quote, or title)
    and any exception's text. Conditions and the criteria that test them are for the RL Gym, never the agent."""
    chosen = [b for b in selected or [] if isinstance(b, dict)]
    if not chosen:
        return []
    lines = ["These policy clauses apply where their conditions hold:"]
    for b in chosen:
        # The export form (clause_id, version, source{locator, quote}), {clause: {...}}, or the flat provisional form.
        ident = b["clause"] if isinstance(b.get("clause"), dict) else b
        src = ident.get("source") if isinstance(ident.get("source"), dict) else {}
        cid = ident.get("clause_id")
        ver = ident.get("version") or b.get("clause_version")
        loc = _text(src.get("locator")) or _text(b.get("locator"))
        obligation = b.get("obligation") if isinstance(b.get("obligation"), str) else None
        body = (
            _text(b.get("text"))
            or _text(obligation)
            or _text(src.get("quote"))
            or _text(b.get("quote"))
            or _text(ident.get("title"))
            or "(text available through policy.read)"
        )
        where = f" [{loc}]" if loc else ""
        lines.append(f"- Clause {cid} v{ver}{where}: {body}")
        for e in b.get("exceptions") or []:
            if isinstance(e, dict) and _text(e.get("text")):
                lines.append(f"   Exception: {_text(e['text'])}")
    return lines


def from_sections(sections):
    parts = []
    keys = [k for k in ORDER if k in sections] + sorted(k for k in sections if k not in ORDER)
    for key in keys:
        body = _section(key, sections[key])
        if body:
            parts.append(f"## {TITLES.get(key, key)}\n" + "\n".join(body))
    return "\n\n".join(parts)


def _kind(prop):
    t = prop.get("type")
    if prop.get("enum"):
        return None, "one of " + ", ".join(map(str, prop["enum"]))
    if t == "boolean":
        return "true or false", None
    if t == "array":
        return "a list", None
    if t == "object":
        return "an object", None
    return None, None


def output_fields(schema):
    """The template's output schema as the agent reads it: each field, whether it's required, its values or kind, its
    description, and the fields of each list item."""
    required = set(schema.get("required") or [])
    lines = []
    for name, prop in (schema.get("properties") or {}).items():
        if not isinstance(prop, dict):
            continue
        word, values = _kind(prop)
        flags = (["required"] if name in required else []) + ([word] if word else [])
        body = "; ".join(x for x in (values, _text(prop.get("description"))) if x)
        lines.append(
            f"- {name}"
            + (f" ({', '.join(flags)})" if flags else "")
            + (f": {body}" if body else "")
        )
        item = prop.get("items") if isinstance(prop.get("items"), dict) else None
        if item and item.get("properties"):
            req = set(item.get("required") or [])
            parts = [f"{k} (required)" if k in req else k for k in item["properties"]]
            lines.append("  each with: " + ", ".join(parts))
    return lines


def build(actor, clauses=None, output_schema=None):
    """{"text", "sha256", "source"} for the actor payload, or GymError TASK_NO_INSTRUCTIONS. `clauses`: the export's
    selected clause versions (E-002), added as a "Policy clauses" part; none → the text and hash are as before.
    `output_schema`: the template's (KYC Judgment C4), added as "Output fields"; none → as before."""
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
    s4 = (
        (actor.get("sections") or {}).get("S4") if isinstance(actor.get("sections"), dict) else None
    )
    already = isinstance(s4, dict) and bool(s4.get("policyBindings"))  # rendered inside S4 already
    extra = [] if already else clause_lines(clauses)
    if extra:
        text += "\n\n## Policy clauses\n" + "\n".join(extra)
    fields = output_fields(output_schema) if isinstance(output_schema, dict) else []
    if fields:
        text += "\n\n## Output fields\n" + "\n".join(fields)
    return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest(), "source": source}


def problem(actor):
    """None if the payload yields instructions, else the reason (for import and admission checks)."""
    try:
        build(actor)
        return None
    except GymError as exc:
        return exc.message
