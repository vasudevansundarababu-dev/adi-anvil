# ruff: noqa: F811
"""Actual API/DB/generation SDK/Docker/MCP/Harbor path using an authored mock provider.

This is software conformance, not evidence that a live generation model is correct.
No provider keys or real requests are used. All databases/credentials are isolated.
"""

import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event

import httpx
import pytest
from test_api_security import USERS
from test_praxis_harbor import BASE
from test_workspace_execution import configured  # noqa: F401,F811

from anvil.config import ROOT
from anvil.db import one, transaction, uid
from anvil.import_worker import process
from anvil.praxis_executable import parse


def bundle(task):
    spec = importlib.util.spec_from_file_location(
        "generated_fixture_contract", ROOT / "services/backend/tests/unit/test_import_codegen.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.fixture_bundle(task)


def mock_provider(value, calls):
    def respond(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert "evaluation_private" not in body["input"][0]["content"]
        return httpx.Response(
            200,
            json={
                "id": "mock-generation",
                "object": "response",
                "model": "test-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(value), "annotations": []}
                        ],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 100, "total_tokens": 200},
            },
        )

    return httpx.MockTransport(respond)


def post(client, path, value=None, key=None):
    response = client.post(
        BASE + "/workspace" + path, json=value or {}, headers={"Idempotency-Key": key or uid()}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def configure(configured, monkeypatch, cap=1000000, paid=False):
    admin = configured["clients"]["admin-1"]
    monkeypatch.setenv("ANVIL_INSTALLATION_ADMIN_IDS", USERS["admin-1"])
    settings = post(
        admin,
        "/import-generation/settings",
        {
            "provider": "openai",
            "model_id": "test-model",
            "secret": "FAKE-GENERATION-ONLY-KEY",
            "default_cap_micro_usd": cap,
            "max_output_tokens": 8192,
            "max_calls": 5,
            "input_micro_usd_per_million_tokens": 1000000,
            "output_micro_usd_per_million_tokens": 1000000,
            "pricing_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "enable_paid_generation": paid,
        },
    )
    assert settings["configured"] and "secret" not in settings
    return admin


@pytest.fixture
def container_free_preflight(monkeypatch):
    """Replaces only the disposable container behind tool-shape probes.

    The real probe shaping, budget, dispatch and permission code still runs. Real container
    probes are covered by the ANVIL_TEST_HARBOR=1 opt-in tests in this module.
    """
    from anvil import import_sandbox

    class Environment:
        def __init__(self, task):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call(self, tool, arguments):
            return {"status": "saved", "path": "output.json"}

    monkeypatch.setattr(import_sandbox, "Environment", Environment)


def claim(project):
    with transaction(project, worker=True) as c:
        return one(c, "SELECT * FROM anvil.claim_import_job()")


@pytest.mark.skipif(
    os.environ.get("ANVIL_TEST_HARBOR") != "1",
    reason="Explicit native Docker/Harbor opt-in required",
)
def test_all_three_goldens_generate_validate_publish_and_notebook_roundtrip(
    configured, monkeypatch
):
    admin = configure(configured, monkeypatch)
    from anvil.cli import PROJECT

    summary = []
    for path in sorted((ROOT / "contracts/praxis/golden-v3").glob("*.task.json")):
        task = parse(path.read_bytes())
        imported = admin.post(
            BASE + "/praxis-sources",
            json={"payload": path.read_text()},
            headers={"Idempotency-Key": uid()},
        )
        assert imported.status_code == 200, imported.text
        sid = imported.json()["data"]["id"]
        key = uid()
        family = post(admin, "/tasks/" + sid + "/generate", key=key)
        assert post(admin, "/tasks/" + sid + "/generate", key=key)["id"] == family["id"]
        calls = []
        job = claim(PROJECT)
        assert str(job["target_id"]) == family["current_revision_id"]
        process(job, transport=mock_provider(bundle(task), calls))
        response = admin.get(BASE + "/workspace/tasks/" + sid + "/executable-import")
        assert response.status_code == 200, response.text
        ready = response.json()["data"]
        assert ready["revisions"][0]["state"] == "ready", ready["revisions"][0]["report"]
        assert (
            len(calls) == 1
            and ready["charged_micro_usd"] == 200
            and ready["reserved_micro_usd"] == 0
        )
        assert len(ready["revisions"][0]["report"]["fixtures"]) == 7
        assert len(ready["revisions"][0]["report"]["source_qa_fixtures"]) == 7
        assert ready["revisions"][0]["report"]["harbor_smoke"]["status"] == "passed"
        from import_pipeline_support import evaluate_ready

        evaluation = evaluate_ready(configured, monkeypatch, ready["revisions"][0]["package_id"])
        rid = ready["current_revision_id"]
        old_settings = ready["settings_id"]
        configure(configured, monkeypatch, cap=2000000)
        latest_settings = admin.get(BASE + "/workspace/import-generation/settings").json()["data"]
        rebound = post(
            admin,
            "/executable-imports/" + ready["id"] + "/rebind",
            {"base_revision_id": rid, "settings_id": latest_settings["id"]},
        )
        assert rebound["ready_revision_id"] == rid and rebound["current_revision_id"] == rid
        assert (
            rebound["cap_micro_usd"] == ready["cap_micro_usd"]
            and rebound["charged_micro_usd"] == 200
        )
        assert rebound["settings_id"] != old_settings
        book_response = admin.get(
            BASE
            + "/workspace/executable-imports/"
            + ready["id"]
            + "/revisions/"
            + rid
            + "/notebook"
        )
        assert book_response.status_code == 200
        assert (
            task.evaluation_private.canary not in book_response.text
            and "FAKE-GENERATION" not in book_response.text
        )
        # Notebook outputs are hostile evidence and must be ignored on return.
        book = book_response.json()
        book["cells"][1]["outputs"] = [{"output_type": "stream", "text": "ready=true"}]
        saved = post(
            admin,
            "/executable-imports/" + ready["id"] + "/edit",
            {"base_revision_id": rid, "notebook": book},
        )
        assert saved["ready_revision_id"] == rid
        process(claim(PROJECT))
        successor = admin.get(BASE + "/workspace/tasks/" + sid + "/executable-import").json()[
            "data"
        ]
        assert successor["revisions"][0]["state"] == "ready", successor["revisions"][0]["report"]
        assert successor["charged_micro_usd"] == 200 and len(calls) == 1
        assert (
            successor["revisions"][0]["settings_id"] == old_settings
        )  # Manual edits retain code-generation provenance.
        stale = admin.post(
            BASE + "/workspace/executable-imports/" + ready["id"] + "/edit",
            json={"base_revision_id": rid, "notebook": book},
            headers={"Idempotency-Key": uid()},
        )
        assert stale.status_code == 409
        summary.append(
            {
                "task": task.task_id,
                "import_id": ready["id"],
                "generation_calls": len(calls),
                "fixtures": 7,
                "harbor_smoke": "passed",
                "notebook_successor": "ready",
                "model_performance": False,
                "evaluation": evaluation,
            }
        )
    target = ROOT / "artifacts/test-runs/import-pipeline-e2e.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2))


def test_installation_scope_project_boundaries_and_unknown_no_retry(
    configured, monkeypatch, container_free_preflight
):
    from anvil.cli import PROJECT

    admin = configured["clients"]["admin-1"]
    other = configured["clients"]["contract-admin-a"]
    settings_body = {
        "provider": "openai",
        "model_id": "test-model",
        "secret": "FAKE-ONLY",
        "default_cap_micro_usd": 1,
        "max_output_tokens": 1024,
        "max_calls": 1,
        "enable_paid_generation": False,
    }
    denied = other.post(
        BASE + "/workspace/import-generation/settings",
        json=settings_body,
        headers={"Idempotency-Key": uid()},
    )
    assert denied.status_code == 403
    admin = configure(configured, monkeypatch)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    family = post(admin, "/tasks/" + source["id"] + "/generate")
    assert (
        configured["clients"]["outsider"]
        .get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import")
        .status_code
        == 404
    )
    calls = []

    def timeout(request):
        calls.append(1)
        raise httpx.ReadTimeout("test-only ambiguity", request=request)

    job = claim(PROJECT)
    process(job, transport=httpx.MockTransport(timeout))
    result = admin.get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import").json()[
        "data"
    ]
    assert result["revisions"][0]["state"] == "outcome_unknown", result
    assert result["reserved_micro_usd"] > 0 and len(calls) == 1
    assert family["id"] == result["id"]


def test_whole_import_cap_blocks_before_dispatch_and_default_change_does_not_reset(
    configured, monkeypatch, container_free_preflight
):
    from anvil.cli import PROJECT

    admin = configure(configured, monkeypatch, cap=1)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    family = post(admin, "/tasks/" + source["id"] + "/generate")
    calls = []
    process(claim(PROJECT), transport=mock_provider(bundle(parse(path.read_bytes())), calls))
    result = admin.get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import").json()[
        "data"
    ]
    assert result["revisions"][0]["state"] == "budget_paused" and calls == []
    assert result["cap_micro_usd"] == 1 and result["reserved_micro_usd"] == 0
    configure(configured, monkeypatch, cap=1000000)
    next_revision = post(admin, "/tasks/" + source["id"] + "/generate")
    assert next_revision["id"] == family["id"] and next_revision["cap_micro_usd"] == 1
    process(claim(PROJECT), transport=mock_provider(bundle(parse(path.read_bytes())), calls))
    assert calls == []


def test_usage_capture_survives_actor_revocation_after_dispatch(
    configured, monkeypatch, container_free_preflight
):
    import psycopg

    from anvil.cli import PROJECT
    from anvil.config import setting

    admin = configure(configured, monkeypatch)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    family = post(admin, "/tasks/" + source["id"] + "/generate")
    calls = []
    provider = mock_provider(bundle(parse(path.read_bytes())), calls)

    def revoke_then_return(request):
        with psycopg.connect(setting("MIGRATION_DATABASE_URL")) as c:
            c.execute(
                "UPDATE anvil.memberships SET active=false WHERE project_id=%s AND user_id=%s",
                (PROJECT, USERS["admin-1"]),
            )
        return provider.handle_request(request)

    process(claim(PROJECT), transport=httpx.MockTransport(revoke_then_return))
    with transaction(PROJECT, worker=True) as c:
        result = one(c, "SELECT * FROM anvil.executable_imports WHERE id=%s", (family["id"],))
        revision = one(
            c,
            "SELECT state FROM anvil.executable_import_revisions WHERE id=%s",
            (family["current_revision_id"],),
        )
        assert result["charged_micro_usd"] == 200 and result["reserved_micro_usd"] == 0
        assert revision["state"] == "generation_failed" and len(calls) == 1


@pytest.mark.skipif(
    os.environ.get("ANVIL_TEST_HARBOR") != "1", reason="Explicit isolated Docker opt-in required"
)
def test_always_allow_guard_cannot_qualify(configured, monkeypatch):
    from anvil.cli import PROJECT

    admin = configure(configured, monkeypatch)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    value = bundle(parse(path.read_bytes()))
    value["code"] = (
        value["code"].split("def guard", 1)[0]
        + "def guard(tool, arguments, inputs, events):\n    return {'allowed': True, 'violations': []}\n"
    )
    post(admin, "/tasks/" + source["id"] + "/generate")
    process(claim(PROJECT), transport=mock_provider(value, []))
    result = admin.get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import").json()[
        "data"
    ]
    assert result["revisions"][0]["state"] == "validation_failed"
    assert "Runtime guard expected/actual mismatch" in result["revisions"][0]["report"]["error"]


@pytest.mark.skipif(
    os.environ.get("ANVIL_TEST_HARBOR") != "1",
    reason="Explicit native Docker/Harbor opt-in required",
)
def test_invalid_generated_code_is_retained_and_can_be_fixed_as_artifact_successor(
    configured, monkeypatch
):
    from anvil.cli import PROJECT

    admin = configure(configured, monkeypatch)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    task = parse(path.read_bytes())
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    broken = bundle(task)
    broken["code"] = "def evaluate(:\n"
    family = post(admin, "/tasks/" + source["id"] + "/generate")
    calls = []
    process(claim(PROJECT), transport=mock_provider(broken, calls))
    result = admin.get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import").json()[
        "data"
    ]
    assert result["revisions"][0]["state"] == "generation_failed"
    assert "rules.py line 1" in result["revisions"][0]["report"]["error"]
    prefix = (
        "/workspace/executable-imports/"
        + family["id"]
        + "/revisions/"
        + family["current_revision_id"]
    )
    code = admin.get(BASE + prefix + "/code")
    assert code.status_code == 200 and code.json()["data"]["code"] == broken["code"]
    assert task.evaluation_private.canary not in code.text
    outsider = configured["clients"]["outsider"]
    assert outsider.get(BASE + prefix + "/code").status_code in (403, 404)
    saved = post(
        admin,
        "/executable-imports/" + family["id"] + "/edit",
        {"base_revision_id": family["current_revision_id"], "artifacts": bundle(task)},
    )
    assert saved["current_revision_id"] != family["current_revision_id"]
    process(claim(PROJECT))
    fixed = admin.get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import").json()[
        "data"
    ]
    assert fixed["revisions"][0]["state"] == "ready", fixed
    assert fixed["charged_micro_usd"] == 200 and len(calls) == 1


def test_paid_generation_requires_exact_admin_source_processing_permission(
    configured, monkeypatch, container_free_preflight
):
    from anvil import workspace_dispatch
    from anvil.cli import PROJECT
    from anvil.import_generation import processing_authorized

    admin = configure(configured, monkeypatch, paid=True)
    monkeypatch.setenv("ANVIL_IMPORT_GENERATION_ENABLED", "true")
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("No network request is allowed in this authority test")

    monkeypatch.setattr(workspace_dispatch, "execute", forbidden)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    family = post(admin, "/tasks/" + source["id"] + "/generate")
    process(claim(PROJECT))
    result = admin.get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import").json()[
        "data"
    ]
    assert (
        result["revisions"][0]["report"]["error"] == "project_admin_processing_permission_required"
    )
    assert calls == [] and result["reserved_micro_usd"] == 0
    wrong = admin.post(
        BASE + "/workspace/tasks/" + source["id"] + "/generate",
        json={
            "rights_confirmed": True,
            "source_sha256": "0" * 64,
            "settings_id": family["settings_id"],
            "cap_micro_usd": family["cap_micro_usd"],
        },
        headers={"Idempotency-Key": uid()},
    )
    assert wrong.status_code == 409
    post(
        admin,
        "/tasks/" + source["id"] + "/generate",
        {
            "rights_confirmed": True,
            "source_sha256": source["source_sha256"],
            "settings_id": family["settings_id"],
            "cap_micro_usd": family["cap_micro_usd"],
        },
    )
    with transaction(PROJECT, USERS["admin-1"]) as c:
        assert processing_authorized(c, family, source["source_sha256"])
    post(admin, "/executable-imports/" + family["id"] + "/processing-rights/revoke")
    with transaction(PROJECT, USERS["admin-1"]) as c:
        assert not processing_authorized(c, family, source["source_sha256"])
    assert calls == []


@pytest.mark.skipif(
    os.environ.get("ANVIL_TEST_HARBOR") != "1", reason="Explicit isolated Docker opt-in required"
)
def test_cancellation_stops_between_generated_rule_invocations(configured, monkeypatch):
    from anvil import import_sandbox
    from anvil.cli import PROJECT

    admin = configure(configured, monkeypatch)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    family = post(admin, "/tasks/" + source["id"] + "/generate")
    original = import_sandbox.execute_code
    invocations = []

    def cancel_after_first(*args, **kwargs):
        result = original(*args, **kwargs)
        invocations.append(1)
        if len(invocations) == 1:
            post(admin, "/executable-imports/" + family["id"] + "/cancel")
        return result

    monkeypatch.setattr(import_sandbox, "execute_code", cancel_after_first)
    process(claim(PROJECT), transport=mock_provider(bundle(parse(path.read_bytes())), []))
    result = admin.get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import").json()[
        "data"
    ]
    assert result["revisions"][0]["state"] == "cancelled" and invocations == [1]
    assert result["charged_micro_usd"] == 200 and result["reserved_micro_usd"] == 0


@pytest.mark.skipif(
    os.environ.get("ANVIL_TEST_HARBOR") != "1", reason="Explicit isolated Docker opt-in required"
)
def test_invalid_output_capture_is_not_misreported_as_empty_zero_score():
    from anvil.import_sandbox import Environment, docker

    task = parse((ROOT / "contracts/praxis/golden-v3/01-marketing.task.json").read_bytes())
    with Environment(task) as environment:
        docker(
            [
                "exec",
                environment.name,
                "python3",
                "-c",
                "from pathlib import Path; Path('/workspace/output/output.json').write_text('x'*65537)",
            ]
        )
        with pytest.raises(ValueError, match="exceeds 65536"):
            environment.output()
        docker(
            [
                "exec",
                environment.name,
                "python3",
                "-c",
                "from pathlib import Path; Path('/workspace/output/output.json').write_text('null')",
            ]
        )
        with pytest.raises(ValueError, match="schema type mismatch"):
            environment.output()


def test_import_terminal_capture_fences_project_before_revision(configured, monkeypatch):
    from anvil import import_worker
    from anvil.cli import PROJECT

    admin = configure(configured, monkeypatch)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    family = post(admin, "/tasks/" + source["id"] + "/generate")
    job = claim(PROJECT)
    entered = Event()
    original = import_worker.project_fence

    def observed(c, project):
        entered.set()
        return original(c, project)

    monkeypatch.setattr(import_worker, "project_fence", observed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction(PROJECT, USERS["admin-1"]) as c:
            c.execute("SELECT id FROM anvil.projects WHERE id=%s FOR UPDATE", (PROJECT,))
            future = pool.submit(
                import_worker.finish,
                job,
                USERS["admin-1"],
                "generation_failed",
                {"stage": "fence_test"},
            )
            assert entered.wait(5) and not future.done()
            assert one(
                c,
                "SELECT id FROM anvil.executable_import_revisions WHERE id=%s FOR UPDATE NOWAIT",
                (family["current_revision_id"],),
            )
        future.result(timeout=5)


@pytest.mark.skipif(
    os.environ.get("ANVIL_TEST_HARBOR") != "1", reason="Explicit isolated Docker opt-in required"
)
def test_private_source_qa_blocks_a_self_consistent_but_wrong_generated_rule(
    configured, monkeypatch
):
    from anvil.cli import PROJECT

    admin = configure(configured, monkeypatch)
    path = ROOT / "contracts/praxis/golden-v3/01-marketing.task.json"
    task = parse(path.read_bytes())
    source = admin.post(
        BASE + "/praxis-sources",
        json={"payload": path.read_text()},
        headers={"Idempotency-Key": uid()},
    ).json()["data"]
    value = bundle(task)
    value["code"] = value["code"].replace("data['max_channel_percent']", "70")
    for case in value["fixtures"]:
        if case["id"] == "M-OVER-LIMIT":
            wrong_case = dict(
                case["output"], allocation_cents={"search": 700001, "linkedin": 99999}
            )
            case["output"] = wrong_case
            for action in case["observed_calls"]:
                if action["tool"] == "save_result":
                    action["arguments"]["output"] = wrong_case
    post(admin, "/tasks/" + source["id"] + "/generate")
    process(claim(PROJECT), transport=mock_provider(value, []))
    result = admin.get(BASE + "/workspace/tasks/" + source["id"] + "/executable-import").json()[
        "data"
    ]
    assert result["revisions"][0]["state"] == "validation_failed"
    assert "Source QA expected/actual mismatch" in result["revisions"][0]["report"]["error"]
