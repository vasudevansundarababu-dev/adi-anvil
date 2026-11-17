-- Source-only immutable Anvil input contexts for unchanged-v1 product tasks.
-- No source/task/template/publication/policy qualification, identity or Run is seeded.
CREATE TABLE anvil.kyc_resolved_input_versions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL, resolution_id uuid NOT NULL,
 project_binding_id uuid NOT NULL,case_import_id uuid NOT NULL,
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 10485760),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(project_id,id),UNIQUE(project_id,resolution_id,project_binding_id,case_import_id,content_sha256),
 FOREIGN KEY(project_id,resolution_id) REFERENCES anvil.praxis_export_resolutions(project_id,id),
 FOREIGN KEY(project_id,project_binding_id) REFERENCES anvil.project_binding_versions(project_id,id),
 FOREIGN KEY(project_id,case_import_id) REFERENCES banking.anvil_imports(project_id,id),
 CHECK(body_canonical::jsonb->>'schema_version' IS NOT DISTINCT FROM 'anvil.private-kyc-resolved-input.v1'),
 CHECK(body_canonical::jsonb->'runtime_qualified' IS NOT DISTINCT FROM 'false'::jsonb),
 CHECK(body_canonical::jsonb->'policy_qualified' IS NOT DISTINCT FROM 'false'::jsonb),
 CHECK(body_canonical::jsonb->>'run_authority' IS NOT DISTINCT FROM 'not_granted')
);
ALTER TABLE anvil.kyc_resolved_input_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.kyc_resolved_input_versions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON anvil.kyc_resolved_input_versions FROM PUBLIC,anvil_worker;
CREATE POLICY engineer_read ON anvil.kyc_resolved_input_versions FOR SELECT TO anvil_app
 USING(anvil.golden_engineer(project_id));
CREATE POLICY engineer_insert ON anvil.kyc_resolved_input_versions FOR INSERT TO anvil_app
 WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY runtime_read ON anvil.kyc_resolved_input_versions FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader
 USING(banking.runtime_scope(project_id));
CREATE POLICY operator_read ON anvil.kyc_resolved_input_versions FOR SELECT TO anvil_kyc_qualifier
 USING(anvil.benchmark_is_admin(project_id,nullif(current_setting('anvil.user',true),'')::uuid));
GRANT SELECT,INSERT ON anvil.kyc_resolved_input_versions TO anvil_app;
GRANT SELECT ON anvil.kyc_resolved_input_versions TO anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_qualifier;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.kyc_resolved_input_versions
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON anvil.kyc_resolved_input_versions
 FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable();

-- New context bytes consume the existing50MiB project-input budget, not a new
-- allowance. Both existing and new INSERT paths serialize on the SAME project
-- row already used by project_inputs.save. Source-byte accounting, not a claim
-- about physical PostgreSQL storage. Older snapshots cannot defeat the count.
CREATE FUNCTION anvil.kyc_input_context_quota_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,pg_temp AS $$
DECLARE used bigint;amount bigint;BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR NEW.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid
 THEN RAISE EXCEPTION 'current original project input context required';END IF;
 PERFORM id FROM anvil.projects WHERE id=NEW.project_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'original project input custody required';END IF;
 SELECT coalesce(sum(size),0) INTO used FROM(
  SELECT i.byte_size AS size FROM anvil.project_data_inputs i WHERE i.project_id=NEW.project_id
  UNION ALL SELECT octet_length(v.body_canonical) FROM anvil.kyc_resolved_input_versions v WHERE v.project_id=NEW.project_id
 ) charged;
 IF TG_TABLE_NAME='project_data_inputs' THEN amount=NEW.byte_size;
 ELSE amount=octet_length(NEW.body_canonical);END IF;
 IF used+amount>52428800 THEN RAISE EXCEPTION 'original project input quota exhausted';END IF;
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION anvil.kyc_input_context_quota_guard() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.kyc_input_context_quota_guard() TO anvil_app;
CREATE TRIGGER kyc_context_quota BEFORE INSERT ON anvil.project_data_inputs
 FOR EACH ROW EXECUTE FUNCTION anvil.kyc_input_context_quota_guard();
CREATE TRIGGER kyc_context_quota BEFORE INSERT ON anvil.kyc_resolved_input_versions
 FOR EACH ROW EXECUTE FUNCTION anvil.kyc_input_context_quota_guard();

CREATE FUNCTION anvil.check_kyc_resolved_input_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,pg_temp AS $$
DECLARE body jsonb=NEW.body_canonical::jsonb;s jsonb=body->'scope';
 b anvil.project_binding_versions;r anvil.praxis_export_resolutions;i banking.anvil_imports;
 task jsonb;row_count bigint;BEGIN
 SELECT * INTO b FROM anvil.project_binding_versions WHERE project_id=NEW.project_id AND id=NEW.project_binding_id;
 SELECT * INTO r FROM anvil.praxis_export_resolutions WHERE project_id=NEW.project_id AND id=NEW.resolution_id;
 SELECT * INTO i FROM banking.anvil_imports WHERE project_id=NEW.project_id AND id=NEW.case_import_id;
 IF b.id IS NULL OR r.id IS NULL OR i.id IS NULL
 OR s->>'project_id' IS DISTINCT FROM NEW.project_id::text
 OR s->>'project_binding_id' IS DISTINCT FROM b.id::text
 OR s->>'project_binding_sha256' IS DISTINCT FROM b.snapshot_sha256
 OR body->>'source_package_sha256' IS DISTINCT FROM r.package_sha256
 OR body->'case_dataset' IS DISTINCT FROM i.manifest->'case_dataset'
 OR jsonb_typeof(body->'rows') IS DISTINCT FROM 'array' OR jsonb_typeof(body->'tasks') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'exact original source binding and dataset import required';END IF;
 row_count=jsonb_array_length(body->'rows');
 IF row_count NOT BETWEEN 1 AND 10000 OR body->>'input_count' IS DISTINCT FROM row_count::text
 OR body#>>'{case_dataset,case_count}' IS DISTINCT FROM row_count::text
 OR row_count<>(SELECT count(*) FROM banking.applications a WHERE a.project_id=NEW.project_id AND a.pack_id=i.pack_id)
 OR row_count<>(SELECT count(DISTINCT member->>'application_id') FROM jsonb_array_elements(body->'rows') member)
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(body->'rows') member
  LEFT JOIN banking.applications a ON a.project_id=NEW.project_id AND a.pack_id=i.pack_id AND a.id=member->>'application_id'
  WHERE a.id IS NULL OR member->>'application_sha256' IS DISTINCT FROM a.snapshot_sha256
  OR member->>'governing_state' IS DISTINCT FROM a.snapshot->>'governing_state'
  OR member->>'product' IS DISTINCT FROM CASE WHEN a.snapshot->>'product' IN('individual','adult_joint','teen_joint','custodial')
   THEN a.snapshot->>'product' ELSE NULL END)
 THEN RAISE EXCEPTION 'complete exact original snapshot membership required';END IF;
 IF jsonb_array_length(body->'tasks') NOT BETWEEN 1 AND 200
 OR jsonb_array_length(body->'tasks')<>(SELECT count(*) FROM anvil.praxis_resolved_tasks t
  WHERE t.project_id=NEW.project_id AND t.resolution_id=r.id)
 OR jsonb_array_length(body->'tasks')<>(SELECT count(DISTINCT t->>'task_id') FROM jsonb_array_elements(body->'tasks') t)
 THEN RAISE EXCEPTION 'complete unique resolved source tasks required';END IF;
 FOR task IN SELECT value FROM jsonb_array_elements(body->'tasks') LOOP
  IF task#>>'{case_selector,field}' IS DISTINCT FROM 'product'
  OR NOT EXISTS(SELECT 1 FROM anvil.praxis_resolved_tasks t
   JOIN anvil.praxis_template_versions v ON v.project_id=t.project_id AND v.id=t.template_id
   JOIN anvil.praxis_template_qualifications q ON q.project_id=t.project_id AND q.template_id=v.id
    AND q.id::text=t.binding->>'qualification_id'
   WHERE t.project_id=NEW.project_id AND t.resolution_id=r.id AND t.task_key=task->>'task_id'
   AND t.revision=task->>'revision_id' AND t.actor_sha256=task->>'actor_sha256'
   AND t.private_reference_sha256=task->>'private_reference_sha256'
   AND v.spec->>'template_id'=task#>>'{template,id}' AND v.version::text=task#>>'{template,version}'
   AND v.spec_sha256=task#>>'{template,sha256}' AND v.version>=7
   AND v.spec#>>'{authoring,template,caseSelector,field}'='product'
   AND t.binding->'case_selector'=task->'case_selector'
   AND q.status='qualified' AND q.receipt_sha256=task->>'template_qualification_receipt_sha256'
   AND NOT EXISTS(SELECT 1 FROM anvil.praxis_template_revocations x WHERE x.project_id=q.project_id AND x.qualification_id=q.id))
  THEN RAISE EXCEPTION 'exact qualified product source task required';END IF;
 END LOOP;
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION anvil.check_kyc_resolved_input_scope() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.check_kyc_resolved_input_scope() TO anvil_app;
CREATE TRIGGER exact_scope BEFORE INSERT ON anvil.kyc_resolved_input_versions
 FOR EACH ROW EXECUTE FUNCTION anvil.check_kyc_resolved_input_scope();

-- Add a distinct product/v1 scope rather than rename or silently reinterpret118.
-- The original automatically named CHECK is discovered from its exact original
-- expression; fail if the expected single constraint is not present.
DO $$ DECLARE constraint_name text;matches integer;BEGIN
 SELECT count(*),min(conname::text) INTO matches,constraint_name FROM pg_constraint
 WHERE conrelid='anvil.kyc_application_policy_qualifications'::regclass AND contype='c'
 AND pg_get_constraintdef(oid) LIKE '%execution_contract%'
 AND pg_get_constraintdef(oid) LIKE '%anvil.template-execution.v4%';
 IF matches<>1 THEN RAISE EXCEPTION 'exact original118 scope constraint required';END IF;
 EXECUTE format('ALTER TABLE anvil.kyc_application_policy_qualifications DROP CONSTRAINT %I',constraint_name);
END $$;
ALTER TABLE anvil.kyc_application_policy_qualifications ADD CONSTRAINT kyc_policy_scope_variant CHECK(
 (body#>>'{scope,execution_contract}' IS NOT DISTINCT FROM 'anvil.template-execution.v4'
  AND NOT (body->'scope' ? 'export_contract'))
 OR (body#>>'{scope,export_contract}' IS NOT DISTINCT FROM 'praxis.authored-task-export.v1'
  AND body#>>'{scope,selector_field}' IS NOT DISTINCT FROM 'product'
  AND NOT (body->'scope' ? 'execution_contract')
  AND (body->'scope') ?& ARRAY['template','template_qualification_receipt_sha256','resolved_input_id','resolved_input_sha256']
  AND jsonb_typeof(body#>'{scope,template}') IS NOT DISTINCT FROM 'object'
  AND body#>>'{scope,resolved_input_sha256}' IS NOT NULL AND body#>>'{scope,resolved_input_sha256}'~'^[a-f0-9]{64}$'
  AND body#>>'{scope,template_qualification_receipt_sha256}' IS NOT NULL
  AND body#>>'{scope,template_qualification_receipt_sha256}'~'^[a-f0-9]{64}$')
);
CREATE OR REPLACE FUNCTION anvil.check_kyc_policy_qualification_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,anvil,pg_temp AS $$
DECLARE b anvil.project_binding_versions%ROWTYPE;s jsonb=NEW.scope_canonical::jsonb;
 record_body jsonb=NEW.body_canonical::jsonb;k text;legacy boolean;product boolean;BEGIN
 FOREACH k IN ARRAY ARRAY['project_binding_sha256','source_sha256','export_sha256','payload_sha256',
  'workflow_review_receipt_sha256','runtime_source_sha256','runtime_image_sha256',
  'environment_binding_sha256','evaluator_bindings_sha256'] LOOP
  IF s->>k IS NULL OR s->>k!~'^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'complete exact scope hash required';END IF;
 END LOOP;
 legacy=s->>'execution_contract' IS NOT DISTINCT FROM 'anvil.template-execution.v4' AND NOT (s ? 'export_contract');
 product=s->>'export_contract' IS NOT DISTINCT FROM 'praxis.authored-task-export.v1'
  AND s->>'selector_field' IS NOT DISTINCT FROM 'product' AND NOT (s ? 'execution_contract');
 SELECT * INTO b FROM anvil.project_binding_versions WHERE project_id=NEW.project_id AND id=NEW.binding_id;
 IF b.id IS NULL OR b.snapshot_sha256 IS DISTINCT FROM s->>'project_binding_sha256'
 OR b.snapshot->>'source_sha256' IS DISTINCT FROM s->>'source_sha256'
 OR NOT EXISTS(SELECT 1 FROM anvil.praxis_resolved_tasks t JOIN anvil.praxis_export_resolutions r
  ON r.project_id=t.project_id AND r.id=t.resolution_id
  JOIN anvil.praxis_template_versions v ON v.project_id=t.project_id AND v.id=t.template_id
  WHERE t.project_id=NEW.project_id AND t.task_key=s->>'task_id' AND t.revision=s->>'revision_id'
  AND t.private_reference_sha256=s->>'payload_sha256' AND r.package_sha256=s->>'export_sha256'
  AND (legacy AND v.spec#>>'{execution,schema_version}'='anvil.template-execution.v4'
   OR product AND v.version>=7 AND v.spec#>>'{authoring,template,caseSelector,field}'='product'
   AND v.spec->>'template_id'=s#>>'{template,id}' AND v.version::text=s#>>'{template,version}'
   AND v.spec_sha256=s#>>'{template,sha256}'
   AND t.binding->'case_selector'=jsonb_build_object('field','product','value',s->>'workflow_product')
   AND EXISTS(SELECT 1 FROM anvil.praxis_template_qualifications q WHERE q.project_id=v.project_id AND q.template_id=v.id
    AND q.id::text=t.binding->>'qualification_id' AND q.status='qualified'
    AND q.receipt_sha256=s->>'template_qualification_receipt_sha256'
    AND NOT EXISTS(SELECT 1 FROM anvil.praxis_template_revocations x WHERE x.project_id=q.project_id AND x.qualification_id=q.id))
   AND EXISTS(SELECT 1 FROM anvil.kyc_resolved_input_versions input WHERE input.project_id=NEW.project_id
    AND input.id::text=s->>'resolved_input_id' AND input.content_sha256=s->>'resolved_input_sha256'
    AND input.project_binding_id=b.id AND input.resolution_id=r.id
    AND (input.body_canonical::jsonb)#>>'{scope,runtime_source_sha256}'=s->>'runtime_source_sha256'
    AND (input.body_canonical::jsonb)#>>'{scope,runtime_image_sha256}'=s->>'runtime_image_sha256'
    AND (input.body_canonical::jsonb)#>>'{scope,environment_binding_sha256}'=s->>'environment_binding_sha256'
    AND (input.body_canonical::jsonb)#>>'{scope,evaluator_bindings_sha256}'=s->>'evaluator_bindings_sha256'
    AND EXISTS(SELECT 1 FROM jsonb_array_elements(input.body_canonical::jsonb->'tasks') task
     WHERE task->>'task_id'=t.task_key AND task->>'revision_id'=t.revision
     AND task->>'review_receipt_sha256'=s->>'workflow_review_receipt_sha256'))))
 THEN RAISE EXCEPTION 'exact original binding, source task and policy scope required';END IF;
 IF record_body->>'expires_at' IS NULL OR record_body->>'expires_at'!~'(Z|[+-][0-9]{2}:[0-9]{2})$'
 OR (record_body->>'expires_at')::timestamptz IS DISTINCT FROM NEW.expires_at
 THEN RAISE EXCEPTION 'exact aware qualification expiry required';END IF;
 RETURN NEW;END $$;
INSERT INTO anvil.schema_versions(version) VALUES(120);
