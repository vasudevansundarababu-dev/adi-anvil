"""Software report contracts; no model or human-review claims."""

import io

import pytest
from pypdf import PdfReader

from anvil import benchmark_rehearsal as rehearsal
from anvil.benchmark_rehearsal_report import render


@pytest.mark.parametrize("template", ["executive", "technical"])
def test_executed_fictional_report_keeps_authorization_and_private_data_separate(template):
    frozen = rehearsal.manifest()
    result = rehearsal.run(frozen)
    result["private_expected_answer"] = "PRIVATE-GOLDEN-SENTINEL-DO-NOT-EXPORT"
    row = {
        "id": "00000000-0000-4000-8000-000000000001",
        "name": "<img src='/etc/passwd'/> Fictional arithmetic",
        "manifest": frozen,
        "manifest_sha256": "a" * 64,
        "result": result,
        "report_authorization": {"state": "admin_run_exempt", "reviewer_verified": False},
    }
    raw = render(row, template)
    assert raw.startswith(b"%PDF")
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)
    assert "Fictional software comparison" in text
    assert "admin_run_exempt" in text and "81" in text
    assert result["result_sha256"] in text
    assert "PRIVATE-GOLDEN-SENTINEL" not in text and "root:x:" not in text
    assert "Provider calls: 0" in text and "not a fabricated" in text
