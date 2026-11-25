"""KYC Judgment v1, RL Gym end to end without Studio: a fake kyc-judgment environment (a bulletin fires after the first
screening check), each agent's episode in the sealed-bundle shape, the judgment lines computed outside the sandbox,
and the real sandbox runner deciding each criterion. The reference agent passes everything; invents-evidence fails
evidence judgment critically; ignores-bulletins fails rules applied (missed bulletin, stale version); a bulletin-free
case makes the rule-in-force line not applicable."""

from test_rlgym_judgment_agents_unit import ACTOR, APP, REF, Env

from anvil.rlgym.catalog import judgment_configs
from anvil.rlgym.runs import events as scenario_log
from anvil.rlgym.runs import library
from anvil.rlgym.scoring import sandbox
from anvil.rlgym.scoring import service as scoring
from anvil.rlgym.systems import mock_provider
from anvil.rlgym.verification import reference

FRAMEWORK = {
    "id": "fw-python-1.0.0",
    "runtime_id": "python",
    "installed_locally": True,
    "state": "qualified",
}
ACC = {"fact": "process", "op": "eq", "value": "account_opening"}


def ver(n, cond, eff=None):
    t = f"text {n}"
    return {
        "version": n,
        "effective": eff or {"mode": "from_date", "from": "2026-01-01"},
        "effect": "obligation",
        "condition": cond,
        "text": t,
        "text_sha256": library.text_sha(t),
    }


LIB = {
    "derived_facts": [],
    "rules": [
        {"rule_id": "FED-ID", "subject": "party", "versions": [ver(1, ACC)]},
        {
            "rule_id": "GB-03",
            "subject": "party",
            "versions": [
                ver(1, {"all": [ACC, {"fact": "party_role", "op": "eq", "value": "minor"}]}),
                {
                    **ver(
                        2,
                        {"all": [ACC, {"fact": "party_role", "op": "eq", "value": "minor"}]},
                        {"mode": "scenario_only"},
                    ),
                    "supersedes": 1,
                },
            ],
        },
    ],
}
CASE = {
    "facts": {"process": "account_opening"},
    "parties": [
        {"party_id": "kj-1-p1", "facts": {"party_role": "primary"}},
        {"party_id": "kj-1-p2", "facts": {"party_role": "minor"}},
    ],
}


class JudgmentEnv(Env):
    def __init__(self, bulletin=True):
        super().__init__()
        self.bulletin, self.fired_at = bulletin, None

    def call(self, tool, args):
        obs = super().call(tool, args)
        if not self.bulletin:
            self.fired = False
        elif tool == "screening.check" and self.fired_at is None:
            self.fired_at = obs["sequence"]
        return obs

    def end(self):
        fired = (
            []
            if self.fired_at is None
            else [
                {
                    "rule_id": "GB-03",
                    "from_version": 1,
                    "to_version": 2,
                    "trigger_sequence": self.fired_at,
                    "published_at_sequence": self.fired_at,
                    "notice_id": "bulletin-0001",
                }
            ]
        )
        return {"scenario_events": fired}


def episode(gen, bulletin=True):
    env = JudgmentEnv(bulletin)
    action = next(gen)
    while "final" not in action:
        action = gen.send(env.call(action["tool"], action.get("args") or {}))
    snaps = {
        "start": {
            "applications": [{"application_id": APP, "submitted_at": "2026-10-15T00:00:00Z"}]
        },
        "end": env.end(),
    }
    return {
        "final_output": action["final"],
        "transcript": env.transcript,
        "snapshots": snaps,
        "scenario_events": scenario_log.scenario_events(snaps, env.transcript),
        "id_aliases": {"aliases": {}},
    }


def verdicts(bundle, ref=REF):
    manifest = {"judgment": {"library": LIB, "cases": {APP: CASE}}}
    configs = []
    for crit in judgment_configs.CHECKS:
        cfg = judgment_configs.config_for(
            crit, {"runner": "verifier_blocks", "runner_version": 1, "evidence": "snapshots"}
        )
        configs.append(({"criterion_id": crit}, {"config": cfg}))
    lines = scoring.judgment_results(manifest, {"case_id": APP}, bundle, ref, None, configs)
    out = sandbox.run_batch(
        FRAMEWORK,
        [row["config"] for _, row in configs],
        {"snapshots": bundle["snapshots"]},
        ref,
        extras=[
            {
                "blocks": [],
                "case_id": APP,
                "judgment_results": lines,
                "expected_values_from": "case_reference",
            }
            for _ in configs
        ],
    )
    return {ev["criterion_id"]: v for (ev, _), v in zip(configs, out, strict=True)}


REF_FULL = {
    **REF,
    "rules_applied": [
        {"rule_id": "GB-03", "version": 2, "party_ids": ["kj-1-p2"]},
        {"rule_id": "FED-ID", "version": 1, "party_ids": ["kj-1-p1", "kj-1-p2"]},
    ],
}


def test_the_reference_agent_passes_every_criterion():
    b = episode(reference.agent(ACTOR, REF_FULL, APP, []))
    got = verdicts(b, REF_FULL)
    assert {k: v["verdict"] for k, v in got.items()} == {
        "rules_applied": "pass",
        "decision_next_action": "pass",
        "evidence_judgment": "pass",
    }, got


def test_invented_evidence_fails_critically():
    b = episode(
        mock_provider.agent(
            "mock/judgment-invents-evidence-v1",
            None,
            "k",
            world="studio-openenv",
            application_id=APP,
        )
    )
    got = verdicts(b, REF_FULL)
    assert (
        got["evidence_judgment"]["verdict"] == "fail"
        and got["evidence_judgment"].get("critical") is True
    )


def test_a_missed_bulletin_fails_rules_applied():
    b = episode(
        mock_provider.agent(
            "mock/judgment-ignores-bulletins-v1",
            None,
            "k",
            world="studio-openenv",
            application_id=APP,
        )
    )
    got = verdicts(b, REF_FULL)
    assert got["rules_applied"]["verdict"] == "fail"
    line = next(
        ln
        for ln in got["rules_applied"]["block_lines"]
        if ln["block_id"] == "rules_applied.rule_in_force"
    )
    assert line["verdict"] == "fail" and line["actual"]["notices_missed"] == ["bulletin-0001"]


def test_without_a_bulletin_the_rule_in_force_line_is_not_applicable():
    ref = {
        **REF_FULL,
        "rules_applied": [
            {"rule_id": "GB-03", "version": 1, "party_ids": ["kj-1-p2"]},
            {"rule_id": "FED-ID", "version": 1, "party_ids": ["kj-1-p1", "kj-1-p2"]},
        ],
    }
    b = episode(reference.agent(ACTOR, ref, APP, []), bulletin=False)
    got = verdicts(b, ref)
    line = next(
        ln
        for ln in got["rules_applied"]["block_lines"]
        if ln["block_id"] == "rules_applied.rule_in_force"
    )
    assert line["verdict"] == "not_applicable" and got["rules_applied"]["verdict"] == "pass"
