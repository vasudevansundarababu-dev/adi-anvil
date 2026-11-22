"""Verifier plug-ins (D22, work package 2.14): the contract round trip, manifest and settings checks, RFC 8785 hashes,
the runner's exit-code handling (a fake Docker), and plug-in lines inside the verifier-blocks sandbox. No Docker."""

import json
import subprocess
import sys

import pytest

from anvil.config import ROOT
from anvil.rlgym.common import GymError
from anvil.rlgym.plugins import contract, runner
from anvil.rlgym.scoring import sandbox_runner as sr

sys.path.insert(0, str(ROOT / "services/stubs"))
import golden_kyc as g  # noqa: E402

MANIFEST = json.loads((ROOT / "services/plugins/gorules-zen/manifest.json").read_text())
MANIFEST = {**MANIFEST, "image": "sha256:" + "d" * 64}
JOB = MANIFEST["known_cases"][0]["job"]


def test_the_zen_manifest_is_valid_and_its_known_cases_cover_pass_fail_blocked():
    contract.check_manifest(MANIFEST)
    assert [c["expect"] for c in MANIFEST["known_cases"]] == ["pass", "fail", "blocked"]
    assert MANIFEST["upstream"] == {
        "package": "zen-engine",
        "version": "2.1.3",
        "wheel": "zen_engine-2.1.3-cp38-abi3-manylinux_2_28_aarch64.whl",
        "sha256": "6fce1a4ce5482bb17c1eb4f19f6a8c6aaa2caea2640388bd2a42ccf1ff846384",
    }
    for bad in (
        {"image": "rlgym-local/verifier-gorules-zen:latest"},
        {"known_cases": MANIFEST["known_cases"][:2]},
        {"reads": ["network"]},
    ):
        with pytest.raises(GymError):
            contract.check_manifest({**MANIFEST, **bad})


def test_settings_are_checked_against_the_plugins_schema():
    schema = MANIFEST["settings_schema"]
    ok = JOB["blocks"][0]["settings"]
    assert contract.schema_errors(schema, ok) == []
    errors = contract.schema_errors(
        schema, {"mode": "guess", "rules": {"ref": "x"}, "inputs": {"a": 3}}
    )
    assert "settings.mode: must be one of ['oracle', 'rule_check']" in errors
    assert "settings.rules.sha256: required" in errors
    assert "settings.inputs.a: expected string" in errors


def test_rfc8785_hash_of_the_stub_rules_file():
    # The stub hashes with sorted compact JSON; for this file (ASCII keys, no floats) that equals RFC 8785.
    assert contract.jcs_sha256(g.ZEN_RULES) == g.ZEN_RULES_SHA256
    assert contract.jcs({"b": 1.0, "a": [1e21, 1e-7, "é"]}) == '{"a":[1e+21,1e-7,"é"],"b":1}'


def fake(*answers):
    calls = []

    def invoke(args, payload, timeout):
        calls.append((args, json.loads(payload)))
        a = answers[min(len(calls), len(answers)) - 1]
        if isinstance(a, Exception):
            raise a
        return a

    return invoke, calls


def result(job, verdict="pass"):
    return json.dumps(
        {
            "schema": contract.RESULT,
            "results": [{"block_id": b["id"], "verdict": verdict} for b in job["blocks"]],
        }
    ).encode()


def test_runner_runs_with_no_network_read_only_non_root_and_limits():
    invoke, calls = fake((0, result(JOB), b""))
    out = runner.run(MANIFEST, JOB, invoke=invoke)
    assert out["results"][0]["verdict"] == "pass"
    args = calls[0][0]
    for flag in (
        ["--network", "none"],
        ["--read-only"],
        ["--cap-drop", "ALL"],
        ["--user", "10001:10001"],
        ["--pids-limit", "64"],
    ):
        i = args.index(flag[0])
        assert args[i : i + len(flag)] == flag
    assert calls[0][1] == JOB  # the job on stdin, unchanged


def test_exit_2_blocks_every_block_with_the_error():
    invoke, calls = fake((2, b"", b"bad job: KeyError"))
    out = runner.run(MANIFEST, JOB, invoke=invoke)
    assert len(calls) == 1 and out["results"][0]["verdict"] == "blocked"
    assert "bad job" in out["results"][0]["detail"]


def test_other_exits_and_timeouts_retry_once_then_block():
    invoke, calls = fake((1, b"", b"segfault"), (0, result(JOB, "fail"), b""))
    assert runner.run(MANIFEST, JOB, invoke=invoke)["results"][0]["verdict"] == "fail"
    assert len(calls) == 2
    invoke, calls = fake(subprocess.TimeoutExpired("docker", 20))
    out = runner.run(MANIFEST, JOB, invoke=invoke)
    assert (
        len(calls) == 2
        and out["results"][0]["verdict"] == "blocked"
        and "limit" in out["results"][0]["detail"]
    )


def test_a_malformed_or_partial_result_is_never_a_pass():
    for bad in (b"not json", json.dumps({"schema": contract.RESULT, "results": []}).encode()):
        invoke, _ = fake((0, bad, b""))
        assert runner.run(MANIFEST, JOB, invoke=invoke)["results"][0]["verdict"] == "blocked"


def test_a_model_calling_plugin_is_refused_until_the_gateway_network_exists():
    invoke, calls = fake((0, result(JOB), b""))
    out = runner.run({**MANIFEST, "calls_model": True}, JOB, invoke=invoke)
    assert not calls and out["results"][0]["verdict"] == "blocked"


def test_plugin_lines_gate_the_criterion_in_the_sandbox():
    zen = {**g.ZEN_BLOCK}
    status = {
        "id": "s",
        "kind": "state",
        "table": "recommendations",
        "row": "any",
        "column": "recommendation",
        "op": "equals",
        "value": {"fixed": "escalate"},
        "on_fail": "STATE_MUTATION_ERROR",
    }
    job = {
        "config": {"runner": "verifier_blocks", "runner_version": 1},
        "evidence": {
            "snapshots": {
                "start": {"recommendations": []},
                "end": {"recommendations": [{"recommendation": "escalate"}]},
            },
            "tool_events": [],
        },
        "blocks": [status, zen],
        "case_id": "c",
        "plugin_results": {
            zen["id"]: {
                "verdict": "fail",
                "expected": "every rule passes",
                "actual": {"failed_rules": ["S4-R07"]},
            }
        },
    }
    out = sr.evaluate(job)
    assert out["verdict"] == "fail"
    line = next(x for x in out["block_lines"] if x["block_id"] == zen["id"])
    assert (
        line["kind"] == "plugin"
        and line["on_fail"] == "POLICY_VIOLATION"
        and line["actual"] == {"failed_rules": ["S4-R07"]}
    )
    job["plugin_results"][zen["id"]]["verdict"] = "pass"
    assert sr.evaluate(job)["verdict"] == "pass"
    del job["plugin_results"]
    assert sr.evaluate(job)["verdict"] == "blocked"  # a plug-in that did not run is never a pass


def test_v12_carries_its_rules_file_inside_the_template_hash():
    t = g.template(g.ZEN_VERSION)
    assert set(t["verifier_files"]) == {g.ZEN_RULES_SHA256}
    decision = next(c for c in t["criteria"] if c["criterion_id"] == "decision")
    assert decision["verifier_blocks"][-1]["plugin"]["id"] == "gorules-zen"
    v11 = g.template(g.EDGES_VERSION)
    assert "verifier_files" not in v11 and t["spec_sha256"] != v11["spec_sha256"]


def test_a_result_on_the_last_stdout_line_is_read_when_the_tool_logs_first():
    logged = b"Starting evaluation...\nRunning 1 test cases\n" + result(JOB)
    invoke, _ = fake((0, logged, b""))
    assert runner.run(MANIFEST, JOB, invoke=invoke)["results"][0]["verdict"] == "pass"


def test_promptfoo_manifest_pins_its_lockfile_and_base_image():
    import hashlib

    m = json.loads((ROOT / "services/plugins/promptfoo/manifest.json").read_text())
    contract.check_manifest({**m, "image": "sha256:" + "e" * 64})
    lock = (ROOT / "services/plugins/promptfoo/package-lock.json").read_bytes()
    assert m["upstream"]["lockfile_sha256"] == hashlib.sha256(lock).hexdigest()
    assert m["upstream"]["version"] == "0.125.1" and m["calls_model"] is False
    assert m["upstream"]["base_image"].startswith("node@sha256:1ee7b5f3")


def test_evidence_paths_in_the_scorer():
    from anvil.rlgym.scoring.service import _path

    root = {
        "output": {"rationale": "x"},
        "state": {"end": {"recommendations": [{"r": "a"}, {"r": "b"}]}},
    }
    assert _path(root, "output.rationale") == "x"
    assert _path(root, "state.end.recommendations[1].r") == "b"
    assert _path(root, "state.end.recommendations[*].r") == ["a", "b"]
    assert _path(root, "output.missing") is None
