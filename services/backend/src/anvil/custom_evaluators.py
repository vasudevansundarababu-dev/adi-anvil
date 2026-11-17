"""Actual Python evaluator programs and durable isolated-test jobs; no API exec."""

import hashlib
import os
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from anvil import auth
from anvil.custom_python_executor import source_hash, validate_request
from anvil.db import Jsonb, audit, digest, one, uid
from anvil.native_image_profile import IMAGE_ID
from anvil.schemas import Strict


class Create(Strict):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=16384)


class Case(Strict):
    actual: Any
    expected: Any
    expected_status: Literal["pass", "partial", "fail", "unscored"]


class Tests(Strict):
    cases: list[Case] = Field(min_length=1, max_length=30)


class Preview(Tests):
    code: str = Field(min_length=1, max_length=16384)


def validate(code, cases):
    request = {"code": code, "cases": cases}
    try:
        validate_request(request)
    except SyntaxError as exc:
        raise HTTPException(
            422,
            {
                "code": "custom_python_syntax_error",
                "line": exc.lineno,
                "column": exc.offset,
                "message": "Fix Python syntax at the indicated line and column.",
                "fix": "Define evaluate(actual, expected) and correct the Python syntax; source text and input values are not included in this error.",
            },
        ) from exc
    except (ValueError, TypeError, RecursionError) as exc:
        raise HTTPException(
            422,
            {
                "code": "invalid_custom_python",
                "message": "Use evaluate(actual, expected), bounded Python source and JSON test cases.",
                "fix": "Supply1–30JSONcases, source<=16384UTF8bytes and total request<=49152bytes; return status pass, partial, fail or unscored.",
            },
        ) from exc
    return request


def get(c, identifier, include_code=False):
    row = one(c, "SELECT * FROM anvil.custom_python_evaluators WHERE id=%s", (identifier,))
    if not row:
        raise HTTPException(404, "Custom Python evaluator not found in this project")
    revoked = one(
        c, "SELECT 1 FROM anvil.custom_python_revocations WHERE evaluator_id=%s", (identifier,)
    )
    tested = one(
        c,
        "SELECT id,request,result,result_sha256 FROM anvil.custom_python_jobs WHERE evaluator_id=%s AND state='completed' ORDER BY finished_at DESC,id DESC LIMIT 1",
        (identifier,),
    )
    valid = (
        tested
        and digest(tested["result"]) == tested["result_sha256"]
        and hashlib.sha256(tested["request"]["code"].encode()).hexdigest() == row["code_sha256"]
        and tested["result"].get("source_sha256") == source_hash()
        and tested["result"].get("image_id") == IMAGE_ID
        and tested["result"].get("passed") is True
        and tested["result"].get("control_coverage_complete") is True
    )
    result = {
        "id": row["id"],
        "name": row["name"],
        "kind": "custom_python",
        "sha256": row["code_sha256"],
        "status": "revoked" if revoked else "tested" if valid else "needs_isolated_testing",
        "deployment_qualified": False,
        "can_bind_for_scoring": False,
        "can_select_for_binding": not bool(revoked),
        "binding_reason": "Save an exact rubric-target selection; independent source/image/target qualification is required before scoring admission",
        "test_job_id": str(tested["id"]) if tested else None,
    }
    if include_code:
        result["code"] = row["code"]
    return result


def queue(c, project, user, code, cases, evaluator_id=None):
    request = validate(code, cases)
    if os.environ.get("ANVIL_CUSTOM_PYTHON_ENABLED") != "true":
        raise HTTPException(
            409,
            {
                "code": "isolated_python_worker_not_enabled",
                "owner": "anvil",
                "message": "Configure and enable the isolated Python worker; API execution is prohibited and deployment qualification remains separate.",
            },
        )
    pending = one(
        c, "SELECT count(*) AS n FROM anvil.custom_python_jobs WHERE state IN('queued','claimed')"
    )
    if pending["n"] >= 20:
        raise HTTPException(
            409,
            {
                "code": "custom_python_queue_capacity",
                "owner": "anvil",
                "message": "This project already has20 pending tests; finish or reconcile them before adding another.",
            },
        )
    identifier = uid()
    c.execute(
        "INSERT INTO anvil.custom_python_jobs(id,project_id,evaluator_id,request,request_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
        (identifier, project, evaluator_id, Jsonb(request), digest(request), user),
    )
    audit(
        c,
        project,
        user,
        "custom_python.test_queued",
        identifier,
        {"request_sha256": digest(request)},
    )
    return {
        "job_id": identifier,
        "state": "queued",
        "deployment_qualified": False,
        "model_calls": 0,
    }


def routes(context, wrap, idempotent):
    router = APIRouter(prefix="/api/v1/projects/{project}/workspace/custom-evaluators")

    @router.get("")
    def listing(project: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            return wrap(
                {
                    "items": [
                        get(c, r["id"])
                        for r in c.execute(
                            "SELECT id FROM anvil.custom_python_evaluators ORDER BY created_at DESC,id LIMIT 100"
                        ).fetchall()
                    ],
                    "language": "python",
                    "execution_location": "isolated_coordinator_container",
                },
                request,
            )

    @router.post("/preview")
    def preview(project: UUID, body: Preview, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            return wrap(
                idempotent(
                    c,
                    project,
                    user,
                    request,
                    body,
                    lambda: queue(
                        c, project, user, body.code, [v.model_dump() for v in body.cases]
                    ),
                ),
                request,
            )

    @router.post("")
    def create(project: UUID, body: Create, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")

            def save():
                validate(
                    body.code, [{"actual": None, "expected": None, "expected_status": "unscored"}]
                )
                identifier = uid()
                c.execute(
                    "INSERT INTO anvil.custom_python_evaluators(id,project_id,name,code,code_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
                    (
                        identifier,
                        project,
                        body.name,
                        body.code,
                        hashlib.sha256(body.code.encode()).hexdigest(),
                        user,
                    ),
                )
                audit(c, project, user, "custom_python.created", identifier)
                return get(c, identifier)

            return wrap(idempotent(c, project, user, request, body, save), request)

    @router.get("/jobs/{identifier}")
    def job(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            row = one(
                c,
                "SELECT id,evaluator_id,state,result,result_sha256,created_at,finished_at FROM anvil.custom_python_jobs WHERE id=%s",
                (identifier,),
            )
            if not row:
                raise HTTPException(404, "Custom Python job not found")
            if row["result"] is not None and digest(row["result"]) != row["result_sha256"]:
                raise HTTPException(409, "Custom Python result integrity check failed")
            return wrap(row, request)

    @router.get("/{identifier}")
    def retrieve(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            return wrap(get(c, identifier, include_code=True), request)

    @router.post("/{identifier}/test")
    def test(project: UUID, identifier: UUID, body: Tests, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")

            def save():
                evaluator = get(c, identifier, include_code=True)
                if evaluator["status"] == "revoked":
                    raise HTTPException(409, "Revoked evaluator cannot be retested/reactivated")
                return queue(
                    c,
                    project,
                    user,
                    evaluator["code"],
                    [v.model_dump() for v in body.cases],
                    identifier,
                )

            return wrap(idempotent(c, project, user, request, body, save), request)

    @router.post("/{identifier}/revoke")
    def revoke(project: UUID, identifier: UUID, request: Request):
        with context(request, project) as (c, user, roles):
            auth.require(roles, "admin", "rl-engineer")
            get(c, identifier)
            c.execute(
                "INSERT INTO anvil.custom_python_revocations(id,project_id,evaluator_id,created_by) VALUES(%s,%s,%s,%s) ON CONFLICT(evaluator_id) DO NOTHING",
                (uid(), project, identifier, user),
            )
            audit(c, project, user, "custom_python.revoked", identifier)
            return wrap(get(c, identifier), request)

    return router
