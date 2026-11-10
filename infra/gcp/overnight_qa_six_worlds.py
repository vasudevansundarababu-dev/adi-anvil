"""Actual QA API/worker six-world technical rehearsal; zero model performance."""

import argparse
import importlib.util
import json
import socket
import ssl
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--harness",
        choices=("local-components-v1", "openenv-0.12-local-v1", "harbor-host-mediated-v1"),
        default="local-components-v1",
    )
    parser.add_argument("--role", choices=("admin", "rl-engineer"))
    args = parser.parse_args()
    assert socket.gethostname() == "anvil-overnight-qa-20261110"
    root = Path("/var/lib/anvil-overnight-qa")
    fixture = json.loads((root / "synthetic-oidc-test-fixture.json").read_text())
    assert fixture["origin"] == "synthetic_oidc_protocol_qa_only"
    spec = importlib.util.spec_from_file_location(
        "qa_oidc", "/home/vasudevan_sundarababu_adi_labs_a/qa-oidc-protocol.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    web = "https://anvil-qa.127.0.0.1.sslip.io:8443"
    auth = "https://auth-anvil-qa.127.0.0.1.sslip.io:8443"
    verify = ssl.create_default_context(cafile=str(root / "config/qa-root-ca.crt"))
    receipts = []
    for role, identity in fixture["users"].items():
        if args.role and role != args.role:
            continue
        with httpx.Client(
            verify=verify, trust_env=False, follow_redirects=False, timeout=30
        ) as client:
            start = client.get(web + "/api/v1/auth/login")
            assert start.headers["location"].startswith(auth + "/realms/")
            form = module.Form()
            form.feed(client.get(start.headers["location"]).text)
            assert form.action.startswith(auth + "/realms/anvil-overnight-qa/")
            response = client.post(
                form.action,
                data={
                    "username": identity["username"],
                    "password": identity["password"],
                    "credentialId": "",
                },
            )
            assert response.headers["location"].startswith(web + "/api/v1/auth/callback?")
            assert client.get(response.headers["location"]).status_code in (302, 307)
            prefix = web + f"/api/v1/projects/{fixture['project']}/workspace"
            envs, bench = prefix + "/environments", prefix + "/benchmark"

            def post(url, body=None):
                response = client.post(
                    url,
                    json=body,
                    headers={
                        "origin": web,
                        "x-csrf-token": client.cookies.get("anvil_csrf"),
                        "idempotency-key": uuid4().hex,
                    },
                )
                assert response.status_code == 200, (
                    f"QA API failed {url.rsplit('/', 1)[-1]} HTTP{response.status_code}"
                )
                return response.json()["data"]

            group = client.get(bench).json()["data"]["groups"][0]
            task = group["tasks"][0]
            templates = client.get(envs).json()["data"]["templates"]
            assert len(templates) == 6
            members = []
            for template in templates:
                pack = post(
                    envs + "/packs/generate",
                    {"template": template["id"], "scenario": template["scenarios"][0]},
                )
                version = post(
                    envs + "/versions",
                    {
                        "pack_id": pack["id"],
                        "name": "Cloud QA technical " + role + " " + template["id"],
                    },
                )
                post(envs + f"/versions/{version['id']}/validate")
                post(envs + f"/versions/{version['id']}/register")
                members.append(
                    {
                        "environment_id": version["id"],
                        "task_id": task["task_id"],
                        "source_environment_id": task["environment_ids"][0],
                        "actions": [
                            {
                                "operation": "list_records",
                                "arguments": {"collection": template["collections"][0]},
                            }
                        ],
                    }
                )
            plan = post(
                envs + "/execution-plans",
                {
                    "name": "Actual QA six-world technical " + role,
                    "task_group_id": group["id"],
                    "members": members,
                    "candidates": ["configured-tools-v1", "empty-tools-v1"],
                    "purpose": "technical_rehearsal",
                    "harness": args.harness,
                },
            )
            run = post(
                bench + "/runs",
                {"plan_id": plan["id"], "expected_plan_sha256": plan["snapshot_sha256"]},
            )
            (root / ("six-worlds-" + args.harness + "-dispatch-public.json")).write_text(
                json.dumps(
                    {
                        "role": role,
                        "run_id": run["id"],
                        "harness": args.harness,
                        "status": "dispatched_no_automatic_retry",
                    }
                )
            )
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                result = client.get(bench + "/runs/" + run["id"]).json()["data"]
                if result["run"]["state"] in {"completed", "failed", "blocked", "cancelled"}:
                    break
                time.sleep(1)
            assert result["run"]["state"] == "completed", "Actual QA durable Run did not complete"
            assert len(result["cells"]) == 12
            assert result["failures"]["cells"] == 0
            if args.harness == "openenv-0.12-local-v1":
                assert result["selected_cell"]["capture"]["openenv_adapter"]["version"] == "0.12.0"
            assert (
                result["run"]["provider_calls"] == 0 and result["run"]["model_performance"] is False
            )
            assert all(cell["assessment"]["earned_points"] is None for cell in result["cells"])
            item = {
                "harness": args.harness,
                "role": role,
                "run_id": run["id"],
                "cells": 12,
                "templates": 6,
                "provider_calls": 0,
                "model_performance": False,
                "task_scoring": "not_evaluated",
                "report_review": result["run"]["report_review"],
            }
            receipts.append(item)
            (root / ("six-worlds-" + args.harness + "-public.json")).write_text(
                json.dumps(
                    {
                        "runs": receipts,
                        "test": "actual_https_api_and_durable_worker",
                        "real_source_bindings": False,
                    }
                )
            )
            if role == "admin":
                for format in ("json", "pdf"):
                    export = client.get(
                        bench + "/runs/" + run["id"] + "/export",
                        params={"format": format, "expected_view_sha256": result["view_sha256"]},
                    )
                    assert export.status_code == 200
                    (root / ("six-world-admin-" + args.harness + "." + format)).write_bytes(
                        export.content
                    )
    print(
        json.dumps(
            {
                "actual_runs": len(receipts),
                "cells": sum(r["cells"] for r in receipts),
                "provider_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
