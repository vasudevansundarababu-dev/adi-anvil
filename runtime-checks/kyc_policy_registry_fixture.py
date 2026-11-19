"""MANUFACTURED isolated SQL prerequisites, never QA publication/qualification.

Port of tests/benchmark/kyc_policy_synthetic_source.py. Inserts synthetic template
publication/conformance and review prerequisites with real constraints enabled;
these assertions are assumptions for reader software tests, not evidence of
publication, human approval, installed runtime qualification or run authority.
"""

from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from anvil.db import digest as stored_digest
from anvil.golden_kyc_anvil import register
from anvil.golden_kyc_resolved_store import policy_scope
from anvil.praxis_capabilities import catalogue
from anvil.praxis_generic_contract import canonical, digest
from anvil.praxis_template_registry import source_hash


def source(c, owned, runtime_source, reference, *, runtime_image):
    project, user = owned[1:3]
    c.execute("SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)", (project, user))
    c.execute("SET LOCAL ROLE anvil_app")
    imported = register(c, project, user, owned[4], reusable=True)
    c.execute("RESET ROLE")
    imp = c.execute("SELECT * FROM banking.anvil_imports WHERE id=%s", (imported["id"],)).fetchone()
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
               "conformance": {"passed": True, "origin": "synthetic-isolated-sql-not-QA"}}
    c.execute("INSERT INTO anvil.praxis_template_qualifications(id,project_id,template_id,receipt,receipt_sha256,status,created_by) "
              "VALUES(%s,%s,%s,%s,%s,'qualified',%s)",
              (qualification_id, project, template_id, Jsonb(receipt), digest(receipt), user))
    c.execute("INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin) "
              "VALUES(%s,%s,%s,%s,0,'application/zip','hidden_reference','clean','synthetic-sql-only')",
              (archive_id, project, str(archive_id), "a" * 64))
    c.execute("INSERT INTO anvil.praxis_export_resolutions(id,project_id,package_key,version,package_sha256,batch_key,part_index,part_count,private_archive_id,receipt,receipt_sha256,created_by) "
              "VALUES(%s,%s,%s,'synthetic-v1',%s,%s,0,1,%s,%s,%s,%s)",
              (resolution_id, project, str(resolution_id), "b" * 64, str(resolution_id), archive_id, Jsonb({}), digest({}), user))
    snapshot = {"source_sha256": "c" * 64, "synthetic_only": "not-QA"}
    c.execute("INSERT INTO anvil.project_binding_versions(id,project_id,task_group_id,version,snapshot,snapshot_sha256,created_by) "
              "VALUES(%s,%s,%s,1,%s,%s,%s)",
              (binding_id, project, imp["task_group_id"], Jsonb(snapshot), stored_digest(snapshot), user))
    tasks = []
    for product in ("individual", "adult_joint", "teen_joint", "custodial"):
        task_key = "synthetic-policy-" + product
        actor, binding = {"synthetic_only": True}, {"qualification_id": str(qualification_id),
            "case_selector": {"field": "product", "value": product}}
        c.execute("INSERT INTO anvil.praxis_resolved_tasks(id,project_id,resolution_id,template_id,task_key,revision,actor,actor_sha256,private_reference_sha256,binding,binding_sha256,created_by) "
                  "VALUES(%s,%s,%s,%s,%s,'synthetic-r8',%s,%s,%s,%s,%s,%s)",
                  (uuid4(), project, resolution_id, template_id, task_key, Jsonb(actor), digest(actor), "d" * 64,
                   Jsonb(binding), digest(binding), user))
        tasks.append({"task_id": task_key, "revision_id": "synthetic-r8", "actor_sha256": digest(actor),
                      "private_reference_sha256": "d" * 64, "review_receipt_sha256": "e" * 64,
                      "case_selector": binding["case_selector"], "template": {"id": str(template_id), "version": 8, "sha256": digest(spec)},
                      "template_qualification_receipt_sha256": digest(receipt)})
    apps = c.execute("SELECT id,snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s ORDER BY id",
                     (project, owned[4])).fetchall()
    rows = [{"application_id": a["id"], "application_sha256": a["snapshot_sha256"],
             "product": a["snapshot"]["product"], "governing_state": a["snapshot"]["governing_state"],
             "task_id": "synthetic-policy-" + a["snapshot"]["product"], "revision_id": "synthetic-r8"} for a in apps]
    body = {"schema_version": "anvil.private-kyc-resolved-input.v1", "runtime_qualified": False,
            "policy_qualified": False, "run_authority": "not_granted", "scope": {
                "project_id": project, "project_binding_id": str(binding_id), "project_binding_sha256": stored_digest(snapshot),
                "runtime_source_sha256": runtime_source, "runtime_image_sha256": runtime_image,
                "environment_binding_sha256": "1" * 64, "evaluator_bindings_sha256": "2" * 64},
            "source_package_sha256": "b" * 64, "case_dataset": imp["manifest"]["case_dataset"],
            "input_count": len(rows), "rows": rows, "tasks": tasks, "source_anvil_requirements": []}
    c.execute("INSERT INTO anvil.kyc_resolved_input_versions(id,project_id,resolution_id,project_binding_id,case_import_id,body_canonical,content_sha256,created_by) "
              "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
              (input_id, project, resolution_id, binding_id, imp["id"], canonical(body).decode(), digest(body), user))
    return policy_scope(c, UUID(project), input_id, "synthetic-policy-individual", "synthetic-r8")
