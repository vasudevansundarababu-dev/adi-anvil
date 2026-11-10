"""Six exact owner-authorized smoke groups, $1 each; no ambiguous retry.

Uses public fictional Task inputs and existing authenticated Admin Run controls.
Draft source status is preserved. Never creates human/source/package approvals.
"""

import json
import ssl
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from overnight_qa_bind_staged_credentials import AUTH, OPERATOR, WEB, Form

MODELS = (("openai", "gpt-6.1-sol"), ("openai", "gpt-6-luna"),
          ("anthropic", "claude-fable-5-2"), ("anthropic", "claude-opus-5-5"),
          ("gemini", "gemini-4-argon"), ("gemini", "gemini-3.8-flash"))
RECEIPT = OPERATOR / "real-model-smoke-public.json"


def main(action):
    assert datetime.now(timezone.utc) < datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
    fixture = json.loads((OPERATOR / "browser-synthetic-fixture.json").read_text())
    assert fixture["origin"] == "synthetic_oidc_protocol_qa_only"
    project = "b3337332-aff7-4041-93f8-6adf9ca276d3"
    assert fixture["project"] == project
    bindings = json.loads((OPERATOR / "credential-bindings-public.json").read_text())
    credentials = {v["provider"]: v for v in bindings["credentials"]}
    verify = ssl.create_default_context(cafile=str(OPERATOR / "qa-root-ca.crt"))
    with httpx.Client(verify=verify, trust_env=False, follow_redirects=False, timeout=30) as client:
        response = client.get(WEB + "/api/v1/auth/login")
        assert response.headers["location"].startswith(AUTH + "/realms/")
        form = Form()
        form.feed(client.get(response.headers["location"]).text)
        assert form.action.startswith(AUTH + "/realms/anvil-overnight-qa/")
        identity = fixture["users"]["admin"]
        response = client.post(form.action, data={"username": identity["username"], "password": identity["password"], "credentialId": ""})
        assert response.headers["location"].startswith(WEB + "/api/v1/auth/callback?")
        assert client.get(response.headers["location"]).status_code in (302, 307)
        endpoint = WEB + f"/api/v1/projects/{project}/workspace"

        def get(path):
            response = client.get(endpoint + path)
            assert response.status_code == 200, "QA API GET HTTP " + str(response.status_code)
            return response.json()["data"]

        def post(path, body, *, version=None):
            headers = {"origin": WEB, "x-csrf-token": client.cookies.get("anvil_csrf"), "idempotency-key": uuid4().hex}
            if version is not None:
                headers["if-match"] = str(version)
            response = client.post(endpoint + path, json=body, headers=headers)
            if response.status_code != 200:
                # API admission details contain no credential/session material.
                if response.status_code == 409:
                    print(json.dumps({"blocked_path": path, "admission": response.json().get("error", response.json().get("detail"))}))
                raise ValueError("QA API POST HTTP " + str(response.status_code))
            return response.json()["data"]

        if action == "prepare":
            assert not RECEIPT.exists(), "Existing smoke receipt requires reconciliation"
            current = get("/models?limit=100")["items"]
            selected = []
            for provider, model in MODELS:
                old = next(v for v in current if v["name"] == "Overnight QA " + model and v["is_current"])
                credential = credentials[provider]
                item = post("/models/" + old["id"] + "/versions", {"name": old["name"], "provider": provider, "model_id": model, "max_output_tokens": 2048, "credential_id": credential["credential_id"], "credential_version_id": credential["version_id"], "processing_terms_reviewed": False}, version=old["profile_row_version"])
                assert item["credential_present"] and item["model_id"] == model
                selected.append(item)
            frameworks = get("/frameworks")["items"]
            runner = next((v for v in frameworks if v["framework"] == "harbor" and v["config"].get("runtime_version") == "0.25.0"), None)
            if runner is None:
                runner = post("/frameworks", {"name": "Owner QA Harbor 0.25.0", "framework": "harbor", "runtime_version": "0.25.0"})
            preset = post("/presets", {"name": "Owner authorized six-model smoke, no human source review", "runner_profile_id": runner["id"], "candidate_runtime": "anvil-structured-json-v1", "model_profile_ids": [v["id"] for v in selected]})
            package = get("/packages?task_id=SEED-PHONE-001")["items"]
            assert len(package) == 1 and package[0]["manifest"]["binding"] == "structured-decision-v1"
            receipt = {"project": project, "task": "SEED-PHONE-001", "source_status": "fictional_draft_no_human_review", "initial_smoke_cap_micro_usd": 10000000, "allocated_micro_usd": 6000000, "source_approvals_created": 0, "groups": []}
            RECEIPT.write_text(json.dumps(receipt))
            for item in selected:
                prep = post("/preparations", {"preset_id": preset["id"], "package_id": package[0]["id"], "model_profile_ids": [item["id"]], "max_output_tokens": 2048, "episode_timeout_seconds": 180, "aggregate_cap_micro_usd": 1000000, "trials_per_model": 1, "max_agent_steps": 1})
                group = post("/execution-groups", {"preparation_id": prep["id"]})
                receipt["groups"].append({"id": group["id"], "subject_hash": group["subject_hash"], "model": item["model_id"], "provider": item["provider"], "cap_micro_usd": 1000000, "launch_attempted": False, "readiness": group["readiness"]})
                RECEIPT.write_text(json.dumps(receipt))
            print(json.dumps(receipt))
        else:
            receipt = json.loads(RECEIPT.read_text())
            assert len(receipt["groups"]) == 6 and sum(v["cap_micro_usd"] for v in receipt["groups"]) == 6000000
            for entry in receipt["groups"]:
                if action == "launch":
                    assert entry["launch_attempted"] is False, "No repeated launch after uncertain outcome"
                    entry["launch_attempted"] = True
                    RECEIPT.write_text(json.dumps(receipt))
                    group = post("/execution-groups/" + entry["id"] + "/launch", {"subject_hash": entry["subject_hash"], "aggregate_cap_micro_usd": entry["cap_micro_usd"], "rights_confirmed": True})
                else:
                    group = get("/execution-groups/" + entry["id"])
                entry["status"] = group["status"]
                entry["readiness"] = group["readiness"]
                entry["results"] = group["models"]
                RECEIPT.write_text(json.dumps(receipt))
            print(json.dumps(receipt))


if __name__ == "__main__":
    import sys
    try:
        assert sys.argv[1] in {"prepare", "launch", "status"}
        main(sys.argv[1])
    except Exception as error:
        detail = str(error) if type(error) is ValueError else type(error).__name__
        raise SystemExit("QA smoke did not complete: " + detail) from None
