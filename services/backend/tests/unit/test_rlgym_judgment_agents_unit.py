"""KYC Judgment v1 agents for the $0 integration run:
- the reference agent produces the Judgment output from reference.v2 (per-party requests and referrals, rules applied
  with governs, notices considered, a faithful audit trail, risk rating and officer flag) and reads notices before
  recommending, so every check passes on it;
- three controlled-mock profiles exercise the graders: diligent, invents-evidence (a critical fail) and
  ignores-bulletins (a missed bulletin). Mock answers never count as model performance."""

from anvil.rlgym.scoring import judgment
from anvil.rlgym.systems import mock_provider
from anvil.rlgym.verification import reference

APP = "kj-1"
PARTIES = [
    {"party_id": "kj-1-p1", "application_id": APP, "role": "primary"},
    {"party_id": "kj-1-p2", "application_id": APP, "role": "minor"},
]
DOCS = {
    "kj-1-p1": [
        {
            "document_id": "kj-1-p1-gov",
            "party_id": "kj-1-p1",
            "kind": "government_id",
            "content": {"name_on_document": "A"},
        }
    ],
    "kj-1-p2": [
        {
            "document_id": "kj-1-p2-gov",
            "party_id": "kj-1-p2",
            "kind": "government_id",
            "content": {"tin": "missing"},
        }
    ],
}
POLICIES_V1 = [
    {"rule_id": "GB-03", "version": 1, "text": "v1"},
    {"rule_id": "FED-ID", "version": 1, "text": "f"},
]
POLICIES_V2 = [
    {"rule_id": "GB-03", "version": 2, "text": "v2"},
    {"rule_id": "FED-ID", "version": 1, "text": "f"},
]


class Env:
    """A tiny fake of the kyc-judgment environment: the bulletin fires after the first screening.check."""

    def __init__(self):
        self.seq, self.fired, self.transcript = 0, False, []

    def call(self, tool, args):
        self.seq += 1
        recs = []
        if tool == "application.read":
            recs = [
                {
                    "application_id": APP,
                    "revision": 1,
                    "submitted_at": "2026-10-15T00:00:00Z",
                    "product": "teen_joint",
                }
            ]
        elif tool == "parties.list":
            recs = PARTIES
        elif tool == "documents.list":
            recs = DOCS.get(args.get("party_id"), [])
        elif tool == "policy.read":
            recs = POLICIES_V2 if self.fired else POLICIES_V1
        elif tool == "notices.read":
            recs = (
                [{"notice_id": "bulletin-0001", "source": "policy_service"}] if self.fired else []
            )
        if tool == "screening.check":
            self.fired = True
        obs = {"ok": True, "sequence": self.seq, "output": {"records": recs}}
        self.transcript.append({"step": self.seq, "tool": tool, "args": args, "observation": obs})
        return obs


def drive(gen):
    env = Env()
    action = next(gen)
    for _ in range(300):
        if "final" in action:
            return action["final"], env
        action = gen.send(env.call(action["tool"], action.get("args") or {}))
    raise AssertionError("no final")


def test_the_judgment_mock_profiles_exist():
    for p in (
        "mock/judgment-diligent-v1",
        "mock/judgment-invents-evidence-v1",
        "mock/judgment-ignores-bulletins-v1",
    ):
        assert p in mock_provider.PROFILES


def test_diligent_reads_notices_and_writes_a_faithful_trail():
    final, env = drive(
        mock_provider.agent(
            "mock/judgment-diligent-v1", None, "k", world="studio-openenv", application_id=APP
        )
    )
    assert final["notices_considered"] == ["bulletin-0001"]
    assert {"rule_id": "GB-03", "version": 2} in [
        {k: r[k] for k in ("rule_id", "version")} for r in final["rules_applied"]
    ]
    assert {a["party_id"] for a in final["assessments"]} == {"kj-1-p1", "kj-1-p2"}
    out = judgment.audit_faithfulness(final["audit_trail"], env.transcript, {}, [])
    assert out["critical"] is False and out["invented"] == []


def test_invents_evidence_is_caught_as_critical():
    final, env = drive(
        mock_provider.agent(
            "mock/judgment-invents-evidence-v1",
            None,
            "k",
            world="studio-openenv",
            application_id=APP,
        )
    )
    out = judgment.audit_faithfulness(final["audit_trail"], env.transcript, {}, [])
    assert out["critical"] is True


def test_ignores_bulletins_misses_the_notice_and_cites_the_old_version():
    final, env = drive(
        mock_provider.agent(
            "mock/judgment-ignores-bulletins-v1",
            None,
            "k",
            world="studio-openenv",
            application_id=APP,
        )
    )
    assert final["notices_considered"] == []
    assert {"rule_id": "GB-03", "version": 1} in [
        {k: r[k] for k in ("rule_id", "version")} for r in final["rules_applied"]
    ]
    assert "notices.read" not in [t["tool"] for t in env.transcript]


REF = {
    "recommendation": "request_information",
    "officer_verification": False,
    "risk_rating": {"required": True, "level": "low"},
    "parties": [
        {"party_id": "kj-1-p1", "outcome": "clear", "requests": [], "referral": None},
        {
            "party_id": "kj-1-p2",
            "outcome": "request_information",
            "requests": ["tin"],
            "referral": None,
        },
    ],
    "rules_applied": [
        {"rule_id": "GB-03", "version": 2, "party_ids": ["kj-1-p2"]},
        {"rule_id": "FED-ID", "version": 1, "party_ids": ["kj-1-p1", "kj-1-p2"]},
    ],
}
ACTOR = {
    "sections": {
        "S3": {
            "tools": [
                "application.read",
                "parties.list",
                "documents.list",
                "document.read",
                "policy.read",
                "notices.read",
                "screening.check",
                "information.request",
                "specialist.refer",
                "recommend",
            ]
        },
        "S5": {
            "steps": [
                {"tool": t}
                for t in (
                    "application.read",
                    "policy.read",
                    "documents.list",
                    "document.read",
                    "screening.check",
                    "recommend",
                )
            ]
        },
    }
}


def test_the_reference_agent_produces_the_judgment_output_from_reference_v2():
    failures = []
    final, env = drive(reference.agent(ACTOR, REF, APP, failures))
    tools = [t["tool"] for t in env.transcript]
    assert tools.index("notices.read") < tools.index("recommend")
    asked = [t["args"] for t in env.transcript if t["tool"] == "information.request"]
    assert [(a["party_id"], a["type"]) for a in asked] == [("kj-1-p2", "tin")]
    assert (
        final["recommendation"] == "request_information" and final["officer_verification"] is False
    )
    assert final["risk_rating"] == {"level": "low"}
    assert final["notices_considered"] == ["bulletin-0001"]
    assert [(r["rule_id"], r["version"]) for r in final["rules_applied"]] == [
        ("GB-03", 2),
        ("FED-ID", 1),
    ]
    x = {
        "final": final,
        "reference": REF,
        "aliases": {},
        "transcript": env.transcript,
        "fired": [
            {
                "rule_id": "GB-03",
                "to_version": 2,
                "published_at_sequence": 3,
                "notice_id": "bulletin-0001",
            }
        ],
    }
    for name in ("decision", "risk_rating", "rule_in_force", "audit_faithfulness"):
        assert judgment.evaluate(name, x)["verdict"] == "pass", name
