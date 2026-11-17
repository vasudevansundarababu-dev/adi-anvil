-- Additive private custody only. No legacy093 reinterpretation, source seed,
-- public variant registration or model admission. Real records require review.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_qualifier') THEN
  CREATE ROLE anvil_kyc_qualifier NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_qualifier'
  AND (rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
 OR pg_has_role('anvil_app','anvil_kyc_qualifier','MEMBER')
 OR pg_has_role('anvil_worker','anvil_kyc_qualifier','MEMBER')
 OR pg_has_role('anvil_golden_scheduler','anvil_kyc_qualifier','MEMBER')
 OR pg_has_role('anvil_golden_grader','anvil_kyc_qualifier','MEMBER')
 THEN RAISE EXCEPTION 'separate restricted KYC operator capability required';END IF;
END $$;
GRANT USAGE ON SCHEMA anvil TO anvil_kyc_qualifier;
GRANT EXECUTE ON FUNCTION anvil.benchmark_is_admin(uuid,uuid) TO anvil_kyc_qualifier;

CREATE TABLE anvil.kyc_application_policy_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 binding_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 131072),
 body jsonb GENERATED ALWAYS AS (body_canonical::jsonb) STORED,
 scope_canonical text NOT NULL CHECK(octet_length(scope_canonical) BETWEEN 2 AND 8192),
 scope_sha256 text NOT NULL CHECK(scope_sha256=encode(sha256(convert_to(scope_canonical,'UTF8')),'hex')),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,binding_id) REFERENCES anvil.project_binding_versions(project_id,id),
 CHECK(jsonb_typeof(body)='object' AND octet_length(body::text)<=131072),
 CHECK(body ?& ARRAY['schema_version','id','scope','policy_set','policy_set_sha256',
  'domain_review_receipt','runtime_control_receipt','expires_at']),
 CHECK(jsonb_typeof(scope_canonical::jsonb)='object'),
 CHECK(body->'scope' IS NOT DISTINCT FROM scope_canonical::jsonb),
 CHECK(body->>'schema_version' IS NOT DISTINCT FROM 'anvil.private-kyc-policy-qualification.v1'),
 CHECK(body->>'id' IS NOT DISTINCT FROM id::text),
 CHECK(body#>>'{scope,project_id}' IS NOT DISTINCT FROM project_id::text),
 CHECK(body#>>'{scope,project_binding_id}' IS NOT DISTINCT FROM binding_id::text),
 CHECK(body#>>'{scope,execution_contract}' IS NOT DISTINCT FROM 'anvil.template-execution.v4'),
 CHECK((body->'scope') ?& ARRAY['project_id','project_binding_id','project_binding_sha256','source_sha256',
  'export_sha256','task_id','revision_id','workflow_product','workflow_review_receipt_sha256','payload_sha256',
  'runtime_source_sha256','runtime_image_sha256','environment_binding_sha256','evaluator_bindings_sha256']),
 CHECK((body->'policy_set') ?& ARRAY['id','version','product','governing_state','charter_profile',
  'federal_refs','state_refs','effective_from','effective_until']),
 CHECK(body#>>'{scope,workflow_product}' IS NOT NULL AND body#>>'{scope,workflow_product}' IN('individual','adult_joint','teen_joint','custodial')),
 CHECK(body#>>'{policy_set,product}' IS NOT DISTINCT FROM body#>>'{scope,workflow_product}'),
 CHECK(body#>>'{policy_set,governing_state}' IS NOT NULL AND body#>>'{policy_set,governing_state}' IN('CA','NY','TX','FL','IL')),
 CHECK(body#>>'{policy_set,charter_profile}' IS NOT NULL AND length(body#>>'{policy_set,charter_profile}') BETWEEN 1 AND 200),
 CHECK(body#>>'{domain_review_receipt,sha256}' IS NOT NULL AND body#>>'{domain_review_receipt,sha256}'~'^[a-f0-9]{64}$'),
 CHECK(body#>>'{runtime_control_receipt,sha256}' IS NOT NULL AND body#>>'{runtime_control_receipt,sha256}'~'^[a-f0-9]{64}$'),
 CHECK(body->>'policy_set_sha256' IS NOT NULL AND body->>'policy_set_sha256'~'^[a-f0-9]{64}$')
);
CREATE INDEX kyc_policy_scope_lookup ON anvil.kyc_application_policy_qualifications(project_id,scope_sha256,expires_at);

CREATE TABLE anvil.kyc_application_policy_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),
 reason text NOT NULL CHECK(length(reason) BETWEEN 1 AND 2000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.kyc_application_policy_qualifications(project_id,id),
 UNIQUE(project_id,qualification_id)
);

-- An operator can append only against the original authenticated source custody.
-- The new workflow/policy applicability itself is attested by reviewed operator
-- records, not inferred from a legacy domain-review hash or a UI boolean.
CREATE FUNCTION anvil.check_kyc_policy_qualification_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,anvil,pg_temp AS $$
DECLARE b anvil.project_binding_versions%ROWTYPE;s jsonb=NEW.scope_canonical::jsonb;
 record_body jsonb=NEW.body_canonical::jsonb;k text;BEGIN
 FOREACH k IN ARRAY ARRAY['project_binding_sha256','source_sha256','export_sha256','payload_sha256',
  'workflow_review_receipt_sha256','runtime_source_sha256','runtime_image_sha256',
  'environment_binding_sha256','evaluator_bindings_sha256'] LOOP
  IF s->>k IS NULL OR s->>k!~'^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'complete exact scope hash required';END IF;
 END LOOP;
 SELECT * INTO b FROM anvil.project_binding_versions WHERE project_id=NEW.project_id AND id=NEW.binding_id;
 IF NOT FOUND OR b.snapshot_sha256 IS DISTINCT FROM s->>'project_binding_sha256'
 OR b.snapshot->>'source_sha256' IS DISTINCT FROM s->>'source_sha256'
 OR NOT EXISTS(SELECT 1 FROM anvil.praxis_resolved_tasks t JOIN anvil.praxis_export_resolutions r
  ON r.project_id=t.project_id AND r.id=t.resolution_id WHERE t.project_id=NEW.project_id
  AND t.task_key=s->>'task_id' AND t.revision=s->>'revision_id'
  AND t.private_reference_sha256=s->>'payload_sha256' AND r.package_sha256=s->>'export_sha256'
  AND EXISTS(SELECT 1 FROM anvil.praxis_template_versions template WHERE template.project_id=t.project_id
   AND template.id=t.template_id AND template.spec#>>'{execution,schema_version}'='anvil.template-execution.v4'))
 THEN RAISE EXCEPTION 'exact original project binding and authenticated task export required';END IF;
 IF record_body->>'expires_at' IS NULL OR record_body->>'expires_at'!~'(Z|[+-][0-9]{2}:[0-9]{2})$'
 OR (record_body->>'expires_at')::timestamptz IS DISTINCT FROM NEW.expires_at
 THEN RAISE EXCEPTION 'exact aware qualification expiry required';END IF;
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION anvil.check_kyc_policy_qualification_scope() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.check_kyc_policy_qualification_scope() TO anvil_kyc_qualifier;
CREATE TRIGGER exact_scope BEFORE INSERT ON anvil.kyc_application_policy_qualifications
 FOR EACH ROW EXECUTE FUNCTION anvil.check_kyc_policy_qualification_scope();

DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['kyc_application_policy_qualifications','kyc_application_policy_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON anvil.%I FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_qualifier',t);
  EXECUTE format('CREATE POLICY engineer_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE POLICY operator_read ON anvil.%I FOR SELECT TO anvil_kyc_qualifier USING(anvil.benchmark_is_admin(project_id,nullif(current_setting(''anvil.user'',true),'''')::uuid))',t);
  EXECUTE format('CREATE POLICY operator_append ON anvil.%I FOR INSERT TO anvil_kyc_qualifier WITH CHECK(created_by=nullif(current_setting(''anvil.user'',true),'''')::uuid AND anvil.benchmark_is_admin(project_id,created_by))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_qualifier',t);
  EXECUTE format('GRANT INSERT ON anvil.%I TO anvil_kyc_qualifier',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON anvil.%I FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
-- The invoker trigger uses explicit admin/project-scoped reads, not a definer
-- bypass of FORCE RLS. No API role membership or legacy write is granted.
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['project_binding_versions','praxis_resolved_tasks','praxis_export_resolutions','praxis_template_versions'] LOOP
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_kyc_qualifier',t);
  EXECUTE format('CREATE POLICY kyc_qualifier_source_read ON anvil.%I FOR SELECT TO anvil_kyc_qualifier USING(anvil.benchmark_is_admin(project_id,nullif(current_setting(''anvil.user'',true),'''')::uuid))',t);
 END LOOP;
END $$;
-- NO role membership/login is issued here; deployment provisions a distinct
-- operator identity after qualification. API clients cannot mint records.
INSERT INTO anvil.schema_versions(version) VALUES(118);
