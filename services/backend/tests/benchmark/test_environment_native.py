"""Opt-in real Harbor0.25 local lifecycle; never a vendor model benchmark."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.encoders import jsonable_encoder
from test_private_storage import connection
from test_private_storage import lab as storage_lab

from anvil import environment_runtime as runtime
from anvil import environment_seeds as seeds
from anvil.environment_collect import verify_receipt
from anvil.environment_harbor import execute

lab = storage_lab
pytestmark = pytest.mark.skipif(
    os.environ.get("ANVIL_ENVIRONMENT_NATIVE_ENABLED") != "true",
    reason="Explicit dedicated native test scope required",
)


@pytest.mark.parametrize("template", list(seeds.CATALOG))
def test_actual_native_harbor_collector_separate_verifier_for_each_seed(lab, template):
    root = Path(tempfile.mkdtemp(prefix="anvil-native-seed-", dir="/private/tmp"))
    with connection("anvil_app", lab["project"], lab["admin"]) as c:
        config = seeds.CATALOG[template]
        pack = runtime.pack_store(
            c, lab["project"], lab["admin"], seeds.generate(template, config["scenarios"][0])
        )
        version = runtime.create_version(
            c, lab["project"], lab["admin"], pack["id"], "Native " + template
        )
        instance = runtime.create_instance(c, lab["project"], lab["admin"], version["id"])

        def actor():
            result = runtime.execute(
                c,
                lab["admin"],
                instance["id"],
                "list_records",
                {"collection": config["collections"][0]},
                0,
            )
            receipt = runtime.export_evidence(c, lab["admin"], instance["id"])
            verify_receipt(
                receipt,
                {
                    "environment_manifest_sha256": version["manifest_sha256"],
                    "pack_sha256": pack["content_sha256"],
                },
                instance["id"],
            )
            return {"actual_tool_result": result}, receipt

        result = execute(
            root / "attempt",
            {"template": template, "origin": "synthetic_reference_software"},
            actor,
            host=os.environ["ANVIL_HARBOR_DOCKER_HOST"],
            python=os.environ["ANVIL_ENVIRONMENT_HARBOR_PYTHON"],
        )
        assert (
            result["collection"]["complete"]
            and result["provider_calls"] == 0
            and result["task_score"] is None
        )
        assert (
            result["native_container_isolation"]
            and result["business_components_location"] == "trusted_host_postgres"
        )
        runtime.close(c, lab["admin"], instance["id"])
        (root / "public-evidence.json").write_text(json.dumps(jsonable_encoder(result), indent=2))
        print("Actual native evidence:", root / "public-evidence.json")
