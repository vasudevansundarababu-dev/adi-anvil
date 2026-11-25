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
    assert final["risk_rating"] == {"required": True, "level": "low", "factors": []}
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


def test_the_reference_agent_uses_the_identity_method_the_reference_names():
    actor = {
        "sections": {
            **ACTOR["sections"],
            "S5": {
                "steps": [
                    {"tool": t}
                    for t in ("application.read", "documents.list", "identity.check", "recommend")
                ]
            },
        }
    }
    actor["sections"]["S3"] = {"tools": [*ACTOR["sections"]["S3"]["tools"], "identity.check"]}
    ref = {**REF, "identity_methods": {"kj-1-p1": "non_documentary"}}
    final, env = drive(reference.agent(actor, ref, APP, []))
    calls = {
        t["args"]["party_id"]: t["args"].get("method")
        for t in env.transcript
        if t["tool"] == "identity.check"
    }
    assert calls == {"kj-1-p1": "non_documentary", "kj-1-p2": None}
    # The new request type and referral specialty pass through as the reference names them.
    ref2 = {
        **REF,
        "parties": [
            {
                "party_id": "kj-1-p1",
                "outcome": "specialist_review",
                "requests": ["identification_number"],
                "referral": "edd",
            },
            {"party_id": "kj-1-p2", "outcome": "clear", "requests": [], "referral": None},
        ],
    }
    final, env = drive(reference.agent(ACTOR, ref2, APP, []))
    assert [t["args"]["type"] for t in env.transcript if t["tool"] == "information.request"] == [
        "identification_number"
    ]
    assert [t["args"]["specialty"] for t in env.transcript if t["tool"] == "specialist.refer"] == [
        "edd"
    ]


# --- run-0238 (test@3, generator 2.7.0): recommend was refused (policy_bundle is the const kyc-judgment.library@1),
# the rationale named no decision, and the audit trail had one step ------------------------------------------------

OPS = [
    {
        "operation_id": "recommend",
        "input_schema": {
            "properties": {"policy_bundle": {"type": "string", "const": "kyc-judgment.library@1"}}
        },
    }
]
STEPS = (
    "## Steps\n1. Read the assigned application. (record with application.read)\n"
    "2. List the parties of the application. (record with parties.list)\n"
    "3. Read the published policy library. (record with policy.read)\n"
    "4. Read any policy notices. (record with notices.read)\n"
    "5. List the documents. (record with documents.list)\n"
    "11. Screen every party. (record with screening.check)\n"
    "15. Record the recommendation. (record with recommend)\n"
)


def drive_with_ops(model):
    env = Env()
    gen = mock_provider.agent(
        model, STEPS, "k", world="studio-openenv", application_id=APP, operations=OPS
    )
    action, calls = next(gen), []
    for _ in range(300):
        if "final" in action:
            return action["final"], calls
        calls.append(action)
        action = gen.send(env.call(action["tool"], action.get("args") or {}))
    raise AssertionError("no final")


def test_recommend_uses_the_offered_policy_bundle():
    _, calls = drive_with_ops("mock/judgment-diligent-v1")
    rec = next(a for a in calls if a["tool"] == "recommend")
    assert rec["args"]["policy_bundle"] == "kyc-judgment.library@1"


def test_without_a_schema_the_old_bundle_stays():
    final, env = drive(
        mock_provider.agent(
            "mock/judgment-diligent-v1", None, "k", world="studio-openenv", application_id=APP
        )
    )
    rec = next(t for t in env.transcript if t["tool"] == "recommend")
    assert rec["args"]["policy_bundle"] == mock_provider.POLICY_BUNDLE


def test_the_rationale_names_the_decision_and_a_rule():
    final, _ = drive_with_ops("mock/judgment-diligent-v1")
    x = {"final": final, "reference": {"status": "complete", "gradable": True}}
    assert judgment.evaluate("rationale", x)["verdict"] == "pass"


def test_the_audit_trail_numbers_the_task_steps_it_performed():
    final, calls = drive_with_ops("mock/judgment-diligent-v1")
    steps = [e["sop_step"] for e in final["audit_trail"]]
    assert steps[:5] == ["1", "2", "3", "4", "5"] and "11" in steps and steps[-1] == "15"
    assert {e["status"] for e in final["audit_trail"]} == {"done"}
    # ignores-bulletins never read notices: no step 4.
    final, _ = drive_with_ops("mock/judgment-ignores-bulletins-v1")
    assert "4" not in [e["sop_step"] for e in final["audit_trail"]]


def test_the_trail_stays_faithful_and_invents_evidence_still_is_caught():
    final, calls = drive_with_ops("mock/judgment-diligent-v1")
    env = Env()
    for a in calls:
        env.call(a["tool"], a.get("args") or {})
    assert (
        judgment.audit_faithfulness(final["audit_trail"], env.transcript, {}, [])["critical"]
        is False
    )
    final, calls = drive_with_ops("mock/judgment-invents-evidence-v1")
    env = Env()
    for a in calls:
        env.call(a["tool"], a.get("args") or {})
    assert (
        judgment.audit_faithfulness(final["audit_trail"], env.transcript, {}, [])["critical"]
        is True
    )
