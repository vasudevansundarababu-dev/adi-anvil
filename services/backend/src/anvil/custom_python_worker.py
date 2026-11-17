"""SQL scheduler/private filesystem coordinator split for once-only Python tests."""

import os
import re
import time
from pathlib import Path
from uuid import UUID

from anvil.db import Jsonb, digest
from anvil.golden_native_bridge import owned_json, private_root, publish


def scheduler_once(connections, root, *, seconds=60):
    if not 1 <= seconds <= 120:
        raise ValueError("Bounded custom Python job wait required")
    root = private_root(Path(root))
    with connections() as c:
        job = c.execute("SELECT anvil.claim_custom_python_job() AS job").fetchone()["job"]
    if job is None:
        return None
    if digest(job["request"]) != job["request_sha256"]:
        raise RuntimeError("custom_python_input_hash_changed_no_replay")
    attempt = root / UUID(job["id"]).hex
    attempt.mkdir(mode=0o700)
    publish(
        attempt / "request.json",
        {
            "id": job["id"],
            "project_id": job["project_id"],
            "request": job["request"],
            "request_sha256": job["request_sha256"],
        },
    )
    deadline = time.monotonic() + seconds
    while not (attempt / "result.json").exists():
        if time.monotonic() >= deadline:
            # Unknown physical execution is not replayed or marked successful.
            raise RuntimeError("custom_python_completion_unconfirmed_no_replay")
        time.sleep(0.05)
    record = owned_json(attempt, "result.json")
    if record.get("request_sha256") != job["request_sha256"] or digest(
        record.get("result")
    ) != record.get("result_sha256"):
        raise RuntimeError("custom_python_result_custody_changed")
    with connections() as c:
        if not c.execute(
            "SELECT anvil.finish_custom_python_job(%s,%s,%s,%s) AS ok",
            (job["id"], job["claim_token"], Jsonb(record["result"]), record["result_sha256"]),
        ).fetchone()["ok"]:
            raise RuntimeError("custom_python_finish_denied_no_replay")
    return {"id": job["id"], "result_sha256": record["result_sha256"]}


def coordinator_once(root, *, host):
    from anvil.custom_python_executor import execute

    if any(
        v and ("DATABASE" in k or k.endswith("API_KEY") or k.endswith("PRIVATE_KEY"))
        for k, v in os.environ.items()
    ):
        raise RuntimeError("Custom coordinator must not receive SQL/provider secrets")
    root = private_root(Path(root))
    for path in sorted(root.iterdir()):
        if not re.fullmatch(r"[a-f0-9]{32}", path.name):
            continue
        attempt = private_root(path)
        if not (attempt / "request.json").exists() or (attempt / "claimed.json").exists():
            continue
        try:
            os.link(attempt / "request.json", attempt / "claimed.json")
        except FileExistsError:
            continue
        request = owned_json(attempt, "request.json")
        if (
            set(request) != {"id", "project_id", "request", "request_sha256"}
            or UUID(request["id"]).hex != path.name
            or digest(request["request"]) != request["request_sha256"]
        ):
            raise RuntimeError("custom_python_claimed_request_invalid_no_replay")
        home = attempt / "executor"
        home.mkdir(mode=0o700)
        try:
            result = execute(home, request["request"], host=host)
        except Exception as exc:
            result = {
                "execution_error": type(exc).__name__,
                "passed": False,
                "deployment_qualified": False,
                "model_calls": 0,
            }
        publish(
            attempt / "result.json",
            {
                "request_sha256": request["request_sha256"],
                "result": result,
                "result_sha256": digest(result),
            },
        )
        return {"id": request["id"], "result_sha256": digest(result)}
    return None
