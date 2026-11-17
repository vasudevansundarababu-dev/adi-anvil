-- Additive v7/product policy delivery. No093 latest-state fallback, legal text,
-- policy qualification, operator login or role membership is seeded here.
CREATE TABLE anvil.kyc_application_policy_materializations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,
 application_id text,created_by uuid NOT NULL REFERENCES anvil.users(id),
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 131072),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.kyc_application_policy_qualifications(project_id,id));
CREATE TABLE anvil.kyc_application_policy_materialization_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,materialization_id uuid NOT NULL UNIQUE,
 created_by uuid NOT NULL REFERENCES anvil.users(id),reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,materialization_id) REFERENCES anvil.kyc_application_policy_materializations(project_id,id));
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['kyc_application_policy_materializations','kyc_application_policy_materialization_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON anvil.%I FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_qualifier',t);
  EXECUTE format('GRANT INSERT ON anvil.%I TO anvil_kyc_qualifier',t);
  EXECUTE format('CREATE POLICY app_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE POLICY operator_read ON anvil.%I FOR SELECT TO anvil_kyc_qualifier USING(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',t);
  EXECUTE format('CREATE POLICY operator_append ON anvil.%I FOR INSERT TO anvil_kyc_qualifier WITH CHECK(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid AND created_by::text=current_setting(''anvil.user'',true) AND anvil.benchmark_is_admin(project_id,created_by))',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON anvil.%I FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE FUNCTION anvil.check_application_policy_materialization() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,pg_temp AS $$
DECLARE parent anvil.kyc_application_policy_qualifications;body jsonb=NEW.body_canonical::jsonb;BEGIN
 SELECT * INTO parent FROM anvil.kyc_application_policy_qualifications
 WHERE project_id=NEW.project_id AND id=NEW.qualification_id;
 IF parent.id IS NULL OR parent.expires_at<=clock_timestamp() OR NEW.expires_at<=clock_timestamp()
 OR NEW.expires_at>parent.expires_at
 OR EXISTS(SELECT 1 FROM anvil.kyc_application_policy_revocations r WHERE r.project_id=NEW.project_id AND r.qualification_id=parent.id)
 OR body->>'schema_version' IS DISTINCT FROM 'anvil.kyc-application-policy-materialization.v1'
 OR body->>'id' IS DISTINCT FROM NEW.id::text OR body->>'qualification_id' IS DISTINCT FROM parent.id::text
 OR body->'scope' IS DISTINCT FROM parent.body->'scope'
 OR body#>>'{scope,export_contract}' IS DISTINCT FROM 'praxis.authored-task-export.v1'
 OR body#>>'{scope,selector_field}' IS DISTINCT FROM 'product'
 OR (body#>>'{scope,template,version}')::integer<7
 OR body->>'policy_set_sha256' IS DISTINCT FROM parent.body->>'policy_set_sha256'
 OR body->>'application_id' IS DISTINCT FROM NEW.application_id
 OR (body->>'expires_at')::timestamptz IS DISTINCT FROM NEW.expires_at
 OR jsonb_typeof(body->'artifacts') IS DISTINCT FROM 'array'
 OR jsonb_array_length(body->'artifacts') NOT BETWEEN 1 AND 200
 THEN RAISE EXCEPTION 'exact current v7 qualified policy materialization required';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION anvil.check_application_policy_materialization() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.check_application_policy_materialization() TO anvil_kyc_qualifier;
CREATE TRIGGER exact_parent BEFORE INSERT ON anvil.kyc_application_policy_materializations
 FOR EACH ROW EXECUTE FUNCTION anvil.check_application_policy_materialization();

-- All three append paths use one existing50MiB project-input allowance. The
-- common advisory fence adds operator appends without granting project UPDATE.
GRANT SELECT(project_id,byte_size) ON anvil.project_data_inputs TO anvil_kyc_qualifier;
CREATE POLICY policy_quota_read ON anvil.project_data_inputs FOR SELECT TO anvil_kyc_qualifier
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE OR REPLACE FUNCTION anvil.kyc_input_context_quota_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,pg_temp AS $$
DECLARE used bigint;amount bigint;BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR NEW.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid
 THEN RAISE EXCEPTION 'current original project input context required';END IF;
 IF TG_TABLE_NAME<>'kyc_application_policy_materializations' THEN
  PERFORM id FROM anvil.projects WHERE id=NEW.project_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'original project input custody required';END IF;
 END IF;
 -- Application writers already lock the project before INSERT. Preserve that
 -- order for direct SQL writers too; operator materializations need no row lock.
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.kyc.input_policy_quota:'||NEW.project_id::text,0));
 SELECT coalesce(sum(size),0) INTO used FROM(
  SELECT i.byte_size AS size FROM anvil.project_data_inputs i WHERE i.project_id=NEW.project_id
  UNION ALL SELECT octet_length(v.body_canonical) FROM anvil.kyc_resolved_input_versions v WHERE v.project_id=NEW.project_id
  UNION ALL SELECT octet_length(m.body_canonical) FROM anvil.kyc_application_policy_materializations m WHERE m.project_id=NEW.project_id
 ) charged;
 IF TG_TABLE_NAME='project_data_inputs' THEN amount=NEW.byte_size;ELSE amount=octet_length(NEW.body_canonical);END IF;
 IF used+amount>52428800 THEN RAISE EXCEPTION 'original project input quota exhausted';END IF;
 RETURN NEW;
END $$;
GRANT EXECUTE ON FUNCTION anvil.kyc_input_context_quota_guard() TO anvil_kyc_qualifier;
CREATE TRIGGER original_quota BEFORE INSERT ON anvil.kyc_application_policy_materializations
 FOR EACH ROW EXECUTE FUNCTION anvil.kyc_input_context_quota_guard();

-- Narrow read owner has no policy INSERT privilege or operational membership.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_context_owner') THEN
  CREATE ROLE anvil_kyc_context_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_context_owner'
  AND (rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
 OR pg_has_role('anvil_app','anvil_kyc_context_owner','MEMBER') OR pg_has_role('anvil_worker','anvil_kyc_context_owner','MEMBER')
 OR pg_has_role('anvil_golden_scheduler','anvil_kyc_context_owner','MEMBER') OR pg_has_role('anvil_golden_grader','anvil_kyc_context_owner','MEMBER')
 OR pg_has_role('anvil_kyc_qualifier','anvil_kyc_context_owner','MEMBER') THEN RAISE EXCEPTION 'disjoint private KYC read owner required';END IF;
END $$;
GRANT USAGE ON SCHEMA anvil,banking TO anvil_kyc_context_owner;
DO $$ DECLARE pair text[];BEGIN
 FOREACH pair SLICE 1 IN ARRAY ARRAY[
 ['banking','paid_agent_bindings'],['banking','trials'],['anvil','harbor_agent_plans'],
 ['anvil','kyc_resolved_input_versions'],['anvil','praxis_resolved_tasks'],['anvil','praxis_template_versions'],
 ['anvil','praxis_template_qualifications'],['anvil','praxis_template_revocations'],['anvil','project_binding_versions'],
 ['banking','anvil_imports'],['banking','applications']] LOOP
  EXECUTE format('GRANT SELECT ON %I.%I TO anvil_kyc_context_owner',pair[1],pair[2]);
  EXECUTE format('CREATE POLICY kyc_context_read ON %I.%I FOR SELECT TO anvil_kyc_context_owner USING(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',pair[1],pair[2]);
 END LOOP;
END $$;
CREATE FUNCTION banking.product_policy_trial_binding(p_trial uuid,p_generation integer) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('application_id',paid.application_id,'resolved_task_id',paid.resolved_task_id,
 'resolved_input',jsonb_build_object('id',v.id,'sha256',v.content_sha256),'native_binding',plan.config->'golden_native_binding',
 'task_id',task.task_key,'revision_id',task.revision,'snapshot',application.snapshot,'snapshot_sha256',application.snapshot_sha256,
 'federal_refs',template.spec#>'{execution,federalPolicies}',
 'template_qualification_source_sha256',q.receipt->>'source_sha256',
 'policy_scope',(v.body_canonical::jsonb->'scope')||jsonb_build_object('source_sha256',preparation.snapshot->>'source_sha256',
  'export_sha256',v.body_canonical::jsonb->>'source_package_sha256','task_id',task.task_key,'revision_id',task.revision,
  'workflow_product',source_task#>>'{case_selector,value}','payload_sha256',task.private_reference_sha256,
  'workflow_review_receipt_sha256',source_task->>'review_receipt_sha256','export_contract','praxis.authored-task-export.v1',
  'selector_field','product','template',source_task->'template',
  'template_qualification_receipt_sha256',source_task->>'template_qualification_receipt_sha256',
  'resolved_input_id',v.id,'resolved_input_sha256',v.content_sha256))
 FROM banking.paid_agent_bindings paid
 JOIN banking.trials trial ON trial.project_id=paid.project_id AND trial.id=paid.trial_id AND trial.generation=paid.generation
 JOIN anvil.harbor_agent_plans plan ON plan.project_id=paid.project_id AND plan.id=paid.plan_id
 JOIN anvil.kyc_resolved_input_versions v ON v.project_id=paid.project_id
  AND v.id::text=plan.config#>>'{golden_native_binding,resolved_input,id}'
  AND v.content_sha256=plan.config#>>'{golden_native_binding,resolved_input,sha256}'
 JOIN anvil.praxis_resolved_tasks task ON task.project_id=paid.project_id AND task.id=paid.resolved_task_id AND task.resolution_id=v.resolution_id
 JOIN anvil.project_binding_versions preparation ON preparation.project_id=v.project_id AND preparation.id=v.project_binding_id
 JOIN banking.anvil_imports imported ON imported.project_id=v.project_id AND imported.id=v.case_import_id AND imported.id=paid.import_id
 JOIN banking.applications application ON application.project_id=paid.project_id AND application.pack_id=imported.pack_id AND application.id=paid.application_id
 CROSS JOIN LATERAL jsonb_array_elements(v.body_canonical::jsonb->'tasks') source_task
 JOIN anvil.praxis_template_versions template ON template.project_id=task.project_id AND template.id=task.template_id
 JOIN anvil.praxis_template_qualifications q ON q.project_id=task.project_id AND q.template_id=template.id
  AND q.id::text=task.binding->>'qualification_id' AND q.status='qualified'
 WHERE paid.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND paid.trial_id=p_trial AND paid.generation=p_generation
 AND trial.assigned_user::text=current_setting('anvil.user',true)
 AND task.binding->>'task_mode'='reusable_application_workflow'
 AND plan.config#>>'{golden_native_binding,task_mode}'='reusable_application_workflow'
 AND preparation.snapshot_sha256=v.body_canonical::jsonb#>>'{scope,project_binding_sha256}'
 AND v.body_canonical::jsonb->'source_anvil_requirements'='[]'::jsonb
 AND source_task->>'task_id'=task.task_key AND source_task->>'revision_id'=task.revision
 AND q.receipt_sha256=source_task->>'template_qualification_receipt_sha256'
 AND EXISTS(SELECT 1 FROM jsonb_array_elements(v.body_canonical::jsonb->'rows') member
  WHERE member->>'application_id'=paid.application_id AND member->>'task_id'=task.task_key
  AND member->>'revision_id'=task.revision AND member->>'application_sha256'=application.snapshot_sha256
  AND member->>'product'=application.snapshot->>'product' AND member->>'governing_state'=application.snapshot->>'governing_state')
 AND NOT EXISTS(SELECT 1 FROM anvil.praxis_template_revocations r WHERE r.project_id=q.project_id AND r.qualification_id=q.id);
$$;
REVOKE ALL ON FUNCTION banking.product_policy_trial_binding(uuid,integer) FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION banking.product_policy_trial_binding(uuid,integer) TO anvil_golden_scheduler;
GRANT CREATE ON SCHEMA banking TO anvil_kyc_context_owner;
ALTER FUNCTION banking.product_policy_trial_binding(uuid,integer) OWNER TO anvil_kyc_context_owner;
REVOKE CREATE ON SCHEMA banking FROM anvil_kyc_context_owner;
CREATE FUNCTION banking.product_policy_trial_mode(p_trial uuid,p_generation integer) RETURNS text
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT plan.config#>>'{golden_native_binding,task_mode}'
 FROM banking.paid_agent_bindings paid
 JOIN banking.trials trial ON trial.project_id=paid.project_id AND trial.id=paid.trial_id AND trial.generation=paid.generation
 JOIN anvil.harbor_agent_plans plan ON plan.project_id=paid.project_id AND plan.id=paid.plan_id
 WHERE paid.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND paid.trial_id=p_trial AND paid.generation=p_generation
 AND trial.assigned_user::text=current_setting('anvil.user',true);
$$;
REVOKE ALL ON FUNCTION banking.product_policy_trial_mode(uuid,integer) FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION banking.product_policy_trial_mode(uuid,integer) TO anvil_golden_scheduler;
GRANT CREATE ON SCHEMA banking TO anvil_kyc_context_owner;
ALTER FUNCTION banking.product_policy_trial_mode(uuid,integer) OWNER TO anvil_kyc_context_owner;
REVOKE CREATE ON SCHEMA banking FROM anvil_kyc_context_owner;
-- Server-minted episode clock at the existing one-attempt job claim. A caller
-- remaining_seconds field cannot extend this immutable cross-host authority.
CREATE TABLE banking.paid_episode_bounds(
 job_id uuid PRIMARY KEY REFERENCES anvil.jobs(id),project_id uuid NOT NULL REFERENCES anvil.projects(id),
 plan_id uuid NOT NULL,actor_id uuid NOT NULL REFERENCES anvil.users(id),
 lease_sha256 text NOT NULL CHECK(lease_sha256~'^[a-f0-9]{64}$'),
 plan_subject_sha256 text NOT NULL CHECK(plan_subject_sha256~'^[a-f0-9]{64}$'),
 started_at timestamptz NOT NULL,deadline_at timestamptz NOT NULL,
 CHECK(deadline_at>started_at AND deadline_at<=started_at+interval '600 seconds'),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id));
ALTER TABLE banking.paid_episode_bounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking.paid_episode_bounds FORCE ROW LEVEL SECURITY;
REVOKE ALL ON banking.paid_episode_bounds FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_qualifier;
GRANT SELECT ON banking.paid_episode_bounds TO anvil_app,anvil_golden_scheduler;
CREATE POLICY app_read ON banking.paid_episode_bounds FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY scheduler_read ON banking.paid_episode_bounds FOR SELECT TO anvil_golden_scheduler USING(banking.runtime_scope(project_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.paid_episode_bounds FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON banking.paid_episode_bounds FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable();
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_episode_owner') THEN
  CREATE ROLE anvil_kyc_episode_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_episode_owner'
  AND (rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
 OR pg_has_role('anvil_app','anvil_kyc_episode_owner','MEMBER') OR pg_has_role('anvil_worker','anvil_kyc_episode_owner','MEMBER')
 OR pg_has_role('anvil_golden_scheduler','anvil_kyc_episode_owner','MEMBER') OR pg_has_role('anvil_golden_grader','anvil_kyc_episode_owner','MEMBER')
 OR pg_has_role('anvil_kyc_qualifier','anvil_kyc_episode_owner','MEMBER') OR pg_has_role('anvil_kyc_context_owner','anvil_kyc_episode_owner','MEMBER')
 THEN RAISE EXCEPTION 'disjoint KYC episode clock owner required';END IF;
END $$;
GRANT USAGE ON SCHEMA anvil,banking TO anvil_kyc_episode_owner;
GRANT SELECT ON anvil.jobs,anvil.harbor_checks,anvil.harbor_agent_plans TO anvil_kyc_episode_owner;
GRANT UPDATE(status,lease_token,lease_until) ON anvil.jobs TO anvil_kyc_episode_owner;
GRANT INSERT ON banking.paid_episode_bounds TO anvil_kyc_episode_owner;
CREATE POLICY episode_clock_append ON banking.paid_episode_bounds FOR INSERT TO anvil_kyc_episode_owner
 WITH CHECK(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE POLICY episode_job_read ON anvil.jobs FOR SELECT TO anvil_kyc_episode_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE POLICY episode_job_claim ON anvil.jobs FOR UPDATE TO anvil_kyc_episode_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid)
 WITH CHECK(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE POLICY episode_check_read ON anvil.harbor_checks FOR SELECT TO anvil_kyc_episode_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE POLICY episode_plan_read ON anvil.harbor_agent_plans FOR SELECT TO anvil_kyc_episode_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE OR REPLACE FUNCTION banking.claim_paid_agent_job() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j anvil.jobs%ROWTYPE;p anvil.harbor_agent_plans%ROWTYPE;token uuid;
 started timestamptz;deadline timestamptz;seconds integer;
BEGIN
 SELECT q.* INTO j FROM anvil.jobs q
 JOIN anvil.harbor_checks h ON h.id=q.target_id AND h.project_id=q.project_id
 JOIN anvil.harbor_agent_plans a ON a.id=h.agent_plan_id AND a.project_id=q.project_id
 WHERE q.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND q.kind='benchmark_golden_paid' AND q.status='queued'
 AND h.state='queued' AND NOT h.cancel_requested AND h.invocation_count=0
 AND a.state='launched' AND a.config->>'golden_kyc_paid'='true'
 ORDER BY q.created_at,q.id FOR UPDATE OF q SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT * INTO p FROM anvil.harbor_agent_plans WHERE check_id=j.target_id AND project_id=j.project_id;
 IF NOT FOUND OR jsonb_typeof(p.config->'episode_timeout_seconds') IS DISTINCT FROM 'number'
 OR (p.config->>'episode_timeout_seconds')!~'^[1-9][0-9]{0,2}$'
 THEN RAISE EXCEPTION 'exact frozen KYC episode bound required';END IF;
 seconds=(p.config->>'episode_timeout_seconds')::integer;
 IF seconds>600 THEN RAISE EXCEPTION 'frozen KYC episode interval exceeded';END IF;
 token=gen_random_uuid();started=clock_timestamp();deadline=started+make_interval(secs=>seconds);
 UPDATE anvil.jobs SET status='leased',lease_token=token,lease_until=started+interval '240 seconds' WHERE id=j.id;
 INSERT INTO banking.paid_episode_bounds(job_id,project_id,plan_id,actor_id,lease_sha256,plan_subject_sha256,started_at,deadline_at)
 VALUES(j.id,j.project_id,p.id,p.created_by,encode(sha256(convert_to(token::text,'UTF8')),'hex'),p.subject_hash,started,deadline);
 RETURN jsonb_build_object('id',j.id,'project_id',j.project_id,'target_id',j.target_id,'lease_token',token,'actor_id',p.created_by,'plan_id',p.id,
  'episode_cutoff',jsonb_build_object('schema_version','anvil.kyc-episode-cutoff.v1','started_at',started,'deadline_at',deadline,
   'observed_at',clock_timestamp(),'plan_subject_sha256',p.subject_hash));
END $$;
REVOKE ALL ON FUNCTION banking.claim_paid_agent_job() FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_grader,anvil_kyc_qualifier;
GRANT EXECUTE ON FUNCTION banking.claim_paid_agent_job() TO anvil_golden_scheduler;
GRANT CREATE ON SCHEMA banking TO anvil_kyc_episode_owner;
ALTER FUNCTION banking.claim_paid_agent_job() OWNER TO anvil_kyc_episode_owner;
REVOKE CREATE ON SCHEMA banking FROM anvil_kyc_episode_owner;
INSERT INTO anvil.schema_versions(version) VALUES(127);
