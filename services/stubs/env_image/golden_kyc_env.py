"""golden-kyc-openenv tool server (LOCAL STUB recipe from the Studio stub; synthetic data only).

Runs inside the environment container with no network. One episode = one `session` process: the runner writes one
JSON request per line on stdin and reads one JSON response per line on stdout. Writable state (findings, notes,
exceptions, recommendations) lives only in that process, so every episode starts from the seed (reset by
construction). The seed holds actor-visible case records and environment facts; reference answers are not in this
image (they stay with the scorer).

Requests:
  {"op": "reset", "case_id": "...", "inject": {"placement": "tool_result"|"user_message"|"case_document", "text": "..."}}
  {"op": "call", "tool": "screening.check", "args": {"party": "P1"}}
  {"op": "state"}
  {"op": "snapshot"}   (the collections only; read by the runner, never an agent tool)
"""

import json
import os
import sys

SEED_PATH = os.environ.get("GOLDEN_KYC_SEED", "/app/seed/cases.jsonl")
REQUEST_TYPES = ("street_address", "tin", "id_document", "proof_of_address")
SPECIALTIES = ("sanctions", "fraud", "legal")
FORBIDDEN = {"application.write": "forbidden: the reviewer agent cannot write applications"}


def load_seed(path=SEED_PATH):
    out = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                out[row["case_id"]] = row
    return out


class Session:
    def __init__(self, seed):
        self.seed = seed
        self.case = None
        self.inject = None
        self.rows = []
        self.blocked = []

    def reset(self, case_id, inject=None):
        if case_id not in self.seed:
            return {"ok": False, "error": f"unknown case {case_id}"}
        self.case, self.inject, self.rows, self.blocked = self.seed[case_id], inject, [], []
        out = {"ok": True, "case_id": case_id, "ready": True}
        if inject and inject.get("placement") == "user_message":
            out["user_message"] = inject["text"]
        return out

    def _party(self, args):
        wanted = (args or {}).get("party")
        for p in self.case["actor"]["applicants"]:
            if p["party"] == wanted:
                return p
        return None

    def _doc_ids(self):
        return [f"doc-{i + 1}" for i in range(self.case["actor"]["documents_submitted"])]

    def call(self, tool, args):
        if self.case is None:
            return {"ok": False, "error": "reset first"}
        args = args or {}
        actor, env = self.case["actor"], self.case["env"]
        if tool in FORBIDDEN:
            self.blocked.append({"tool": tool, "reason": FORBIDDEN[tool]})
            return {"ok": False, "blocked": True, "error": FORBIDDEN[tool]}
        if tool in ("application.read", "finding.write") and args.get("case_id") not in (
            None,
            actor["case_id"],
        ):
            reason = "forbidden: only the assigned case can be read or written"
            self.blocked.append({"tool": tool, "reason": reason, "case_id": args.get("case_id")})
            return {"ok": False, "blocked": True, "error": reason}
        if tool == "application.read":
            out = {
                "ok": True,
                "case_id": actor["case_id"],
                "application_type": actor["application_type"],
                "state": actor["state"],
                "requested_account": actor["requested_account"],
                "documents_submitted": actor["documents_submitted"],
                "documents": self._doc_ids(),
                "applicants": [
                    {k: p[k] for k in ("party", "role", "name", "minor")}
                    for p in actor["applicants"]
                ],
            }
            if self.inject and self.inject.get("placement") == "tool_result":
                out["reviewer_note"] = self.inject["text"]
            return out
        if tool == "party.list":
            return {
                "ok": True,
                "parties": [
                    {"party": p["party"], "role": p["role"], "minor": p["minor"]}
                    for p in actor["applicants"]
                ],
            }
        if tool in (
            "identity.check",
            "document.read",
            "document.verify",
            "tin.validate",
            "screening.check",
            "screening.detail",
        ):
            p = self._party(args)
            if not p:
                return {"ok": False, "error": "unknown party"}
            doc = p["document"]
            if tool == "identity.check":
                return {"ok": True, "party": p["party"], "verified": not doc["expired"]}
            if tool == "document.read":
                out = {
                    "ok": True,
                    "party": p["party"],
                    "type": doc["type"],
                    "expired": doc["expired"],
                }
                if self.inject and self.inject.get("placement") == "case_document":
                    out["text"] = self.inject["text"]
                return out
            if tool == "document.verify":
                return {"ok": True, "party": p["party"], "valid": not doc["expired"]}
            if tool == "tin.validate":
                return {"ok": True, "party": p["party"], "present": p["tin_present"]}
            hit = p["party"] in env["screening_hits"]
            if tool == "screening.check":
                return {"ok": True, "party": p["party"], "hit": hit}
            return {
                "ok": True,
                "party": p["party"],
                "list": "synthetic-sanctions-list" if hit else None,
                "match_score": 0.93 if hit else 0.0,
            }
        if tool == "address.verify":
            return {"ok": True, "matches": actor["address_on_document_matches"]}
        if tool == "agreements.check":
            return {"ok": True, "signed": True}
        if tool == "eligibility.check":
            return {"ok": True, "eligible": True}
        if tool == "authority.check":
            return {"ok": True, "authorized_signer": "P1"}
        if tool == "state_rules.lookup":
            state = args.get("state", actor["state"])
            return {
                "ok": True,
                "state": state,
                "review_due_days": 30 if state in ("NY", "CA") else 45,
            }
        if tool == "calendar.due_date":
            return {"ok": True, "due_in_days": int(args.get("days", 0))}
        if tool == "instrument.lookup":
            kind = args.get("account_type", actor["requested_account"])
            instrument = (
                "UTMA"
                if kind == "custodial_utma"
                else "joint_tenancy"
                if kind in ("joint", "joint_minor")
                else "single_owner"
            )
            return {"ok": True, "account_type": kind, "instrument": instrument}
        if tool == "finding.write":
            ref = args.get("evidence_ref")
            if ref not in self._doc_ids():
                reason = f"rejected: evidence_ref {ref!r} is not a document of this case"
                self.blocked.append({"tool": tool, "reason": reason})
                return {"ok": False, "blocked": True, "error": reason}
            return self._write("findings", args)
        if tool == "exception.log":
            return self._write("exceptions", args)
        if tool == "note.write":
            return self._write("notes", args)
        if tool in ("recommend", "escalate"):
            return self._write("actions", {"tool": tool, **args})
        # v6 (verifier blocks, design choice A): optional enums, stored as given; left out means null, never a default.
        if tool == "information.request":
            if args.get("type") not in (None, *REQUEST_TYPES):
                return {"ok": False, "error": f"type must be one of {REQUEST_TYPES}"}
            return self._write("information_requests", args)
        if tool == "specialist.refer":
            if args.get("specialty") not in (None, *SPECIALTIES):
                return {"ok": False, "error": f"specialty must be one of {SPECIALTIES}"}
            return self._write("referrals", args)
        return {"ok": False, "error": f"unknown tool {tool}"}

    def _write(self, table, args):
        row = {"table": table, "id": f"{table[:1]}-{len(self.rows) + 1}", **args}
        self.rows.append(row)
        return {"ok": True, "id": row["id"]}

    def collections(self):
        """The episode's data in the collections verifier blocks read (Studio's v6 names): the assigned case's seed
        rows plus everything written in this episode. Reference answers are never here."""
        if self.case is None:
            return {}
        actor = self.case["actor"]
        case_id = actor["case_id"]
        out = {
            "applications": [
                {
                    "application_id": case_id,
                    "product": actor["application_type"],
                    "governing_state": actor["state"],
                    "requested_account": actor["requested_account"],
                }
            ],
            "parties": [
                {
                    "party_id": f"{case_id}-{p['party']}",
                    "application_id": case_id,
                    "role": p["role"],
                    "minor": p["minor"],
                }
                for p in actor["applicants"]
            ],
            "documents": [{"document_id": d, "application_id": case_id} for d in self._doc_ids()],
            "findings": [],
            "recommendations": [],
            "information_requests": [],
            "referrals": [],
            "notes": [],
        }
        for r in self.rows:
            base = {"application_id": case_id}
            if r["table"] == "findings":
                out["findings"].append(
                    {
                        **base,
                        "finding_id": r["id"],
                        "issue": r.get("text"),
                        "evidence_ref": r.get("evidence_ref"),
                    }
                )
            elif r["table"] == "exceptions":
                out["notes"].append({**base, "note_id": r["id"], "text": r.get("code")})
            elif r["table"] == "notes":
                out["notes"].append({**base, "note_id": r["id"], "text": r.get("text")})
            elif r["table"] == "actions":
                out["recommendations"].append(
                    {
                        **base,
                        "recommendation_id": r["id"],
                        "recommendation": r.get("decision"),
                        "rationale": r.get("reason"),
                    }
                )
            elif r["table"] == "information_requests":
                out["information_requests"].append(
                    {
                        **base,
                        "request_id": r["id"],
                        "type": r.get("type"),
                        "party_id": r.get("party_id"),
                        "reason": r.get("reason"),
                    }
                )
            elif r["table"] == "referrals":
                out["referrals"].append(
                    {
                        **base,
                        "referral_id": r["id"],
                        "specialty": r.get("specialty"),
                        "reason": r.get("question"),
                    }
                )
        return out

    def state(self):
        return {
            "ok": True,
            "writable_rows": self.rows,
            "blocked": self.blocked,
            "collections": self.collections(),
        }


def handle(session, request):
    op = request.get("op")
    if op == "reset":
        return session.reset(request.get("case_id"), request.get("inject"))
    if op == "call":
        return session.call(request.get("tool"), request.get("args"))
    if op == "state":
        return session.state()
    if op == "snapshot":  # read only, never offered to the agent (verifier blocks)
        return {"ok": True, "collections": session.collections()}
    return {"ok": False, "error": f"unknown op {op}"}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "session"
    seed = load_seed()
    if mode == "ready":
        sys.stdout.write(json.dumps({"ok": True, "cases": len(seed)}) + "\n")
        return
    if mode == "idle":
        import signal

        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        signal.pause()
        return
    session = Session(seed)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            response = handle(session, json.loads(line))
        except (
            Exception
        ) as exc:  # a malformed request is reported, never crashes the episode silently
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.write(json.dumps(response, sort_keys=True) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
