"""Opaque IDs for the agent (owner decision 24 Nov 2026: "RL Gym hides IDs today"; Studio's D-039 audit).

On golden-kyc-openenv @6-@8 a case's IDs name its edge case (kyc-teen-joint-minor-without-tin-001, and the party and
document IDs built on it), so an agent could read the answer off an ID. Between the agent and the environment, the
RL Gym replaces every case, application, party and document ID in what the agent receives with an opaque alias, and maps
the agent's arguments (and its final answer) back before the environment or a grader sees them.

- Per episode, random (the agent can't learn a mapping across episodes); within an episode the same ID always gets the
  same alias. Aliases carry no words: APP-, PTY-, DOC- or ID- and 8 hex characters.
- The environment's data is never changed. Graders, the trace, the report and SME review use real IDs; the episode's
  sealed bundle keeps the alias table so what the agent saw can be reconstructed.
- Also replaced inside longer strings, such as a file name that embeds an ID, and any token built on the case ID.
"""

import re
import secrets

VERSION = "rlgym-id-alias@1"
PREFIX = {"applications": "APP", "parties": "PTY", "documents": "DOC"}
ID_KEYS = {
    "applications": ("application_id",),
    "parties": ("party_id",),
    "documents": ("document_id",),
}


class Aliaser:
    def __init__(self, case_id, start=None, token=None):
        self.case_id = case_id
        self._token = token or (lambda: secrets.token_hex(4).upper())
        self.forward, self.back_map = {}, {}
        self._add(case_id, "APP")
        start = start or {}
        # Every application, party and document in the environment, not only this case's: a list call can return
        # other cases' records, and their IDs name their edge cases too. This case's first, so its aliases are stable.
        tables = [(t, k, PREFIX[t]) for t, keys in ID_KEYS.items() for k in keys]
        mine = {case_id}
        for p in start.get("parties") or []:
            if isinstance(p, dict) and p.get("application_id") == case_id:
                mine.add(p.get("party_id"))
        for table, key, prefix in tables:
            rows = [r for r in start.get(table) or [] if isinstance(r, dict)]
            rows.sort(
                key=lambda r: (
                    r.get(key) not in mine and r.get("party_id") not in mine,
                    str(r.get(key)),
                )
            )
            for r in rows:
                self._add(r.get(key), prefix)
        # Any other token built on the case ID (e.g. a derived id or a file name) is aliased when first seen.
        self._derived = re.compile(re.escape(case_id) + r"[A-Za-z0-9-]*") if case_id else None
        self._compile()

    def _add(self, real, prefix):
        if not isinstance(real, str) or not real or real in self.forward:
            return
        alias = f"{prefix}-{self._token()}"
        while alias in self.back_map:
            alias = f"{prefix}-{self._token()}"
        self.forward[real] = alias
        self.back_map[alias] = real

    def _compile(self):
        reals = sorted(self.forward, key=len, reverse=True)
        # Whole IDs only ("doc-1" never inside "doc-12"); an ID may sit inside a file name ("<id>_passport.pdf").
        self._fwd = (
            re.compile(
                r"(?<![A-Za-z0-9-])(?:"
                + "|".join(re.escape(r) for r in reals)
                + r")(?![A-Za-z0-9-])"
            )
            if reals
            else None
        )
        aliases = sorted(self.back_map, key=len, reverse=True)
        self._bwd = re.compile("|".join(re.escape(a) for a in aliases)) if aliases else None

    def _out_str(self, s):
        if self._derived:
            new = [tok for tok in set(self._derived.findall(s)) if tok not in self.forward]
            for tok in new:
                self._add(tok, "ID")
            if new:
                self._compile()
        return self._fwd.sub(lambda m: self.forward[m.group(0)], s) if self._fwd else s

    def _back_str(self, s):
        return self._bwd.sub(lambda m: self.back_map[m.group(0)], s) if self._bwd else s

    def _walk(self, value, fn):
        if isinstance(value, str):
            return fn(value)
        if isinstance(value, dict):
            return {
                (fn(k) if isinstance(k, str) else k): self._walk(v, fn) for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._walk(v, fn) for v in value]
        return value

    def out(self, value):
        """What the agent receives: real IDs → aliases (the environment's own value is not changed)."""
        return self._walk(value, self._out_str)

    def back(self, value):
        """What the agent sends: aliases → real IDs, before the environment or a grader sees it."""
        return self._walk(value, self._back_str)

    def record(self):
        return {"version": VERSION, "aliases": dict(self.forward)}
