-- Actual scoped PO decisions, disjoint from runtime qualification. No seeded approvals.
CREATE TABLE anvil.kyc_policy_operator_principals(
 login_role name NOT NULL,project_id uuid NOT NULL REFERENCES anvil.projects(id),user_id uuid NOT NULL REFERENCES anvil.users(id),
 PRIMARY KEY(login_role,project_id));
REVOKE ALL ON anvil.kyc_policy_operator_principals FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT SELECT ON anvil.kyc_policy_operator_principals TO anvil_kyc_qualifier;
ALTER TABLE anvil.kyc_policy_operator_principals ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.kyc_policy_operator_principals FORCE ROW LEVEL SECURITY;
CREATE POLICY own_login ON anvil.kyc_policy_operator_principals FOR SELECT TO anvil_kyc_qualifier
 USING(login_role=session_user);
CREATE FUNCTION anvil.kyc_policy_operator_scope(p uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM anvil.kyc_policy_operator_principals x WHERE x.login_role=session_user
  AND x.project_id=p AND x.user_id::text=current_setting('anvil.user',true)
  AND p::text=current_setting('anvil.project',true) AND anvil.benchmark_is_admin(p,x.user_id))
$$;
REVOKE ALL ON FUNCTION anvil.kyc_policy_operator_scope(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.kyc_policy_operator_scope(uuid) TO anvil_kyc_qualifier;
CREATE TABLE anvil.kyc_policy_review_subjects(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 131072),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 UNIQUE(project_id,id),UNIQUE(project_id,content_sha256),
 CHECK(body_canonical::jsonb->>'schema_version' IS NOT DISTINCT FROM 'anvil.kyc-policy-domain-subject.v1'));
CREATE TABLE anvil.kyc_policy_review_receipts(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 subject_id uuid,kind text NOT NULL CHECK(kind IN('domain','runtime')),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 131072),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 expires_at timestamptz NOT NULL,UNIQUE(project_id,id),
 FOREIGN KEY(project_id,subject_id) REFERENCES anvil.kyc_policy_review_subjects(project_id,id));
CREATE TABLE anvil.kyc_policy_review_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,receipt_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 2000),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(project_id,receipt_id),FOREIGN KEY(project_id,receipt_id) REFERENCES anvil.kyc_policy_review_receipts(project_id,id));

DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['kyc_policy_review_subjects','kyc_policy_review_receipts','kyc_policy_review_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON anvil.%I FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_qualifier',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_kyc_qualifier,anvil_golden_scheduler,anvil_golden_grader',t);
  EXECUTE format('CREATE POLICY app_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY operator_read ON anvil.%I FOR SELECT TO anvil_kyc_qualifier USING(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',t);
  EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON anvil.%I FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
GRANT INSERT ON anvil.kyc_policy_review_subjects,anvil.kyc_policy_review_receipts,anvil.kyc_policy_review_revocations TO anvil_app;
GRANT INSERT ON anvil.kyc_policy_review_receipts TO anvil_kyc_qualifier;
CREATE POLICY app_subject_append ON anvil.kyc_policy_review_subjects FOR INSERT TO anvil_app
 WITH CHECK(created_by::text=current_setting('anvil.user',true) AND anvil.benchmark_is_admin(project_id,created_by));
CREATE POLICY app_domain_append ON anvil.kyc_policy_review_receipts FOR INSERT TO anvil_app
 WITH CHECK(kind='domain' AND created_by::text=current_setting('anvil.user',true) AND anvil.benchmark_is_admin(project_id,created_by));
CREATE POLICY qualifier_runtime_append ON anvil.kyc_policy_review_receipts FOR INSERT TO anvil_kyc_qualifier
 WITH CHECK(kind='runtime' AND project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND created_by::text=current_setting('anvil.user',true) AND anvil.benchmark_is_admin(project_id,created_by));
CREATE POLICY app_revoke ON anvil.kyc_policy_review_revocations FOR INSERT TO anvil_app
 WITH CHECK(created_by::text=current_setting('anvil.user',true) AND anvil.benchmark_is_admin(project_id,created_by));

-- The database fence also covers direct authorized SQL, not only the Python CLI.
CREATE FUNCTION anvil.fence_kyc_policy_review() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.kyc.policy.review:'||NEW.project_id::text,0));
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION anvil.fence_kyc_policy_review() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.fence_kyc_policy_review() TO anvil_app,anvil_kyc_qualifier;
CREATE TRIGGER a_review_fence BEFORE INSERT ON anvil.kyc_policy_review_revocations
 FOR EACH ROW EXECUTE FUNCTION anvil.fence_kyc_policy_review();
CREATE TRIGGER a_review_fence BEFORE INSERT ON anvil.kyc_application_policy_qualifications
 FOR EACH ROW EXECUTE FUNCTION anvil.fence_kyc_policy_review();

CREATE FUNCTION anvil.check_kyc_scoped_review() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $$
DECLARE b jsonb=NEW.body_canonical::jsonb;s anvil.kyc_policy_review_subjects;members integer;BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.kyc.policy.review:'||NEW.project_id::text,0));
 IF b->>'schema_version' IS DISTINCT FROM 'anvil.kyc-policy-review-receipt.v1'
 OR b->>'id' IS DISTINCT FROM NEW.id::text OR b->>'project_id' IS DISTINCT FROM NEW.project_id::text
 OR b->>'reviewer_id' IS DISTINCT FROM NEW.created_by::text OR b->>'kind' IS DISTINCT FROM NEW.kind
 OR (b->>'expires_at')::timestamptz IS DISTINCT FROM NEW.expires_at
 OR NEW.expires_at<=clock_timestamp() OR b->>'decision' IS NULL OR b->>'decision' NOT IN('approved','rejected')
 THEN RAISE EXCEPTION 'exact scoped review receipt required';END IF;
 IF NEW.kind='domain' THEN
  PERFORM id FROM anvil.projects WHERE id=NEW.project_id FOR UPDATE;
  SELECT * INTO s FROM anvil.kyc_policy_review_subjects WHERE project_id=NEW.project_id AND id=NEW.subject_id;
  IF s.id IS NULL OR b->>'subject_sha256' IS DISTINCT FROM s.content_sha256
  OR b->'subject' IS DISTINCT FROM s.body_canonical::jsonb
  OR b->>'subject_id' IS DISTINCT FROM s.id::text
  OR NOT anvil.benchmark_is_admin(NEW.project_id,NEW.created_by)
  THEN RAISE EXCEPTION 'current exact policy review subject and PO required';END IF;
  SELECT count(*) INTO members FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
   WHERE m.project_id=NEW.project_id AND m.role='admin' AND m.active AND u.active;
  IF s.created_by=NEW.created_by AND members<>1 THEN RAISE EXCEPTION 'self approval requires exactly one active PO';END IF;
  IF b->'self_approved' IS DISTINCT FROM to_jsonb(s.created_by=NEW.created_by)
  THEN RAISE EXCEPTION 'server recorded self approval required';END IF;
 ELSE
  IF NEW.subject_id IS NOT NULL OR b->>'subject_id' IS NOT NULL
  OR b#>>'{subject,schema_version}' IS DISTINCT FROM 'anvil.kyc-policy-runtime-subject.v1'
  OR b->>'decision' IS DISTINCT FROM 'approved'
  THEN RAISE EXCEPTION 'operator runtime evidence subject required';END IF;
 END IF;
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION anvil.check_kyc_scoped_review() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.check_kyc_scoped_review() TO anvil_app,anvil_kyc_qualifier;
CREATE TRIGGER scoped_review BEFORE INSERT ON anvil.kyc_policy_review_receipts
 FOR EACH ROW EXECUTE FUNCTION anvil.check_kyc_scoped_review();

CREATE FUNCTION anvil.kyc_policy_reviews_current(p uuid,b jsonb,expires timestamptz) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $$
DECLARE s jsonb=b->'scope';d anvil.kyc_policy_review_receipts;r anvil.kyc_policy_review_receipts;BEGIN
 SELECT * INTO d FROM anvil.kyc_policy_review_receipts WHERE project_id=p AND kind='domain'
 AND id=(b#>>'{domain_review_receipt,id}')::uuid AND content_sha256=b#>>'{domain_review_receipt,sha256}';
 SELECT * INTO r FROM anvil.kyc_policy_review_receipts WHERE project_id=p AND kind='runtime'
 AND id=(b#>>'{runtime_control_receipt,id}')::uuid AND content_sha256=b#>>'{runtime_control_receipt,sha256}';
 IF d.id IS NULL OR r.id IS NULL OR expires<=statement_timestamp() OR d.expires_at<expires OR r.expires_at<expires
 OR NOT anvil.benchmark_is_admin(p,d.created_by) OR NOT anvil.benchmark_is_admin(p,r.created_by)
 OR d.body_canonical::jsonb->>'decision' IS DISTINCT FROM 'approved'
 OR r.body_canonical::jsonb->>'decision' IS DISTINCT FROM 'approved'
 OR EXISTS(SELECT 1 FROM anvil.kyc_policy_review_revocations v WHERE v.project_id=p AND v.receipt_id IN(d.id,r.id))
 OR d.body_canonical::jsonb->'subject' IS DISTINCT FROM jsonb_build_object(
  'schema_version','anvil.kyc-policy-domain-subject.v1','template',s->'template',
  'task_id',s->'task_id','revision_id',s->'revision_id','policy_set',b->'policy_set')
 OR r.body_canonical::jsonb->'subject' IS DISTINCT FROM jsonb_build_object(
  'schema_version','anvil.kyc-policy-runtime-subject.v1','runtime_source_sha256',s->'runtime_source_sha256',
  'runtime_image_sha256',s->'runtime_image_sha256','environment_binding_sha256',s->'environment_binding_sha256',
  'evaluator_bindings_sha256',s->'evaluator_bindings_sha256')
 THEN RETURN false;END IF;
 RETURN true;END $$;
REVOKE ALL ON FUNCTION anvil.kyc_policy_reviews_current(uuid,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.kyc_policy_reviews_current(uuid,jsonb,timestamptz)
 TO anvil_app,anvil_kyc_qualifier,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION anvil.benchmark_is_admin(uuid,uuid) TO anvil_golden_scheduler,anvil_golden_grader;
CREATE FUNCTION anvil.check_kyc_policy_review_references() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $$ BEGIN
 IF NOT anvil.kyc_policy_reviews_current(NEW.project_id,NEW.body_canonical::jsonb,NEW.expires_at)
 THEN RAISE EXCEPTION 'authenticated exact current policy and runtime reviews required';END IF;
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION anvil.check_kyc_policy_review_references() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.check_kyc_policy_review_references() TO anvil_kyc_qualifier;
CREATE TRIGGER actual_reviews BEFORE INSERT ON anvil.kyc_application_policy_qualifications
 FOR EACH ROW EXECUTE FUNCTION anvil.check_kyc_policy_review_references();

GRANT SELECT ON anvil.praxis_template_qualifications,anvil.praxis_template_revocations TO anvil_kyc_qualifier;
CREATE POLICY qualifier_read ON anvil.praxis_template_qualifications FOR SELECT TO anvil_kyc_qualifier
 USING(anvil.kyc_policy_operator_scope(project_id));
CREATE POLICY qualifier_read ON anvil.praxis_template_revocations FOR SELECT TO anvil_kyc_qualifier
 USING(anvil.kyc_policy_operator_scope(project_id));
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['kyc_policy_review_subjects','kyc_policy_review_receipts','kyc_policy_review_revocations',
 'kyc_application_policy_qualifications','kyc_application_policy_revocations',
 'kyc_application_policy_materializations','kyc_application_policy_materialization_revocations',
 'kyc_resolved_input_versions','project_binding_versions','praxis_resolved_tasks','praxis_export_resolutions',
 'praxis_template_versions','praxis_template_qualifications','praxis_template_revocations','project_data_inputs'] LOOP
  EXECUTE format('CREATE POLICY enrolled_operator ON anvil.%I AS RESTRICTIVE FOR ALL TO anvil_kyc_qualifier USING(anvil.kyc_policy_operator_scope(project_id)) WITH CHECK(anvil.kyc_policy_operator_scope(project_id))',t);
 END LOOP;
END $$;
-- V2 retains complete original sources; public tools deliver bounded documents.
-- Preserve the existing v1 storage cap rather than silently widening its contract.
DO $$ DECLARE n text;matches integer;BEGIN
 SELECT count(*),min(conname::text) INTO matches,n FROM pg_constraint
 WHERE conrelid='anvil.kyc_application_policy_materializations'::regclass AND contype='c'
 AND pg_get_constraintdef(oid) LIKE '%octet_length(body_canonical)%'
 AND pg_get_constraintdef(oid) LIKE '%131072%';
 IF matches<>1 THEN RAISE EXCEPTION 'exact original materialization size constraint required';END IF;
 EXECUTE format('ALTER TABLE anvil.kyc_application_policy_materializations DROP CONSTRAINT %I',n);
END $$;
ALTER TABLE anvil.kyc_application_policy_materializations ADD CONSTRAINT versioned_materialization_size CHECK(
 octet_length(body_canonical)>=2 AND (
  (body_canonical::jsonb->>'schema_version'='anvil.kyc-application-policy-materialization.v1' AND octet_length(body_canonical)<=131072)
  OR (body_canonical::jsonb->>'schema_version'='anvil.kyc-application-policy-materialization.v2' AND octet_length(body_canonical)<=1048576)));
-- Keep all original scope/expiry checks in the existing exact-parent trigger.
DO $$ DECLARE original text;BEGIN
 SELECT pg_get_functiondef('anvil.check_application_policy_materialization()'::regprocedure) INTO original;
 IF strpos(original, 'OR body->>''schema_version'' IS DISTINCT FROM ''anvil.kyc-application-policy-materialization.v1''')=0
 THEN RAISE EXCEPTION 'exact original materialization parent guard required';END IF;
 EXECUTE replace(original,
  'OR body->>''schema_version'' IS DISTINCT FROM ''anvil.kyc-application-policy-materialization.v1''',
  'OR body->>''schema_version'' IS NULL OR body->>''schema_version'' NOT IN (''anvil.kyc-application-policy-materialization.v1'',''anvil.kyc-application-policy-materialization.v2'')');
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(129);
