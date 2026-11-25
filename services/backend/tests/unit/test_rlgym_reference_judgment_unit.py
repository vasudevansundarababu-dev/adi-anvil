"""The reference agent, G-01 (lookup) and G-02 (bulletin-blind) grade KYC Judgment v1 criteria exactly as a run does:
the activation bridge's graders (config.grader kyc-judgment.g2.<criterion>) get their judgment lines computed outside
the sandbox from the same frozen part a run's manifest holds (policy library, scenarios, case facts), the episode's
transcript and fired scenario events, and the project's placeholder switch. Before this every criterion came back
"blocked" (0/50) on the integration-test suite. A test-channel environment (key ending -test) uses its contract's
lookup baseline."""

import inspect

from anvil.rlgym.scoring import service as scoring
from anvil.rlgym.verification import bulletin_blind, lookup, reference_run

LINES = {"rules_applied.rules_applied": {"verdict": "pass"}}


def test_a_bridge_grader_gets_its_criterions_judgment_lines():
    cfg = {"grader": "kyc-judgment.g2.rules_applied"}
    assert scoring.judgment_extra(cfg, "rules_applied", {}, LINES) == {
        "judgment_results": LINES,
        "criterion": "rules_applied",
    }


def test_verifier_blocks_get_judgment_lines_beside_their_blocks():
    base = {"blocks": [{"id": "b"}], "case_id": "c"}
    out = scoring.judgment_extra({"runner": "verifier_blocks"}, "x", base, LINES)
    assert out == {**base, "judgment_results": LINES}
    assert scoring.judgment_extra({"runner": "verifier_blocks"}, "x", base, {}) == base
    assert scoring.judgment_extra({}, "x", {}, LINES) == {}  # nothing judgment-shaped: unchanged


def test_the_run_path_and_the_reference_path_share_it():
    assert "judgment_extra(" in inspect.getsource(scoring)
    src = inspect.getsource(reference_run._score)
    assert "scoring.judgment_results(" in src and "scoring.judgment_extra(" in src
    assert '"placeholder_graded"' in src and '"judgment"' in src
    assert "scenario_events" in src and '"transcript"' in src


def test_a_reference_episode_keeps_a_scoring_only_transcript():
    assert '"transcript": transcript' in inspect.getsource(reference_run._episode)
    # The stored report never carries observations: rows pick their fields.
    assert 'ep["transcript"]' not in inspect.getsource(reference_run.run)


def test_every_verification_path_freezes_the_judgment_part():
    for fn in (reference_run.run, lookup.run, bulletin_blind.run):
        src = inspect.getsource(fn)
        assert "judgment_context(" in src and "judgment=" in src


def test_a_test_channel_environment_uses_its_contracts_lookup():
    assert lookup.lookup_for("kyc-judgment-openenv-test@2") is lookup.lookup_for(
        "kyc-judgment-openenv@1"
    )
    assert lookup.lookup_for("kyc-judgment-openenv-test@2") is not None
    assert lookup.lookup_for("unknown-env-test@1") is None


def test_the_lookups_decision_is_played_as_given():
    """G-01 drives the reference agent with the lookup's decision; the truth's reference_if_not_fired must not let the
    agent swap it for the starting rules' answer."""
    src = inspect.getsource(lookup.run)
    assert "lookup.played(truth, said)" in src or "played(truth, said)" in src
    out = lookup.played(
        {"recommendation": "x", "reference_if_not_fired": {"recommendation": "y"}},
        {"recommendation": "z"},
    )
    assert out == {"recommendation": "z"}
