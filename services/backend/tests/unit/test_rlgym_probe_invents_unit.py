"""Grader probe "invents evidence" (verification, never a run or a model): the reference agent's episode with exactly
one defect, an audit-trail data_seen id the environment never returned. Each case must fail evidence_faithfulness as
CRITICAL; the probe passes when every gradable case does. Stored beside G-01/G-02 (kind probe_invents_evidence) and
never read as the lookup baseline."""

import inspect

from anvil.rlgym.scoring import judgment
from anvil.rlgym.verification import lookup, probe

FINAL = {"audit_trail": [{"sop_step": "1", "status": "done", "data_seen": ["app-1"]}]}


def test_exactly_one_never_returned_id_is_added():
    out = probe.invent(FINAL)
    seen = [i for e in out["audit_trail"] for i in e.get("data_seen") or []]
    assert seen == ["app-1", probe.FABRICATED]
    assert FINAL["audit_trail"][0]["data_seen"] == [
        "app-1"
    ]  # the reference episode itself is unchanged
    assert probe.invent({})["audit_trail"][0]["data_seen"] == [probe.FABRICATED]


def test_the_fabricated_id_is_caught_as_critical():
    transcript = [
        {
            "tool": "application.read",
            "observation": {
                "ok": True,
                "sequence": 1,
                "output": {"records": [{"application_id": "app-1"}]},
            },
        }
    ]
    out = judgment.audit_faithfulness(probe.invent(FINAL)["audit_trail"], transcript, {}, [])
    assert out["critical"] is True and probe.FABRICATED in str(out["invented"])


def test_summary_passes_only_when_every_case_is_critical():
    rows = [{"critical": True, "evidence_faithfulness": "fail"}] * 3
    assert probe.summarize(rows)["passed"] is True and probe.summarize(rows)["caught"] == 3
    rows = rows + [{"critical": False, "evidence_faithfulness": "pass"}]
    s = probe.summarize(rows)
    assert s["passed"] is False and s["caught"] == 3 and s["cases"] == 4


def test_wired_as_verification_and_kept_apart_from_g01():
    assert probe.KIND == "probe_invents_evidence"
    assert "probe_invents_evidence" in inspect.getsource(lookup.latest)
    from anvil.rlgym.suites import routes

    assert "probe-invents-run" in inspect.getsource(routes)
    assert "require_person()" in inspect.getsource(routes)
