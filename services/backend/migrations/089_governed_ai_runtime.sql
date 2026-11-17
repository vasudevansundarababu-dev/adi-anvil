-- Candidate eligibility comes from privileged independent controls, never an AI
-- assertion or a client's ready flag. Empty coverage blocks generation.
CREATE TABLE anvil.task_capability_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,target text NOT NULL,
 kind text NOT NULL CHECK(kind IN('evaluator','method','safety')),candidate_id text NOT NULL,candidate_sha256 text NOT NULL CHECK(candidate_sha256~'^[a-f0-9]{64}$'),
 source_sha256 text NOT NULL,release_sha256 text NOT NULL,evidence jsonb NOT NULL,evidence_sha256 text NOT NULL,
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.task_capability_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.task_capability_qualifications(project_id,id),UNIQUE(qualification_id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['task_capability_qualifications','task_capability_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE FUNCTION anvil.task_capability_revocation_lock() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 PERFORM 1 FROM anvil.task_capability_qualifications WHERE id=NEW.qualification_id AND project_id=NEW.project_id FOR UPDATE;
 RETURN NEW;END $$;
CREATE TRIGGER serialize_revocation BEFORE INSERT ON anvil.task_capability_revocations FOR EACH ROW EXECUTE FUNCTION anvil.task_capability_revocation_lock();
CREATE FUNCTION anvil.governed_evaluator_change_lock() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 PERFORM 1 FROM anvil.evaluator_configurations WHERE id=NEW.configuration_id AND project_id=NEW.project_id FOR UPDATE;
 RETURN NEW;END $$;
CREATE TRIGGER governed_change_lock BEFORE INSERT ON anvil.evaluator_revocations FOR EACH ROW EXECUTE FUNCTION anvil.governed_evaluator_change_lock();
CREATE TRIGGER governed_change_lock BEFORE INSERT ON anvil.evaluator_validation_receipts FOR EACH ROW EXECUTE FUNCTION anvil.governed_evaluator_change_lock();

CREATE OR REPLACE FUNCTION anvil.pilot_dispatch_capacity() RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE env text;cap integer;used bigint;BEGIN
 SELECT environment INTO STRICT env FROM anvil.pilot_budget_policies;
 cap=CASE env WHEN 'qa' THEN 2 WHEN 'staging' THEN 1 ELSE 0 END;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil:pilot-dispatch-capacity',0));
 SELECT count(*) INTO used FROM anvil.harbor_agent_calls WHERE status IN('dispatching','execution_unknown') AND usage->>'pilot_broker_claimed'='true';
 used=used+(SELECT count(*) FROM anvil.governed_ai_calls WHERE state IN('dispatching','execution_unknown') AND broker_claimed);
 RETURN used<cap;
END $$;

CREATE FUNCTION anvil.governed_ai_custody() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR (NEW.id,NEW.project_id,NEW.budget_id,NEW.created_by,NEW.purpose,NEW.request_key,NEW.request,NEW.request_sha256,NEW.model_binding,NEW.bound_micro_usd,NEW.created_at)
 IS DISTINCT FROM(OLD.id,OLD.project_id,OLD.budget_id,OLD.created_by,OLD.purpose,OLD.request_key,OLD.request,OLD.request_sha256,OLD.model_binding,OLD.bound_micro_usd,OLD.created_at)
 OR OLD.state IN('completed','error','execution_unknown') THEN RAISE EXCEPTION 'immutable AI intent or terminal receipt';END IF;
 IF OLD.state='queued' THEN
  IF NEW.state<>'dispatching' OR NEW.dispatch_token IS NULL OR NEW.broker_claimed OR NEW.result IS NOT NULL THEN RAISE EXCEPTION 'once-only AI dispatch intent required';END IF;
 ELSIF NEW.dispatch_token IS DISTINCT FROM OLD.dispatch_token OR NEW.broker_claimed<OLD.broker_claimed THEN RAISE EXCEPTION 'immutable AI dispatch capability';
 ELSIF NEW.state='dispatching' THEN
  IF OLD.broker_claimed OR NOT NEW.broker_claimed OR NEW.result IS NOT NULL THEN RAISE EXCEPTION 'once-only AI broker claim required';END IF;
 ELSIF NEW.state NOT IN('completed','error','execution_unknown') OR NEW.result IS NULL OR NEW.result_sha256 IS NULL OR NEW.finished_at IS NULL THEN RAISE EXCEPTION 'terminal AI receipt required';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER custody BEFORE UPDATE OR DELETE ON anvil.governed_ai_calls FOR EACH ROW EXECUTE FUNCTION anvil.governed_ai_custody();

CREATE FUNCTION anvil.claim_governed_ai_job() RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE j anvil.jobs%ROWTYPE;a anvil.governed_ai_calls%ROWTYPE;token uuid;BEGIN
 SELECT q.* INTO j FROM anvil.jobs q JOIN anvil.governed_ai_calls c ON c.id=q.target_id AND c.project_id=q.project_id
 WHERE q.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND q.kind='benchmark_governed_ai' AND q.status='queued' AND c.state='queued'
 AND anvil.shared_execution_budget_active(c.budget_id) AND anvil.benchmark_is_admin(c.project_id,c.created_by)
 ORDER BY q.created_at,q.id FOR UPDATE OF q SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL;END IF;
 token=gen_random_uuid();UPDATE anvil.jobs SET status='leased',lease_token=token,lease_until=clock_timestamp()+interval '180 seconds',attempts=attempts+1 WHERE id=j.id;
 SELECT * INTO a FROM anvil.governed_ai_calls WHERE id=j.target_id;
 RETURN jsonb_build_object('job_id',j.id,'project_id',j.project_id,'actor_id',a.created_by,'call_id',a.id,'lease_token',token);
END $$;
REVOKE ALL ON FUNCTION anvil.claim_governed_ai_job() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_governed_ai_job() TO anvil_golden_scheduler;

CREATE FUNCTION anvil.start_governed_ai_call(p_job uuid,p_lease uuid,p_call uuid) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE a anvil.governed_ai_calls%ROWTYPE;token uuid;BEGIN
 SELECT c.* INTO a FROM anvil.governed_ai_calls c JOIN anvil.jobs j ON j.target_id=c.id AND j.project_id=c.project_id
 WHERE c.id=p_call AND c.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND c.created_by=nullif(current_setting('anvil.user',true),'')::uuid AND c.state='queued'
 AND j.id=p_job AND j.kind='benchmark_governed_ai' AND j.status='leased' AND j.lease_token=p_lease AND j.lease_until>clock_timestamp()
 FOR UPDATE OF c;
 IF NOT FOUND OR NOT anvil.shared_execution_budget_active(a.budget_id) OR NOT anvil.benchmark_is_admin(a.project_id,a.created_by) THEN RETURN NULL;END IF;
 token=gen_random_uuid();UPDATE anvil.governed_ai_calls SET state='dispatching',dispatch_token=token WHERE id=a.id;
 RETURN token;
END $$;

CREATE FUNCTION anvil.claim_governed_ai_sdk(p_job uuid,p_lease uuid,p_call uuid,p_dispatch uuid,p_hash text,p_model jsonb) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE a anvil.governed_ai_calls%ROWTYPE;issuing_admin_id uuid;BEGIN
 SELECT * INTO a FROM anvil.governed_ai_calls WHERE id=p_call AND project_id=nullif(current_setting('anvil.project',true),'')::uuid FOR UPDATE;
 IF NOT FOUND OR a.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid OR a.state<>'dispatching' OR a.broker_claimed
 OR a.dispatch_token IS DISTINCT FROM p_dispatch OR a.model_binding IS DISTINCT FROM p_model OR a.request->>'prompt_sha256' IS DISTINCT FROM p_hash THEN RETURN false;END IF;
 PERFORM 1 FROM anvil.shared_execution_budgets WHERE id=a.budget_id FOR UPDATE;
 SELECT created_by INTO issuing_admin_id FROM anvil.shared_execution_budgets WHERE id=a.budget_id;
 PERFORM 1 FROM anvil.users WHERE id IN(issuing_admin_id,a.created_by) ORDER BY id FOR SHARE;
 PERFORM 1 FROM anvil.memberships WHERE project_id=a.project_id AND user_id IN(issuing_admin_id,a.created_by) ORDER BY user_id FOR SHARE;
 PERFORM 1 FROM anvil.workspace_model_profiles p JOIN anvil.workspace_model_versions v ON v.profile_id=p.id AND v.project_id=p.project_id WHERE v.connection_id=(a.model_binding->>'id')::uuid ORDER BY p.id FOR SHARE OF p;
 PERFORM 1 FROM anvil.workspace_credentials WHERE id=(a.model_binding->'credential'->>'id')::uuid FOR SHARE;
 PERFORM 1 FROM anvil.connections WHERE id=(a.model_binding->>'id')::uuid FOR SHARE;
 IF NOT anvil.shared_execution_budget_active(a.budget_id) OR NOT anvil.benchmark_is_admin(a.project_id,a.created_by)
 OR NOT EXISTS(SELECT 1 FROM anvil.jobs WHERE id=p_job AND project_id=a.project_id AND target_id=a.id AND kind='benchmark_governed_ai' AND status='leased' AND lease_token=p_lease AND lease_until>clock_timestamp())
 OR NOT EXISTS(SELECT 1 FROM anvil.pilot_budget_policies WHERE environment='qa' AND status='active' AND start_at<=clock_timestamp() AND end_at>clock_timestamp())
 OR NOT anvil.pilot_dispatch_capacity() THEN RETURN false;END IF;
 IF NOT EXISTS(SELECT 1 FROM anvil.connections c JOIN anvil.workspace_model_versions v ON v.connection_id=c.id
 JOIN anvil.workspace_model_profiles p ON p.id=v.profile_id AND p.project_id=v.project_id
 JOIN anvil.workspace_credentials h ON h.id=(a.model_binding->'credential'->>'id')::uuid AND h.project_id=c.project_id
 WHERE c.id=(a.model_binding->>'id')::uuid AND c.project_id=a.project_id AND c.status<>'revoked'
 AND c.config_hash=a.model_binding->>'config_hash' AND p.current_connection_id=c.id AND p.disabled_at IS NULL
 AND h.revoked_at IS NULL AND h.current_version_id=(a.model_binding->'credential'->>'version_id')::uuid) THEN RETURN false;END IF;
 IF jsonb_typeof(a.request->'qualifications') IS DISTINCT FROM 'array' THEN RETURN false;END IF;
 PERFORM 1 FROM anvil.task_capability_qualifications q WHERE q.project_id=a.project_id
 AND q.id IN(SELECT (v->>'id')::uuid FROM jsonb_array_elements(a.request->'qualifications') v) ORDER BY q.id FOR SHARE;
 PERFORM 1 FROM anvil.evaluator_configurations e JOIN anvil.task_capability_qualifications q ON q.candidate_id=e.id::text AND q.kind='evaluator' AND q.project_id=e.project_id
 WHERE q.id IN(SELECT (v->>'id')::uuid FROM jsonb_array_elements(a.request->'qualifications') v) ORDER BY e.id FOR SHARE OF e;
 IF jsonb_typeof(a.request->'qualifications') IS DISTINCT FROM 'array'
 OR (a.purpose<>'custom_code_generation' AND jsonb_array_length(a.request->'qualifications')=0)
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(a.request->'qualifications') v WHERE NOT EXISTS(
  SELECT 1 FROM anvil.task_capability_qualifications q JOIN anvil.shared_execution_budgets b ON b.id=a.budget_id
  WHERE q.id=(v->>'id')::uuid AND q.project_id=a.project_id AND q.task_group_id=b.task_group_id
  AND q.source_sha256=b.source_sha256 AND q.release_sha256=a.request->>'release_sha256'
  AND q.evidence_sha256=v->>'evidence_sha256' AND q.candidate_sha256=v->>'candidate_sha256'
  AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.task_capability_revocations r WHERE r.qualification_id=q.id)
  AND NOT EXISTS(SELECT 1 FROM anvil.evaluator_revocations r WHERE q.kind='evaluator' AND r.configuration_id::text=q.candidate_id)
 )) THEN RETURN false;END IF;
 UPDATE anvil.governed_ai_calls SET broker_claimed=true WHERE id=a.id;
 RETURN true;
END $$;

CREATE FUNCTION anvil.finish_governed_ai_call(p_call uuid,p_token uuid,p_state text,p_result jsonb,p_hash text,p_cost bigint) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 IF p_state NOT IN('completed','error','execution_unknown') OR octet_length(p_result::text)>262144 OR p_hash!~'^[a-f0-9]{64}$' THEN RETURN false;END IF;
 UPDATE anvil.governed_ai_calls SET state=p_state,result=p_result,result_sha256=p_hash,actual_micro_usd=p_cost,finished_at=clock_timestamp()
 WHERE id=p_call AND project_id=nullif(current_setting('anvil.project',true),'')::uuid AND created_by=nullif(current_setting('anvil.user',true),'')::uuid AND state='dispatching' AND dispatch_token=p_token;
 IF NOT FOUND THEN RETURN false;END IF;
 INSERT INTO anvil.audit_events(project_id,actor_id,action,target_id,metadata)
 SELECT project_id,created_by,'governed_ai.completed',id,jsonb_build_object('state',p_state,'result_sha256',p_hash,'actual_micro_usd',p_cost)
 FROM anvil.governed_ai_calls WHERE id=p_call;
 UPDATE anvil.jobs SET status=CASE WHEN p_state='completed' THEN 'succeeded' ELSE 'failed' END,error_code=p_result->>'error_code'
 WHERE target_id=p_call AND project_id=nullif(current_setting('anvil.project',true),'')::uuid AND kind='benchmark_governed_ai' AND status='leased';
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION anvil.start_governed_ai_call(uuid,uuid,uuid),anvil.claim_governed_ai_sdk(uuid,uuid,uuid,uuid,text,jsonb),anvil.finish_governed_ai_call(uuid,uuid,text,jsonb,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.start_governed_ai_call(uuid,uuid,uuid),anvil.claim_governed_ai_sdk(uuid,uuid,uuid,uuid,text,jsonb),anvil.finish_governed_ai_call(uuid,uuid,text,jsonb,text,bigint) TO anvil_app;

CREATE FUNCTION anvil.lock_governed_ai_completion(p_call uuid,p_token uuid) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE a anvil.governed_ai_calls%ROWTYPE;issuing_admin_id uuid;BEGIN
 SELECT * INTO a FROM anvil.governed_ai_calls WHERE id=p_call AND project_id=nullif(current_setting('anvil.project',true),'')::uuid AND created_by=nullif(current_setting('anvil.user',true),'')::uuid AND dispatch_token=p_token AND state='dispatching' FOR UPDATE;
 IF NOT FOUND THEN RETURN false;END IF;
 PERFORM 1 FROM anvil.shared_execution_budgets WHERE id=a.budget_id FOR UPDATE;
 SELECT created_by INTO issuing_admin_id FROM anvil.shared_execution_budgets WHERE id=a.budget_id;
 PERFORM 1 FROM anvil.users WHERE id IN(issuing_admin_id,a.created_by) ORDER BY id FOR SHARE;
 PERFORM 1 FROM anvil.memberships WHERE project_id=a.project_id AND user_id IN(issuing_admin_id,a.created_by) ORDER BY user_id FOR SHARE;
 PERFORM 1 FROM anvil.workspace_model_profiles p JOIN anvil.workspace_model_versions v ON v.profile_id=p.id AND v.project_id=p.project_id WHERE v.connection_id=(a.model_binding->>'id')::uuid FOR SHARE OF p;
 PERFORM 1 FROM anvil.workspace_credentials WHERE id=(a.model_binding->'credential'->>'id')::uuid FOR SHARE;
 PERFORM 1 FROM anvil.task_capability_qualifications q WHERE q.id IN(SELECT (v->>'id')::uuid FROM jsonb_array_elements(a.request->'qualifications') v) ORDER BY q.id FOR SHARE;
 PERFORM 1 FROM anvil.evaluator_configurations e JOIN anvil.task_capability_qualifications q ON q.candidate_id=e.id::text AND q.kind='evaluator' AND q.project_id=e.project_id
 WHERE q.id IN(SELECT (v->>'id')::uuid FROM jsonb_array_elements(a.request->'qualifications') v) ORDER BY e.id FOR SHARE OF e;
 RETURN anvil.shared_execution_budget_active(a.budget_id) AND anvil.benchmark_is_admin(a.project_id,a.created_by);
END $$;
REVOKE ALL ON FUNCTION anvil.lock_governed_ai_completion(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.lock_governed_ai_completion(uuid,uuid) TO anvil_app;

CREATE FUNCTION anvil.reconcile_governed_ai_call(p_call uuid,p_hash text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE a anvil.governed_ai_calls%ROWTYPE;j anvil.jobs%ROWTYPE;receipt jsonb;state text;BEGIN
 SELECT * INTO a FROM anvil.governed_ai_calls WHERE id=p_call AND project_id=nullif(current_setting('anvil.project',true),'')::uuid FOR UPDATE;
 IF NOT FOUND OR NOT anvil.benchmark_is_admin(a.project_id,nullif(current_setting('anvil.user',true),'')::uuid) OR a.request_sha256 IS DISTINCT FROM p_hash THEN RETURN NULL;END IF;
 IF a.state IN('completed','error','execution_unknown') THEN RETURN jsonb_build_object('already_terminal',true,'state',a.state,'physical_request_replayed',false);END IF;
 SELECT * INTO j FROM anvil.jobs WHERE project_id=a.project_id AND target_id=a.id AND kind='benchmark_governed_ai' FOR UPDATE;
 IF NOT FOUND OR j.lease_until IS NULL OR j.lease_until>clock_timestamp() THEN RETURN NULL;END IF;
 state=CASE WHEN a.broker_claimed THEN 'execution_unknown' ELSE 'error' END;
 IF a.state='queued' THEN
  UPDATE anvil.governed_ai_calls SET state='dispatching',dispatch_token=gen_random_uuid() WHERE id=a.id;
 END IF;
 receipt=jsonb_build_object('schema_version','anvil.governed-ai-result.v1','origin','operational_reconciliation',
  'request_sha256',a.request_sha256,'output',NULL,'model_performance',false,'physical_request_replayed',false,
  'error_code',CASE WHEN a.broker_claimed THEN 'physical_request_unconfirmed_after_lease_expiry' ELSE 'not_dispatched_before_lease_expiry' END,
  'model_request_may_have_occurred',a.broker_claimed,'bound_retained_micro_usd',a.bound_micro_usd);
 -- Use a canonical custody hash supplied by the trusted caller in a separate
 -- finish operation; this function returns status/receipt only until then.
 RETURN jsonb_build_object('state',state,'receipt',receipt,'dispatch_token',(SELECT dispatch_token FROM anvil.governed_ai_calls WHERE id=a.id));
END $$;
REVOKE ALL ON FUNCTION anvil.reconcile_governed_ai_call(uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.reconcile_governed_ai_call(uuid,text) TO anvil_app;
CREATE FUNCTION anvil.finish_ai_reconciliation(p_call uuid,p_hash text,p_receipt jsonb,p_result_hash text) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ DECLARE disposition jsonb;BEGIN
 disposition=anvil.reconcile_governed_ai_call(p_call,p_hash);
 IF disposition IS NULL OR disposition ? 'already_terminal' OR disposition->'receipt' IS DISTINCT FROM p_receipt OR p_result_hash!~'^[a-f0-9]{64}$' THEN RETURN false;END IF;
 UPDATE anvil.governed_ai_calls SET state=disposition->>'state',result=p_receipt,result_sha256=p_result_hash,finished_at=clock_timestamp()
 WHERE id=p_call AND state='dispatching';
 UPDATE anvil.jobs SET status='failed',error_code='governed_ai_reconciled_unconfirmed' WHERE target_id=p_call AND project_id=nullif(current_setting('anvil.project',true),'')::uuid AND kind='benchmark_governed_ai';
 RETURN true;END $$;
REVOKE ALL ON FUNCTION anvil.finish_ai_reconciliation(uuid,text,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.finish_ai_reconciliation(uuid,text,jsonb,text) TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(89);
