"""Actual SQL rejection of malformed internal policy snapshots; no execution claims."""

from copy import deepcopy
from uuid import uuid4

import psycopg
import pytest
from test_private_storage import connection
from test_private_storage import lab as storage_fixture

from anvil import benchmark_rehearsal as rehearsal
from anvil import benchmark_report_policy as report_policy
from anvil.db import Jsonb, digest

lab = storage_fixture


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "missing_version",
        "missing_count",
        "null_count",
        "string_count",
        "boolean_count",
        "list_count",
        "null_version",
        "count_over_bound",
        "count_negative",
        "unknown_policy_id",
        "wrong_policy_sha",
        "false_admin_flag",
        "wrong_default_count",
    ],
)
def test_forward_guard_rejects_malformed_policy_without_persisting_authority(lab, fault):
    identifier = str(uuid4())
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        manifest = rehearsal.manifest()
        c.execute(
            "INSERT INTO anvil.benchmark_rehearsals(id,project_id,name,created_by,manifest,manifest_sha256) VALUES(%s,%s,'Unexecuted SQL guard probe',%s,%s,%s)",
            (identifier, lab["project"], lab["engineer"], Jsonb(manifest), digest(manifest)),
        )
        frozen = report_policy.current(c, lab["project"])
    policy = deepcopy(frozen)
    if fault == "empty":
        policy = {}
    elif fault == "missing_version":
        policy.pop("version")
    elif fault == "missing_count":
        policy.pop("required_reviewers")
    elif fault == "null_count":
        policy["required_reviewers"] = None
    elif fault == "string_count":
        policy["required_reviewers"] = "1"
    elif fault == "boolean_count":
        policy["required_reviewers"] = True
    elif fault == "list_count":
        policy["required_reviewers"] = []
    elif fault == "null_version":
        policy["version"] = None
    elif fault == "count_over_bound":
        policy["required_reviewers"] = 11
    elif fault == "count_negative":
        policy["required_reviewers"] = -1
    elif fault == "unknown_policy_id":
        policy["policy_id"] = str(uuid4())
    elif fault == "wrong_policy_sha":
        policy["policy_sha256"] = "0" * 64
    elif fault == "false_admin_flag":
        policy["admin_run_exempt"] = False
    elif fault == "wrong_default_count":
        policy["required_reviewers"] = 0
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute(
                "INSERT INTO anvil.benchmark_report_authorizations(id,project_id,target_kind,target_id,policy,policy_sha256,admin_run_exempt,actor_id) VALUES(%s,%s,'rehearsal',%s,%s,%s,false,%s)",
                (
                    str(uuid4()),
                    lab["project"],
                    identifier,
                    Jsonb(policy),
                    frozen["policy_sha256"],
                    lab["engineer"],
                ),
            )
    with connection() as c:
        assert (
            c.execute(
                "SELECT count(*) n FROM anvil.benchmark_report_authorizations WHERE target_id=%s",
                (identifier,),
            ).fetchone()["n"]
            == 0
        )
