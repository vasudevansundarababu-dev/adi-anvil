"""MANUFACTURED isolated SQL prerequisites, never QA publication/qualification.

Port of tests/benchmark/kyc_policy_synthetic_source.py. Inserts synthetic template
publication/conformance and review prerequisites with real constraints enabled;
these assertions are assumptions for reader software tests, not evidence of
publication, human approval, installed runtime qualification or run authority.
"""

from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from anvil.db import digest as stored_digest
from anvil.golden_kyc_anvil import register, validate_software
from anvil.golden_kyc_resolved_store import policy_scope
from anvil.praxis_capabilities import catalogue
from anvil.praxis_generic_contract import canonical, digest
from anvil.praxis_template_registry import source_hash

PRODUCTS = ("individual", "adult_joint", "teen_joint", "custodial")
STATES = ("CA", "NY", "TX", "FL", "IL")


def require(condition):
    if not condition:
        raise ValueError("Synthetic four-product import fixture refused")


def source(c, owned, runtime_source, reference, *, runtime_image):
    project, user = owned[1:3]
    c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (project, user))
    c.execute("SET LOCAL ROLE anvil_app")
    apps = c.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
                     (project, owned[4])).fetchall()
    imported = register(c, project, user, owned[4], application_types=True)
    imp = c.execute("SELECT * FROM banking.anvil_imports WHERE project_id=%s AND id=%s", (project, imported["id"])).fetchone()
    validate_software(c, imp)
    group = c.execute("SELECT content,content_sha256 FROM anvil.benchmark_task_groups WHERE project_id=%s AND id=%s",
                      (project, imp["task_group_id"])).fetchone()
    actual_tasks = group["content"]["tasks"]
    by_product = {task["actor"].get("workflow_product"): task for task in actual_tasks}
    evaluators, assignments = imp["manifest"]["evaluators"], imp["manifest"]["case_assignments"]
    original = {app["id"]: app for app in apps}
    require(imp["manifest"]["task_mode"] == "reusable_application_workflow" and imp["manifest"]["source_sha256"] == runtime_source
        and len(actual_tasks) == 4 and set(by_product) == set(PRODUCTS) and len({task["task_version"] for task in actual_tasks}) == 1
        and stored_digest(group["content"]) == group["content_sha256"] == imp["manifest"]["task_group_sha256"]
        and len(evaluators) == len({item["configuration_id"] for item in evaluators}) == 50
        and all(task["rubric"] == actual_tasks[0]["rubric"] and len(task["rubric"]["criteria"]) == 20 for task in actual_tasks)
        and len(assignments) == len(original) == len(apps) == imp["manifest"]["case_dataset"]["case_count"]
        and len({item["application_id"] for item in assignments}) == len(apps)
        and {item["application_id"] for item in assignments} == set(original)
        and {(app["snapshot"]["product"], app["snapshot"]["governing_state"]) for app in apps} == {(product, state) for product in PRODUCTS for state in STATES})
    for item in assignments:
        app = original[item["application_id"]]
        require(stored_digest(app["snapshot"]) == app["snapshot_sha256"] == item["application_sha256"]
            and item["product"] == app["snapshot"]["product"] and item["governing_state"] == app["snapshot"]["governing_state"]
            and item["task_id"] == by_product[item["product"]]["task_id"])
    environment_rows = c.execute("SELECT * FROM anvil.environment_task_bindings WHERE project_id=%s AND environment_id=%s AND task_group_id=%s",
        (project, imp["environment_id"], imp["task_group_id"])).fetchall()
    require(len(environment_rows) == 4 and {row["task_id"] for row in environment_rows} == {task["task_id"] for task in actual_tasks})
    actual_bindings = {row["task_id"]: row for row in environment_rows}
    for product, task in by_product.items():
        row = actual_bindings[task["task_id"]]
        require(row["task_version"] == task["task_version"] and stored_digest(row["snapshot"]) == row["snapshot_sha256"]
            and row["snapshot"]["task_payload_sha256"] == task["payload_sha256"] and row["snapshot"]["evaluators"] == evaluators
            and row["snapshot"]["case_selector"] == {"field": "product", "value": product, "case_count": sum(item["product"] == product for item in assignments)})
    require(apps == c.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
        (project, owned[4])).fetchall())
    c.execute("RESET ROLE")
    template_id, qualification_id, resolution_id, archive_id, binding_id, input_id = (uuid4() for _ in range(6))
    catalogue_version = "1.0.0"  # Same pinned synthetic fixture catalogue, not a published task.
    spec = {"template_id": str(template_id), "version": 8,
            "authoring": {"template": {"caseSelector": {"field": "product"}}},
            "execution": {"schema_version": "anvil.template-execution.v2", "catalogue_version": catalogue_version,
                          "environment": {"id": "synthetic-policy-sql-only"}, "federalPolicies": [reference]},
            "skills": {}, "synthetic_only": "not-published-not-QA"}
    parts = {key: digest(spec[key]) for key in ("authoring", "execution", "skills")}
    catalog_hash = catalogue(catalogue_version)["sha256"]
    c.execute("INSERT INTO anvil.praxis_template_versions(id,project_id,template_key,version,spec,spec_sha256,part_hashes,catalogue_sha256,created_by) "
              "VALUES(%s,%s,%s,8,%s,%s,%s,%s,%s)",
              (template_id, project, str(template_id), Jsonb(spec), digest(spec), Jsonb(parts), catalog_hash, user))
    receipt = {"source_sha256": source_hash(), "template_sha256": digest(spec), "part_hashes": parts,
               "catalogue_sha256": catalog_hash, "publication_verified": True,
               "conformance": {"passed": True, "export_selector_field": "product", "origin": "synthetic-isolated-sql-not-QA"}}
    c.execute("INSERT INTO anvil.praxis_template_qualifications(id,project_id,template_id,receipt,receipt_sha256,status,created_by) "
              "VALUES(%s,%s,%s,%s,%s,'qualified',%s)",
              (qualification_id, project, template_id, Jsonb(receipt), digest(receipt), user))
    c.execute("INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin) "
              "VALUES(%s,%s,%s,%s,0,'application/zip','hidden_reference','clean','synthetic-sql-only')",
              (archive_id, project, str(archive_id), "a" * 64))
    c.execute("INSERT INTO anvil.praxis_export_resolutions(id,project_id,package_key,version,package_sha256,batch_key,part_index,part_count,private_archive_id,receipt,receipt_sha256,created_by) "
              "VALUES(%s,%s,%s,'synthetic-v1',%s,%s,0,1,%s,%s,%s,%s)",
              (resolution_id, project, str(resolution_id), "b" * 64, str(resolution_id), archive_id, Jsonb({}), digest({}), user))
    snapshot = {"source_sha256": group["content_sha256"], "synthetic_only": "not-QA",
        "golden_reference_import_id": str(imp["id"]), "golden_import_manifest_sha256": imp["manifest_sha256"]}
    c.execute("INSERT INTO anvil.project_binding_versions(id,project_id,task_group_id,version,snapshot,snapshot_sha256,created_by) "
              "VALUES(%s,%s,%s,1,%s,%s,%s)",
              (binding_id, project, imp["task_group_id"], Jsonb(snapshot), stored_digest(snapshot), user))
    tasks = []
    for product in PRODUCTS:
        task = by_product[product]
        task_key, revision, actor = task["task_id"], task["task_version"], task["actor"]
        original_binding = actual_bindings[task_key]
        binding = {"qualification_id": str(qualification_id), "qualification_sha256": digest(receipt),
            "source_sha256": receipt["source_sha256"], "actor_sha256": digest(actor), "task_mode": "reusable_application_workflow",
            "case_selector": {"field": "product", "value": product},
            "environment_task_binding": {"id": str(original_binding["id"]), "sha256": original_binding["snapshot_sha256"]}}
        c.execute("INSERT INTO anvil.praxis_resolved_tasks(id,project_id,resolution_id,template_id,task_key,revision,actor,actor_sha256,private_reference_sha256,binding,binding_sha256,created_by) "
                  "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  (uuid4(), project, resolution_id, template_id, task_key, revision, Jsonb(actor), digest(actor), task["payload_sha256"],
                   Jsonb(binding), digest(binding), user))
        tasks.append({"task_id": task_key, "revision_id": revision, "actor_sha256": digest(actor),
                      "private_reference_sha256": task["payload_sha256"], "review_receipt_sha256": "e" * 64,
                      "case_selector": binding["case_selector"], "template": {"id": str(template_id), "version": 8, "sha256": digest(spec)},
                      "template_qualification_receipt_sha256": digest(receipt)})
    rows = [{"application_id": item["application_id"], "application_sha256": item["application_sha256"], "product": item["product"],
        "governing_state": item["governing_state"], "task_id": item["task_id"], "revision_id": by_product[item["product"]]["task_version"],
        "status": "assigned_pending_policy_and_runtime_qualification"} for item in assignments]
    body = {"schema_version": "anvil.private-kyc-resolved-input.v1", "runtime_qualified": False,
            "policy_qualified": False, "run_authority": "not_granted", "scope": {
                "project_id": project, "project_binding_id": str(binding_id), "project_binding_sha256": stored_digest(snapshot),
                "runtime_source_sha256": runtime_source, "runtime_image_sha256": runtime_image,
                "environment_binding_sha256": imp["manifest"]["environment_manifest_sha256"], "evaluator_bindings_sha256": digest(evaluators)},
            "source_package_sha256": "b" * 64, "case_dataset": imp["manifest"]["case_dataset"],
            "input_count": len(rows), "rows": rows, "tasks": tasks, "source_anvil_requirements": []}
    c.execute("INSERT INTO anvil.kyc_resolved_input_versions(id,project_id,resolution_id,project_binding_id,case_import_id,body_canonical,content_sha256,created_by) "
              "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
              (input_id, project, resolution_id, binding_id, imp["id"], canonical(body).decode(), digest(body), user))
    return policy_scope(c, UUID(project), input_id, by_product["individual"]["task_id"], by_product["individual"]["task_version"])
