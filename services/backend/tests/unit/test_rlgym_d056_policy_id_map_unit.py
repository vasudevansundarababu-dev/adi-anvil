"""D-056: Authoring's task entry may carry a policy_id_map from its rule ids to the environment's policy ids. At reset the
agent's view of S4 shows the environment's ids, only when the map's environment version and policy hashes match the
environment being run; the original ids stay in the evidence. Without a map nothing changes. Synthetic data only."""

import copy
import hashlib
import inspect

from anvil.rlgym.runs import instructions, policy_ids, worker

DOC = "54e00852-42c6-4f43-a7b9-732cf7fd0882"
ENV = "golden-kyc-openenv@12"
TEXTS = {
    "KYC-01": "Run identity.check for every party.",
    "KYC-02": "Each application needs proof of address.",
}
POLICIES = [{"rule_id": k, "title": k, "text": v, "source": "synthetic"} for k, v in TEXTS.items()]


def h(text):
    return hashlib.sha256(text.encode()).hexdigest()


ACTOR = {
    "sections": {
        "S1": {"title": "Review a KYC application"},
        "S4": {
            "statePolicies": [
                {
                    "ruleId": DOC,
                    "locator": "project rule set v2",
                    "ruleVersion": "rs2.d1",
                    "contentSha256": "a5c0aa26" + "0" * 56,
                }
            ]
        },
    }
}


def spec(**over):
    s = {
        "environment_version": ENV,
        "map": {DOC: ["KYC-01", "KYC-02"]},
        "policies": {k: {"content_sha256": h(v)} for k, v in TEXTS.items()},
    }
    s.update(over)
    return s


def test_no_map_changes_nothing():
    before = copy.deepcopy(ACTOR)
    shown, record = policy_ids.apply(ACTOR, None, ENV, POLICIES)
    assert shown is ACTOR and record is None and ACTOR == before


def test_a_matching_map_shows_the_environment_ids_and_keeps_the_original_for_audit():
    before = copy.deepcopy(ACTOR)
    shown, record = policy_ids.apply(ACTOR, spec(), ENV, POLICIES)
    assert ACTOR == before  # the frozen payload is never edited
    text = instructions.build(shown)["text"]
    assert "Rule KYC-01, KYC-02 (project rule set v2" in text and DOC not in text
    assert record["applied"] is True and record["warning"] is None
    assert record["environment_version"] == ENV
    assert record["rules"] == [{"original": DOC, "shown": ["KYC-01", "KYC-02"]}]


def test_a_different_environment_version_leaves_s4_and_warns():
    shown, record = policy_ids.apply(ACTOR, spec(), "golden-kyc-openenv@11", POLICIES)
    assert shown is ACTOR and record["applied"] is False
    assert (
        "golden-kyc-openenv@12" in record["warning"]
        and "golden-kyc-openenv@11" in record["warning"]
    )


def test_a_changed_policy_text_leaves_s4_and_warns():
    changed = [
        dict(p, text=p["text"] + " (edited)") if p["rule_id"] == "KYC-02" else p for p in POLICIES
    ]
    shown, record = policy_ids.apply(ACTOR, spec(), ENV, changed)
    assert shown is ACTOR and record["applied"] is False and "KYC-02" in record["warning"]


def test_a_policy_the_environment_does_not_have_leaves_s4_and_warns():
    shown, record = policy_ids.apply(ACTOR, spec(), ENV, POLICIES[:1])
    assert shown is ACTOR and record["applied"] is False and "KYC-02" in record["warning"]


def test_a_map_without_hashes_or_version_is_never_applied():
    for bad in (
        {DOC: ["KYC-01"]},  # the bare form: nothing to verify against
        spec(policies={}),
        spec(environment_version=None),
        spec(map={DOC: "KYC-01"}),
        "not a map",
    ):
        shown, record = policy_ids.apply(ACTOR, bad, ENV, POLICIES)
        assert shown is ACTOR and record["applied"] is False and record["warning"]


def test_unreadable_environment_policies_leave_s4_and_warn():
    shown, record = policy_ids.apply(ACTOR, spec(), ENV, None)
    assert shown is ACTOR and record["applied"] is False and "policies" in record["warning"]


def test_rules_the_map_does_not_name_stay_as_they_are():
    actor = copy.deepcopy(ACTOR)
    actor["sections"]["S4"]["statePolicies"].append({"ruleId": "other-rule", "locator": "x"})
    shown, record = policy_ids.apply(actor, spec(), ENV, POLICIES)
    text = instructions.build(shown)["text"]
    assert "Rule other-rule (x" in text and record["unmapped"] == ["other-rule"]


def test_the_row_hash_is_accepted_too():
    from anvil.rlgym.common import sha

    s = spec(policies={p["rule_id"]: {"content_sha256": sha(p)} for p in POLICIES})
    assert policy_ids.apply(ACTOR, s, ENV, POLICIES)[1]["applied"] is True


class Session:
    def __init__(self, policies):
        self.policies = policies

    def request(self, msg):
        if msg["op"] == "reset":
            return {"ok": True, "user_message": "Review the application."}
        if msg["op"] == "snapshot":
            return {"ok": True, "collections": {"policies": self.policies}}
        if msg["op"] == "call":
            raise RuntimeError("stop after reset")
        return {"ok": True}

    def close(self):
        pass


def _run(task):
    episode = {
        "id": "run-x-e0001",
        "run_id": "run-x",
        "workspace_id": "ws",
        "kind": "case",
        "task_id": "t1",
        "task_revision": 1,
        "case_id": "kyc-1",
        "attempt": 1,
        "tries": 1,
        "system_id": "mock-a",
        "ts_prompt_id": None,
    }
    manifest = {
        "manifest": {
            "tasks": [task],
            "models": [{"system_id": "mock-a", "model_id": "mock/erratic-v1"}],
            "environment": {"version_id": ENV},
            "execution_mode": "mock",
            "note": "test",
        },
        "manifest_sha256": "0" * 64,
    }
    instance = {"env": {"schema": {"collections": [{"name": "policies"}]}}, "container": "c"}
    try:
        worker.execute(
            episode,
            {"episode_timeout_s": 60},
            manifest,
            instance,
            ACTOR,
            session_factory=lambda: Session(POLICIES),
        )
    except RuntimeError as exc:
        return exc.partial
    raise AssertionError("expected the fake session to stop the episode")


def test_the_worker_applies_the_map_at_reset_and_records_it():
    partial = _run({"task_id": "t1", "revision": 1, "policy_id_map": spec()})
    record = partial["policy_id_map"]
    assert record["applied"] is True and record["rules"][0]["original"] == DOC
    shown = record["instructions_sha256"]
    assert shown["original"] == instructions.build(ACTOR)["sha256"] != shown["shown"]


def test_the_worker_without_a_map_records_nothing():
    partial = _run({"task_id": "t1", "revision": 1})
    assert "policy_id_map" not in partial


def test_import_keeps_the_map_and_the_manifest_freezes_it():
    from anvil.rlgym.projects import service as projects
    from anvil.rlgym.runs import service as runs

    assert 'task.get("policy_id_map")' in inspect.getsource(projects)
    assert '"policy_id_map": t["policy_id_map"]' in inspect.getsource(runs._manifest)
