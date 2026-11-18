from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException

from anvil import golden_kyc_input_binding as binding
from anvil.praxis_generic_contract import digest


def source(kind="user_session"):
    project, sponsor = uuid4(), uuid4()
    receipt = {"package_sha256": "a" * 64, "source_sha256": "b" * 64,
               "authenticated_actor": {"kind": kind, "client_id": None,
                                       "sponsor_user_id": str(sponsor)}}
    if kind == "workload_identity":
        receipt["authenticated_actor"]["client_id"] = str(uuid4())
    return project, {"project_id": project, "created_by": sponsor, "receipt": receipt,
                     "receipt_sha256": digest(receipt), "package_sha256": "a" * 64}


@pytest.mark.parametrize("kind", ["user_session", "workload_identity"])
def test_genuine_stored_modes_keep_their_identity(monkeypatch, kind):
    project, row = source(kind)
    before = deepcopy(row)
    monkeypatch.setattr(binding, "one", lambda *args: {"id": row["created_by"]})
    binding.authenticated_resolution(object(), project, row)
    assert row == before


@pytest.mark.parametrize("fault", ["foreign_project", "receipt_hash", "package", "sponsor",
                                  "inactive_sponsor", "client_on_session", "unknown_mode",
                                  "missing_source", "missing_workload_client"])
def test_offline_upload_does_not_accept_forged_or_unscoped_provenance(monkeypatch, fault):
    project, row = source("workload_identity" if fault == "missing_workload_client" else "user_session")
    actor = row["receipt"]["authenticated_actor"]
    if fault == "foreign_project":
        project = uuid4()
    elif fault == "package":
        row["receipt"]["package_sha256"] = "c" * 64
    elif fault == "sponsor":
        actor["sponsor_user_id"] = str(uuid4())
    elif fault == "client_on_session":
        actor["client_id"] = str(uuid4())
    elif fault == "unknown_mode":
        actor["kind"] = "approved_by_zip"
    elif fault == "missing_source":
        row["receipt"].pop("source_sha256")
    elif fault == "missing_workload_client":
        actor["client_id"] = None
    row["receipt_sha256"] = "0" * 64 if fault == "receipt_hash" else digest(row["receipt"])
    monkeypatch.setattr(binding, "one", lambda *args: None if fault == "inactive_sponsor" else {"id": row["created_by"]})
    with pytest.raises(HTTPException) as error:
        binding.authenticated_resolution(object(), project, row)
    assert error.value.status_code == 409
    assert error.value.detail["ready"] is False
