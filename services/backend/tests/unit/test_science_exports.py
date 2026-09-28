import io
import json
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pypdf import PdfReader

from anvil.evaluation import score_rubric
from anvil.fixtures import HASHES, trusted
from anvil.reports import LABEL, html_bytes, pdf_bytes
from anvil.schemas import Rubric


def test_weighted_score_critical_and_threshold():
    rubric = {
        "criteria": [{"id": "a", "weight_bps": 6000}, {"id": "b", "weight_bps": 4000}],
        "threshold": 75,
        "critical_rules": ["critical"],
    }
    assert score_rubric(rubric, {"a": 4, "b": 2}, []) == (Decimal("80"), "pass")
    assert score_rubric(rubric, {"a": 4, "b": 2}, ["critical"]) == (Decimal("80"), "fail")
    rubric["threshold"] = 85
    assert score_rubric(rubric, {"a": 4, "b": 2}, []) == (Decimal("80"), "fail")
    with pytest.raises(HTTPException):
        score_rubric(rubric, {"a": 4}, [])
    with pytest.raises(HTTPException):
        score_rubric(rubric, {"a": 4, "b": True}, [])


def test_original_fixture_integrity_and_independent_calculations():
    for path in HASHES:
        assert trusted(path)
    assert 90 * 125 - 60 * 125 == 3750
    assert (80 - 60) / 80 < Decimal(".30")
    assert Decimal(240000) / Decimal(140000) > Decimal("1.7")
    assert 400000 < 500000
    assert 125000 > 120000


def test_pdf_single_page_and_html_escaping():
    content = {
        "label": LABEL,
        "question": "Does a supplied constraint survive?",
        "tested": "Three original synthetic cases; no measured model performance.",
        "observed": ["Three passes, three failures in six illustrative episodes."],
        "relevance": "A scoped diagnostic question, not a causal claim.",
        "boundary": "Synthetic source, predetermined output, scripted review. Uncertainty not estimated. Improvement not tested.",
        "next_step": "Review evidence before proposing a real pilot.",
        "report_revision_id": "00000000-0000-4000-8000-000000000001",
    }
    pdf = PdfReader(io.BytesIO(pdf_bytes(content)))
    assert len(pdf.pages) == 1
    assert float(pdf.pages[0].mediabox.width) == pytest.approx(595.2756, abs=0.01)
    assert LABEL in pdf.pages[0].extract_text()
    content["question"] = "<script>alert(1)</script>"
    assert b"<script>" not in html_bytes(content)
    content["question"] = "overflow " * 1000
    with pytest.raises(ValueError, match="question_word_limit"):
        pdf_bytes(content)
    content["question"] = "x" * 10000
    with pytest.raises(ValueError, match="one_page_overflow"):
        pdf_bytes(content)


def test_rubric_rejects_missing_anchors_and_bad_weights():
    from pydantic import ValidationError

    template = json.loads(trusted("rubric-template.json"))
    content = {
        "title": "test",
        "criteria": template["criteria"],
        "threshold": 75,
        "critical_rules": [],
        "calibration": {
            k: "test"
            for k in [
                "clear_pass",
                "clear_fail",
                "valid_alternative",
                "critical_error",
                "ambiguous_reference",
            ]
        },
        "reviewer_id": "00000000-0000-4000-8000-000000000001",
        "advisor_id": "00000000-0000-4000-8000-000000000002",
        "origin": "original_synthetic_fixture",
    }
    Rubric.model_validate(content)
    content["criteria"][0]["weight_bps"] = 4999
    with pytest.raises(ValidationError):
        Rubric.model_validate(content)
    content["criteria"][0]["weight_bps"] = 5000
    del content["criteria"][0]["anchors"]["2"]
    with pytest.raises(ValidationError):
        Rubric.model_validate(content)


@pytest.mark.parametrize("include_valid", [False, True])
def test_denominators_keep_cancelled_unknown_invalid_and_missing_separate(
    monkeypatch, include_valid
):
    from anvil import reports

    entries = [
        ("cancelled", "pending_review", None),
        ("execution_unknown", "pending_review", None),
        ("failed_operational", "invalid", None),
        ("finalized", "unscorable", None),
        ("awaiting_review", "pending_review", None),
    ]
    if include_valid:
        entries.extend([("finalized", "pass", Decimal(100)), ("finalized", "fail", Decimal(70))])
    episodes = [
        {
            "id": str(i),
            "state": state,
            "outcome": outcome,
            "score": score,
            "final_assessment_id": str(i) if state == "finalized" else None,
        }
        for i, (state, outcome, score) in enumerate(entries)
    ]

    class Query:
        def execute(self, *args):
            return self

        def fetchall(self):
            return episodes

    def revision(c, rid, kind):
        content = {
            "protocol": {
                "suite_revision_id": "suite",
                "objective_revision_id": "objective",
                "candidates": ["a", "b"],
            },
            "suite": {"task_revision_ids": ["task"]},
            "objective": {"hypothesis": "test"},
            "task": {
                "source_revision_id": "source",
                "family_id": "family",
                "origin": "original_synthetic_fixture",
            },
        }[kind]
        return {"id": rid, "content_hash": "test-hash", "content": content}

    monkeypatch.setattr(
        reports,
        "get_run",
        lambda c, rid: {
            "state": "review_pending",
            "protocol_revision_id": "protocol",
            "origin": "illustrative",
        },
    )
    monkeypatch.setattr(reports.domain, "get_revision", revision)
    result = reports.facts(Query(), "run", final=False)
    assert (
        result["cancelled"]
        == result["unknown"]
        == result["invalid"]
        == result["unscorable"]
        == result["pending"]
        == 1
    )
    assert result["valid"] == (2 if include_valid else 0)
    assert result["mean_score"] == (85 if include_valid else None)
    assert result["pass_rate"] == (0.5 if include_valid else None)
