"""KYC Judgment v1 at admission: the pinned policy library (Studio's scorer endpoint, RL Gym review B1) and each
selected case's registry-case v2 facts are frozen in the manifest, so grading never reads anything that could change.
Only registry-case v2 cases trigger it: golden KYC v8 admission makes no extra call and its manifest is unchanged."""

import inspect

import pytest

from anvil.rlgym.common import GymError, sha
from anvil.rlgym.runs import library
from anvil.rlgym.runs import service as runs

V2 = {
    "schema_version": "adi.utility.registry-case.v2",
    "case_id": "kj-1",
    "application_type": "adult_joint",
    "facts": {"process": "account_opening"},
    "parties": [{"party_id": "kj-1-p1", "facts": {"citizenship": ["US"]}}],
}
LIB = {
    "library_id": "kyc-judgment.library",
    "export": {"library_revision": 1},
    "rules": [
        {
            "rule_id": "R",
            "subject": "case",
            "versions": [
                {
                    "version": 1,
                    "text": "t",
                    "text_sha256": library.text_sha("t"),
                    "effective": {"mode": "from_date", "from": "2026-01-01"},
                    "effect": "obligation",
                    "condition": None,
                }
            ],
        }
    ],
}


def test_v8_cases_freeze_nothing_and_call_nothing():
    def fetch():
        raise AssertionError("no call for v1 cases")

    assert (
        runs.judgment_part([{"case_id": "kyc-1", "application_type": "custodial"}], fetch) is None
    )


def test_v2_cases_freeze_the_library_and_their_facts():
    out = runs.judgment_part([V2], lambda: {"library": LIB, "sha256": sha(LIB)})
    assert out["library"] == LIB and out["library_sha256"] == sha(LIB)
    assert out["cases"]["kj-1"] == {"facts": V2["facts"], "parties": V2["parties"]}


def test_a_library_whose_text_hashes_do_not_match_is_refused():
    bad = {
        **LIB,
        "rules": [
            {
                **LIB["rules"][0],
                "versions": [{**LIB["rules"][0]["versions"][0], "text_sha256": "0" * 64}],
            }
        ],
    }
    with pytest.raises(GymError) as e:
        runs.judgment_part([V2], lambda: {"library": bad, "sha256": sha(bad)})
    assert e.value.code == "HASH_MISMATCH"


def test_admission_and_manifest_carry_it():
    assert "judgment_part(" in inspect.getsource(runs.admission_check)
    assert '"judgment"' in inspect.getsource(runs._manifest)
