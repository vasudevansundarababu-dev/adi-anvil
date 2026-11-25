"""Studio generator 2.7.0 (test@3): the end snapshot's `notices` collection holds what was published (with its
published_at_sequence, rule_id and version) and `scenario_events` holds the case's event definitions; the earlier
`scenario_events_fired` / `notices_published` collections are gone. RL Gym read only the old ones, so it saw no bulletin
in run-0238 (kj-7273836474's PH-PROOF-OF-ADDRESS v2 published at sequence 3). Every fired-bulletin reader (grading,
the library's rule in force, G-02) goes through events.scenario_events, which now reads both shapes."""

from anvil.rlgym.runs import events
from anvil.rlgym.verification import bulletin_blind

DEF = {
    "case_id": "kj-1",
    "event_id": "kj-1-e1",
    "notice_id": "kj-1-n1",
    "operation_id": "documents.list",
    "rule_id": "PH-PROOF-OF-ADDRESS",
    "version": 2,
    "supersedes": 1,
}
NOTICE = {
    "notice_id": "kj-1-n1",
    "published_at_sequence": 3,
    "rule_id": "PH-PROOF-OF-ADDRESS",
    "version": 2,
    "source": "policy_service",
    "text_sha256": "abc",
    "title": "Policy bulletin",
}
END_270 = {"scenario_events": [DEF], "notices": [NOTICE]}
TRANSCRIPT = [
    {"tool": "documents.list", "observation": {"ok": True, "sequence": 3}},
    {"tool": "recommend", "observation": {"ok": True, "sequence": 9}},
]


def test_a_270_bulletin_is_read_from_notices():
    out = events.scenario_events(
        {"start": {"scenario_events": [DEF], "notices": []}, "end": END_270}, TRANSCRIPT
    )
    assert out["fired"] == [
        {
            "event_id": "kj-1-e1",
            "notice_id": "kj-1-n1",
            "rule_id": "PH-PROOF-OF-ADDRESS",
            "from_version": 1,
            "to_version": 2,
            "published_at_sequence": 3,
            "text_sha256": "abc",
        }
    ]
    assert out["notices_published"] == [NOTICE]
    assert out["unread"] == ["kj-1-n1"]


def test_an_unpublished_definition_is_not_fired():
    out = events.scenario_events({"end": {"scenario_events": [DEF], "notices": []}}, TRANSCRIPT)
    assert out is None or out["fired"] == []


def test_the_older_shape_still_reads():
    old = {"scenario_events_fired": [{"rule_id": "R", "to_version": 2, "published_at_sequence": 1}]}
    assert events.scenario_events({"end": old}, [])["fired"][0]["to_version"] == 2


def test_g02_sees_a_270_bulletin():
    ep = {"snapshots": {"end": END_270}, "transcript": TRANSCRIPT}
    assert bulletin_blind.bulletin_fired(ep) is True


# --- Studio's sealed evidence (GET /evidence/{generation}) is the source of fired records --------------------------

STUDIO = {
    "scenario_events_fired": [
        {
            "scenario_id": "kj-1.scenario",
            "event_id": "kj-1-e1",
            "case_id": "kj-1",
            "trigger_sequence": 3,
            "published_at_sequence": 3,
            "rule_id": "PH-PROOF-OF-ADDRESS",
            "from_version": 1,
            "to_version": 2,
            "from_text_sha256": "a",
            "to_text_sha256": "b",
            "notice_id": "kj-1-n1",
        }
    ],
    "notices_published": [NOTICE],
}


def test_studios_sealed_evidence_is_preferred():
    out = events.scenario_events({"end": {}}, TRANSCRIPT, studio=STUDIO)
    assert out["fired"] == STUDIO["scenario_events_fired"]
    assert out["notices_published"] == [NOTICE]


def test_without_studios_evidence_the_notices_still_serve():
    out = events.scenario_events({"end": END_270}, TRANSCRIPT, studio=None)
    assert out["fired"][0]["to_version"] == 2


def test_the_adapter_fetches_the_sealed_evidence_after_sealing():
    import inspect

    from anvil.rlgym.runs import openenv, worker
    from anvil.rlgym.verification import reference_run

    assert '"studio_evidence"' in inspect.getsource(openenv.OpenEnvSession.request)
    assert '"/evidence/' in inspect.getsource(openenv.OpenEnvSession._evidence)
    assert 'studio=state.pop("studio_evidence", None)' in inspect.getsource(
        worker
    ) or "studio_evidence" in inspect.getsource(worker)
    assert "studio_evidence" in inspect.getsource(reference_run._episode)
    assert "studio_evidence" in inspect.getsource(bulletin_blind.bulletin_fired)
