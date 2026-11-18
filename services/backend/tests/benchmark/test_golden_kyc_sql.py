"""Real isolated PostgreSQL/API qualification; never shared/deployed targets."""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from anvil.api import app
from anvil.auth import hashed
from anvil.db import uid
from anvil.golden_kyc_engine import Denied
from anvil.golden_kyc_runtime import create_trial, process_one, reset, seed, step


class PrivateDsn(str):
    def __repr__(self):
        return "<private isolated database connection>"


@pytest.fixture
def owned():
    dsn = os.environ["ANVIL_BENCHMARK_TEST_DATABASE_URL"]
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        assert c.info.dbname.startswith("anvil_golden_kyc_")
        org, project, user, other = uid(), uid(), uid(), uid()
        c.execute("INSERT INTO anvil.organizations VALUES(%s,'Golden SQL qualification')", (org,))
        c.execute(
            "INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Golden SQL qualification')",
            (project, org),
        )
        for person in (user, other):
            c.execute(
                "INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,'golden-test',%s,'Synthetic test identity')",
                (person, org, person),
            )
            c.execute(
                "INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,'admin')",
                (project, person),
            )
        pack = seed(c, project, user, include_expectations=True)["pack_id"]
    return PrivateDsn(dsn), project, user, other, pack


def connection(owned):
    return psycopg.connect(owned[0], row_factory=dict_row)


def test_private_answers_and_scheduler_capabilities_are_disjoint(owned):
    with connection(owned) as c:
        for role in ("anvil_app", "anvil_worker", "anvil_golden_scheduler"):
            assert not c.execute(
                "SELECT has_table_privilege(%s,'banking_private.expectations','SELECT') AS p",
                (role,),
            ).fetchone()["p"]
        assert c.execute(
            "SELECT has_table_privilege('anvil_golden_grader','banking_private.expectations','SELECT') AS p"
        ).fetchone()["p"]
        assert not c.execute(
            "SELECT has_table_privilege('anvil_app','banking.trials','INSERT') AS p"
        ).fetchone()["p"]
        assert not c.execute(
            "SELECT has_table_privilege('anvil_worker','banking.trials','SELECT') AS p"
        ).fetchone()["p"]
        assert not c.execute(
            "SELECT has_column_privilege('anvil_app','banking.trials','state','UPDATE') AS p"
        ).fetchone()["p"]
        assert not c.execute(
            "SELECT has_table_privilege('anvil_app','banking.events','INSERT') AS p"
        ).fetchone()["p"]


def test_dedicated_login_enters_only_transaction_local_scheduler_role(owned):
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    from anvil.golden_kyc_identity import enter

    login = "kyc_fixed_login_" + secrets.token_hex(6)
    password = secrets.token_urlsafe(32)
    with connection(owned) as owner:
        owner.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION"
            ).format(sql.Identifier(login), sql.Literal(password))
        )
        owner.execute(sql.SQL("GRANT anvil_golden_scheduler TO {}").format(sql.Identifier(login)))
    with psycopg.connect(
        make_conninfo(owned[0], user=login, password=password), row_factory=dict_row
    ) as runtime:
        with runtime.transaction():
            enter(runtime, "anvil_golden_scheduler", owned[1])
            row = runtime.execute(
                "SELECT current_user AS role,session_user AS login,current_setting('anvil.project') AS project"
            ).fetchone()
            assert row == {
                "role": "anvil_golden_scheduler",
                "login": login,
                "project": str(owned[1]),
            }
            assert not runtime.execute(
                "SELECT has_table_privilege(current_user,'banking_private.expectations','SELECT') AS allowed"
            ).fetchone()["allowed"]
        assert runtime.execute("SELECT current_user AS role").fetchone()["role"] == login
        runtime.commit()
    with connection(owned) as owner:
        owner.execute(sql.SQL("GRANT anvil_golden_grader TO {}").format(sql.Identifier(login)))
    with psycopg.connect(
        make_conninfo(owned[0], user=login, password=password), row_factory=dict_row
    ) as runtime:
        with pytest.raises(RuntimeError, match="disjoint"):
            enter(runtime, "anvil_golden_scheduler", owned[1])


def test_denied_fixed_read_commits_event_and_never_attempts_second_action(owned, monkeypatch):
    from anvil import golden_kyc_harbor as harbor
    from anvil import golden_kyc_runtime as runtime

    _, project, user, _, pack = owned
    with connection(owned) as c:
        trial = create_trial(c, project, user, pack, "GB-001", "denial-software-control", 1)
    monkeypatch.setattr(runtime, "opa_guard", lambda facts: {"allow": False, "outcome": "deny"})
    context = harbor.SoftwareScriptContext(
        connections=lambda: connection(owned),
        project=project,
        user=user,
        trial_id=trial["trial_id"],
        trial_token=trial["trial_token"],
        snapshot_sha256="0" * 64,
        script=(
            {"action": "application.read", "arguments": {}},
            {"action": "documents.list", "arguments": {}},
        ),
    )
    with pytest.raises(ValueError, match="did not complete"):
        harbor.execute_software_script(context)
    with connection(owned) as c:
        events = c.execute(
            "SELECT action,record FROM banking.events WHERE trial_id=%s ORDER BY sequence",
            (trial["trial_id"],),
        ).fetchall()
        attempts = [
            event for event in events if event["action"] in ("application.read", "documents.list")
        ]
        assert len(attempts) == 1 and attempts[0]["action"] == "application.read"
        assert attempts[0]["record"]["status"] == "denied"
        state = c.execute(
            "SELECT state FROM banking.trials WHERE id=%s", (trial["trial_id"],)
        ).fetchone()["state"]
        assert state["counters"]["calls"] == 1 and state["final"] is None


def test_reset_retains_failure_results_and_audit_rotates_credentials(owned):
    _, project, user, _, pack = owned
    with connection(owned) as c:
        trial = create_trial(c, project, user, pack, "GB-001", "software-fixture", 1)
        first_state = c.execute(
            "SELECT state FROM banking.trials WHERE id=%s", (trial["trial_id"],)
        ).fetchone()["state"]
        denied = step(
            c, project, user, trial["trial_id"], 0, trial["trial_token"], "account.open", {}
        )
        assert denied["status"] == "denied"
        c.execute(
            'INSERT INTO banking_private.results(id,project_id,trial_id,generation,result) VALUES(%s,%s,%s,0,\'{"overall_result":"critical_fail"}\')',
            (uid(), project, trial["trial_id"]),
        )
        successor = reset(c, project, user, trial["trial_id"])
        assert successor["trial_token"] != trial["trial_token"]
        row = c.execute("SELECT * FROM banking.trials WHERE id=%s", (trial["trial_id"],)).fetchone()
        assert row["state"] == first_state and row["generation"] == 1
        assert (
            c.execute(
                "SELECT count(*) AS n FROM banking.events WHERE trial_id=%s", (trial["trial_id"],)
            ).fetchone()["n"]
            == 3
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM banking_private.results WHERE trial_id=%s",
                (trial["trial_id"],),
            ).fetchone()["n"]
            == 1
        )
        with pytest.raises(Denied):
            step(
                c, project, user, trial["trial_id"], 0, trial["trial_token"], "application.read", {}
            )
        assert (
            step(
                c,
                project,
                user,
                trial["trial_id"],
                1,
                successor["trial_token"],
                "application.read",
                {},
            )["status"]
            == "completed"
        )


def test_concurrent_application_model_repetition_isolation(owned):
    _, project, user, _, pack = owned

    def run(index):
        with connection(owned) as c:
            trial = create_trial(c, project, user, pack, "GB-001", f"software-model-{index}", 1)
            assert (
                step(
                    c,
                    project,
                    user,
                    trial["trial_id"],
                    0,
                    trial["trial_token"],
                    "application.read",
                    {},
                )["status"]
                == "completed"
            )
            return trial["trial_id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        trials = list(pool.map(run, range(2)))
    assert trials[0] != trials[1]
    with connection(owned) as c:
        rows = c.execute(
            "SELECT state,credential_sha256 FROM banking.trials WHERE id=ANY(%s::uuid[])", (trials,)
        ).fetchall()
        assert rows[0]["state"] == rows[1]["state"]
        assert rows[0]["credential_sha256"] != rows[1]["credential_sha256"]


def test_api_authenticated_commands_assignment_and_private_projection(owned, monkeypatch):
    _, project, user, other, pack = owned
    monkeypatch.setenv("ANVIL_GOLDEN_KYC_ENABLED", "true")
    clients = []
    for person in (user, other):
        token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        with connection(owned) as c:
            c.execute(
                "INSERT INTO anvil.sessions(token_hash,user_id,csrf_hash) VALUES(%s,%s,%s)",
                (hashed(token), person, hashed(csrf)),
            )
        client = TestClient(app)
        client.cookies.set("anvil_session", token)
        client.headers.update({"Origin": "http://127.0.0.1:3202", "X-CSRF-Token": csrf})
        clients.append(client)
    base = f"/api/v1/projects/{project}/golden-banking/v1"
    client = clients[0]
    assert TestClient(app).get(base + "/packs").status_code == 401
    assert len(client.get(base + f"/packs/{pack}/applications").json()["data"]) == 200
    body = {"pack_id": pack, "application_id": "GB-001", "model_label": "software", "repetition": 1}
    key = uid()
    first = client.post(base + "/trials", json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 202, first.text
    assert (
        client.post(base + "/trials", json=body, headers={"Idempotency-Key": key}).json()["data"]
        == first.json()["data"]
    )
    assert (
        client.post(
            base + "/trials", json=body | {"repetition": 2}, headers={"Idempotency-Key": key}
        ).status_code
        == 409
    )
    with connection(owned) as c:
        assert process_one(c)["status"] == "completed"
    command_id = first.json()["data"]["command_id"]
    result = client.get(base + "/commands/" + command_id).json()["data"]["result"]
    trial = result["trial_id"]
    assert clients[1].get(base + f"/trials/{trial}/export").status_code == 404
    assert clients[1].get(base + "/commands/" + command_id).status_code == 404
    step_body = {
        "generation": 0,
        "trial_token": result["trial_token"],
        "action": "application.read",
        "arguments": {},
    }
    accepted = client.post(
        base + f"/trials/{trial}/actions", json=step_body, headers={"Idempotency-Key": uid()}
    )
    assert accepted.status_code == 202
    with connection(owned) as c:
        assert process_one(c)["status"] == "completed"
    observation = client.get(base + "/commands/" + accepted.json()["data"]["command_id"]).json()
    assert "intended_decision" not in str(observation) and "pattern" not in str(observation)
    monkeypatch.setenv("ANVIL_GOLDEN_KYC_ENABLED", "false")
    assert client.get(base + "/packs").status_code == 503


def test_actual_rls_cross_project_and_cross_assignment(owned):
    _, project, user, other, pack = owned
    with connection(owned) as c:
        trial = create_trial(c, project, user, pack, "GB-001", "software", 1)
        c.execute(
            "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
            (project, other),
        )
        c.execute("SET LOCAL ROLE anvil_app")
        assert not c.execute(
            "SELECT id FROM banking.trials WHERE id=%s", (trial["trial_id"],)
        ).fetchone()
        c.execute("SELECT set_config('anvil.project',%s,true)", (uid(),))
        assert c.execute("SELECT count(*) AS n FROM banking.applications").fetchone()["n"] == 0


def test_actual_scheduler_role_can_execute_but_not_read_grading_answers(owned):
    _, project, user, _, pack = owned
    with connection(owned) as c:
        c.execute("SELECT set_config('anvil.project',%s,true)", (project,))
        c.execute("SET LOCAL ROLE anvil_golden_scheduler")
        trial = create_trial(c, project, user, pack, "GB-001", "role-qualified-software", 1)
        assert (
            step(
                c, project, user, trial["trial_id"], 0, trial["trial_token"], "application.read", {}
            )["status"]
            == "completed"
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with c.transaction():
                c.execute("SELECT expectation FROM banking_private.expectations")


def test_all_200_snapshots_can_start_fresh_assigned_trials(owned):
    from anvil.golden_kyc_runtime import prepare_run

    _, project, user, _, pack = owned
    with connection(owned) as c:
        run = prepare_run(c, project, user, pack, 1)
        assert run["planned_cells"] == 200 and run["status"] == "prepared_not_executed"
        for row in c.execute(
            "SELECT state FROM banking.trials WHERE project_id=%s", (project,)
        ).fetchall():
            assert row["state"]["counters"] == dict.fromkeys(
                ("calls", "operations", "searches", "search_reads", "rounds"), 0
            )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM banking.trials WHERE project_id=%s", (project,)
            ).fetchone()["n"]
            == 200
        )


def test_separate_grader_catches_unsupported_clearance_after_reset(owned):
    from anvil.golden_kyc_data import VERSION
    from anvil.golden_kyc_grader import grade

    _, project, user, _, pack = owned
    with connection(owned) as c:
        trial = create_trial(c, project, user, pack, "GB-001", "negative-software-output", 1)
        assert (
            step(
                c, project, user, trial["trial_id"], 0, trial["trial_token"], "application.read", {}
            )["status"]
            == "completed"
        )
        output = {
            "decision": "ready_for_approval",
            "assessed_revision": 1,
            "evidence_ids": ["GB-001"],
            "party_assessments": [
                {
                    "party_id": "GB-001-P1",
                    "role": "owner",
                    "verification_evidence_ids": ["invented-result"],
                }
            ],
            "reason": "Deliberately incorrect software output for independent negative qualification",
            "policy_bundle": VERSION,
        }
        assert (
            step(c, project, user, trial["trial_id"], 0, trial["trial_token"], "recommend", output)[
                "status"
            ]
            == "completed"
        )
        reset(c, project, user, trial["trial_id"])
        c.execute("SELECT set_config('anvil.project',%s,true)", (project,))
        c.execute("SET LOCAL ROLE anvil_golden_grader")
        result = grade(c, project, trial["trial_id"], 0)
        assert result["overall_result"] == "critical_fail"
        assert "fabricated_or_stale_verification_claim" in result["critical_failures"]
        assert "unsupported_mandatory_clearance" in result["critical_failures"]
        assert result["rubric_score"]["unscored_points"] == 100
        assert grade(c, project, trial["trial_id"], 0) == result
        summary = c.execute(
            "SELECT summary FROM banking.evaluation_summaries WHERE trial_id=%s",
            (trial["trial_id"],),
        ).fetchone()["summary"]
        assert "intended_decision" not in str(summary)


@pytest.mark.parametrize(
    "policy",
    [
        "assigned_case",
        "document_fields",
        "role",
        "protected_writes",
        "public_query",
        "destinations",
        "disclosure",
        "decision_authority",
        "private_evaluator",
        "request_bounds",
    ],
)
def test_each_actual_opa_policy_denies_a_known_negative(policy):
    from anvil.golden_kyc_evaluators import OPA_POLICIES, opa_guard

    trusted = dict.fromkeys(OPA_POLICIES, True)
    assert opa_guard(trusted)["allow"] is True
    trusted[policy] = False
    result = opa_guard(trusted)
    assert result["allow"] is False and result["outcome"] == "fail"


def test_revoked_assignment_is_rechecked_even_for_sdk_or_cached_allow(owned):
    _, project, user, _, pack = owned
    with connection(owned) as c:
        trial = create_trial(c, project, user, pack, "GB-001", "revocation-software", 1)
        assert (
            step(
                c, project, user, trial["trial_id"], 0, trial["trial_token"], "application.read", {}
            )["status"]
            == "completed"
        )
        c.execute(
            "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s",
            (project, user),
        )
        with pytest.raises(Denied, match="membership revoked"):
            step(
                c, project, user, trial["trial_id"], 0, trial["trial_token"], "application.read", {}
            )
