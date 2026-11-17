-- Golden-specific physical requests remain inside the SAME071 group reservation.
-- No policy, provider credential, rights approval, live flag or refund is seeded.
-- Existing global id uniqueness already implies this scoped key; declare it for
-- composite foreign-key enforcement rather than weakening the project binding.
ALTER TABLE anvil.harbor_agent_calls ADD CONSTRAINT golden_paid_call_project_identity UNIQUE(project_id,id);
CREATE TABLE anvil.golden_paid_manifests(
 project_id uuid NOT NULL,group_id uuid PRIMARY KEY,subject_hash text NOT NULL,
 manifest jsonb NOT NULL,manifest_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id));
CREATE TABLE anvil.golden_paid_call_claims(
 project_id uuid NOT NULL,group_id uuid NOT NULL,call_id uuid PRIMARY KEY,
 request_key text NOT NULL,request_sha256 text NOT NULL,bound_micro_usd bigint NOT NULL CHECK(bound_micro_usd>0),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(group_id,request_key),
 FOREIGN KEY(group_id) REFERENCES anvil.golden_paid_manifests(group_id),
 FOREIGN KEY(project_id,call_id) REFERENCES anvil.harbor_agent_calls(project_id,id));
ALTER TABLE anvil.golden_paid_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.golden_paid_manifests FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON anvil.golden_paid_manifests FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY admin_insert ON anvil.golden_paid_manifests FOR INSERT TO anvil_app WITH CHECK(
 anvil.golden_engineer(project_id) AND anvil.benchmark_is_admin(project_id,created_by)
 AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
GRANT SELECT,INSERT ON anvil.golden_paid_manifests TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.golden_paid_manifests FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
ALTER TABLE anvil.golden_paid_call_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.golden_paid_call_claims FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON anvil.golden_paid_call_claims FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
GRANT SELECT ON anvil.golden_paid_call_claims TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.golden_paid_call_claims FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE FUNCTION anvil.claim_golden_paid_call(p_group uuid,p_plan uuid,p_call uuid,p_request text,p_manifest text,p_bound bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE g anvil.workspace_execution_groups%ROWTYPE;m anvil.golden_paid_manifests%ROWTYPE;
 r anvil.pilot_budget_reservations%ROWTYPE;budget anvil.pilot_budget_policies%ROWTYPE;
 plan anvil.harbor_agent_plans%ROWTYPE;invocation anvil.harbor_agent_calls%ROWTYPE;used bigint;
BEGIN
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE id=p_group FOR UPDATE;
 IF NOT FOUND OR g.state<>'launched' OR g.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid
 OR g.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid OR NOT anvil.golden_engineer(g.project_id) THEN RETURN false;END IF;
 SELECT * INTO m FROM anvil.golden_paid_manifests WHERE group_id=g.id AND project_id=g.project_id;
 IF NOT FOUND OR m.subject_hash<>g.subject_hash OR m.manifest_sha256 IS DISTINCT FROM p_manifest OR p_bound IS NULL OR p_bound<=0 THEN RETURN false;END IF;
 SELECT * INTO r FROM anvil.pilot_budget_reservations WHERE group_id=g.id;
 IF NOT FOUND OR r.environment<>'qa' OR r.project_id<>g.project_id OR r.subject_hash<>g.subject_hash
 OR r.amount_micro_usd<>(m.manifest->>'aggregate_cap_micro_usd')::bigint THEN RETURN false;END IF;
 SELECT * INTO budget FROM anvil.pilot_budget_policies WHERE environment='qa' FOR SHARE;
 IF NOT FOUND OR budget.status<>'active' OR now()<budget.start_at OR now()>=budget.end_at THEN RETURN false;END IF;
 SELECT * INTO plan FROM anvil.harbor_agent_plans WHERE id=p_plan AND project_id=g.project_id;
 IF NOT FOUND OR plan.state<>'launched' OR plan.created_by IS DISTINCT FROM g.created_by OR plan.config->>'golden_kyc_paid' IS DISTINCT FROM 'true' OR plan.config->>'workspace_execution_group' IS DISTINCT FROM g.id::text OR (plan.config ? 'golden_paid_manifest_sha256' AND plan.config->>'golden_paid_manifest_sha256' IS DISTINCT FROM p_manifest) THEN RETURN false;END IF;
 SELECT * INTO invocation FROM anvil.harbor_agent_calls WHERE id=p_call AND plan_id=p_plan AND project_id=g.project_id FOR UPDATE;
 IF NOT FOUND OR invocation.status<>'dispatching' OR invocation.usage->>'pilot_broker_claimed'='true'
 OR p_bound>invocation.reserved_micro_usd THEN RETURN false;END IF;
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(m.manifest->'requests') q WHERE q->>'id'=p_request
 AND q->>'plan_id'=p_plan::text AND (q->>'stage_index')::int=invocation.stage_index
 AND q->>'provider'=plan.config->'workspace_model'->>'provider'
 AND q->>'model_id'=plan.config->'workspace_model'->>'model_id'
 AND (q->>'maximum_micro_usd')::bigint=p_bound) THEN RETURN false;END IF;
 IF EXISTS(SELECT 1 FROM anvil.golden_paid_call_claims WHERE call_id=p_call OR(group_id=g.id AND request_key=p_request)) THEN RETURN false;END IF;
 SELECT coalesce(sum(bound_micro_usd),0) INTO used FROM anvil.golden_paid_call_claims WHERE group_id=g.id;
 IF used+p_bound>r.amount_micro_usd THEN RETURN false;END IF;
 INSERT INTO anvil.golden_paid_call_claims(project_id,group_id,call_id,request_key,request_sha256,bound_micro_usd)
 VALUES(g.project_id,g.id,p_call,p_request,invocation.request_sha256,p_bound);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION anvil.claim_golden_paid_call(uuid,uuid,uuid,text,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_golden_paid_call(uuid,uuid,uuid,text,text,bigint) TO anvil_app;

-- Candidate prompt inputs are strictly separated from trial tokens and graders.
ALTER TABLE anvil.praxis_resolved_tasks ADD CONSTRAINT golden_paid_task_project_identity UNIQUE(project_id,id);
CREATE TABLE banking.paid_agent_bindings(
 project_id uuid NOT NULL,plan_id uuid PRIMARY KEY,group_id uuid NOT NULL,import_id uuid NOT NULL,
 trial_id uuid NOT NULL,application_id text NOT NULL,generation integer NOT NULL CHECK(generation>=0),
 runtime_sha256 text NOT NULL,resolved_task_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id),
 FOREIGN KEY(project_id,import_id) REFERENCES banking.anvil_imports(project_id,id),
 FOREIGN KEY(project_id,resolved_task_id) REFERENCES anvil.praxis_resolved_tasks(project_id,id),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id));
CREATE TABLE banking.paid_agent_observations(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,stage_index integer NOT NULL CHECK(stage_index>=0),
 action_sha256 text NOT NULL,observation jsonb NOT NULL,observation_sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(plan_id,stage_index),
 FOREIGN KEY(plan_id) REFERENCES banking.paid_agent_bindings(plan_id));
ALTER TABLE banking.paid_agent_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking.paid_agent_bindings FORCE ROW LEVEL SECURITY;
CREATE POLICY paid_binding_read ON banking.paid_agent_bindings FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY paid_binding_scheduler ON banking.paid_agent_bindings TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
GRANT SELECT ON banking.paid_agent_bindings TO anvil_app;
GRANT SELECT,INSERT ON banking.paid_agent_bindings TO anvil_golden_scheduler;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.paid_agent_bindings FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
ALTER TABLE banking.paid_agent_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking.paid_agent_observations FORCE ROW LEVEL SECURITY;
CREATE POLICY paid_observation_read ON banking.paid_agent_observations FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY paid_observation_scheduler ON banking.paid_agent_observations TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
GRANT SELECT ON banking.paid_agent_observations TO anvil_app;
GRANT SELECT,INSERT ON banking.paid_agent_observations TO anvil_golden_scheduler;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.paid_agent_observations FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
REVOKE INSERT ON banking.paid_agent_bindings,banking.paid_agent_observations FROM anvil_golden_scheduler;

CREATE FUNCTION banking.bind_paid_agent_trial(p_job uuid,p_token uuid,p_plan uuid,p_trial uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,banking,pg_temp AS $$
DECLARE p anvil.harbor_agent_plans%ROWTYPE;t banking.trials%ROWTYPE;
BEGIN
 SELECT a.* INTO p FROM anvil.harbor_agent_plans a
 JOIN anvil.jobs j ON j.target_id=a.check_id AND j.project_id=a.project_id
 JOIN anvil.harbor_checks h ON h.id=a.check_id AND h.project_id=a.project_id
 WHERE a.id=p_plan AND a.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND a.state='launched' AND a.config->>'golden_kyc_paid'='true'
 AND j.id=p_job AND j.kind='benchmark_golden_paid' AND j.status='leased'
 AND j.lease_token=p_token AND j.lease_until>now() AND h.state='running' AND NOT h.cancel_requested;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO t FROM banking.trials WHERE id=p_trial AND project_id=p.project_id FOR UPDATE;
 IF NOT FOUND OR t.pack_id::text IS DISTINCT FROM p.config->'golden_native_binding'->>'pack_id'
 OR t.application_id IS DISTINCT FROM p.config->'golden_native_binding'->>'application_id'
 OR t.assigned_user IS DISTINCT FROM p.created_by OR t.generation<>1 OR t.closed
 OR t.created_at<(SELECT started_at FROM anvil.harbor_checks WHERE id=p.check_id)
 OR EXISTS(SELECT 1 FROM banking.events WHERE trial_id=t.id AND action<>'reset')
 OR EXISTS(SELECT 1 FROM banking.paid_agent_bindings WHERE plan_id=p.id OR trial_id=t.id)
 THEN RETURN false; END IF;
 INSERT INTO banking.paid_agent_bindings(project_id,plan_id,group_id,import_id,trial_id,application_id,generation,runtime_sha256,resolved_task_id,created_by)
 VALUES(p.project_id,p.id,(p.config->>'workspace_execution_group')::uuid,
 (p.config->'golden_native_binding'->>'import_id')::uuid,t.id,t.application_id,t.generation,
 p.config->'golden_native_binding'->>'runtime_sha256',
 (p.config->'golden_native_binding'->>'resolved_task_id')::uuid,p.created_by);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION banking.bind_paid_agent_trial(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.bind_paid_agent_trial(uuid,uuid,uuid,uuid) TO anvil_golden_scheduler;

-- Narrow scheduler RPCs, rather than granting the private service normal-worker
-- or API table/credential access. Never reclaim a leased/uncertain paid job.
CREATE FUNCTION banking.claim_paid_agent_job() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,banking,pg_temp AS $$
DECLARE j anvil.jobs%ROWTYPE;p anvil.harbor_agent_plans%ROWTYPE; token uuid;
BEGIN
 SELECT q.* INTO j FROM anvil.jobs q
 JOIN anvil.harbor_checks h ON h.id=q.target_id AND h.project_id=q.project_id
 JOIN anvil.harbor_agent_plans a ON a.id=h.agent_plan_id AND a.project_id=q.project_id
 WHERE q.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND q.kind='benchmark_golden_paid' AND q.status='queued'
 AND h.state='queued' AND NOT h.cancel_requested AND h.invocation_count=0
 AND a.state='launched' AND a.config->>'golden_kyc_paid'='true'
 ORDER BY q.created_at,q.id FOR UPDATE OF q SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO p FROM anvil.harbor_agent_plans WHERE check_id=j.target_id AND project_id=j.project_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'native plan missing'; END IF;
 token=gen_random_uuid();
 UPDATE anvil.jobs SET status='leased',lease_token=token,lease_until=now()+interval '240 seconds' WHERE id=j.id;
 RETURN jsonb_build_object('id',j.id,'project_id',j.project_id,'target_id',j.target_id,
 'lease_token',token,'actor_id',p.created_by,'plan_id',p.id);
END $$;
REVOKE ALL ON FUNCTION banking.claim_paid_agent_job() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.claim_paid_agent_job() TO anvil_golden_scheduler;

CREATE FUNCTION banking.heartbeat_paid_agent_job(p_job uuid,p_token uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,banking,pg_temp AS $$
BEGIN
 UPDATE anvil.jobs SET lease_until=now()+interval '240 seconds'
 WHERE id=p_job AND project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND kind='benchmark_golden_paid' AND status='leased' AND lease_token=p_token AND lease_until>now();
 RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION banking.heartbeat_paid_agent_job(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.heartbeat_paid_agent_job(uuid,uuid) TO anvil_golden_scheduler;

CREATE FUNCTION banking.record_paid_agent_turn(p_job uuid,p_token uuid,p_plan uuid,p_stage integer,p_text text,p_action_sha text,p_observation jsonb,p_observation_sha text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,banking,pg_temp AS $$
DECLARE project uuid;
BEGIN
 SELECT j.project_id INTO project FROM anvil.jobs j
 JOIN anvil.harbor_agent_plans p ON p.check_id=j.target_id AND p.project_id=j.project_id
 WHERE j.id=p_job AND j.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND j.kind='benchmark_golden_paid' AND j.status='leased' AND j.lease_token=p_token AND j.lease_until>now()
 AND p.id=p_plan AND p.config->>'golden_kyc_paid'='true';
 IF NOT FOUND OR octet_length(p_text)>65536 OR octet_length(p_observation::text)>262144
 OR p_action_sha!~'^[a-f0-9]{64}$' OR p_observation_sha!~'^[a-f0-9]{64}$'
 OR p_stage<0 OR p_stage<>(SELECT count(*) FROM banking.paid_agent_observations WHERE plan_id=p_plan)
 OR NOT EXISTS(SELECT 1 FROM anvil.harbor_agent_calls WHERE project_id=project AND plan_id=p_plan
 AND stage_index=p_stage AND status='completed' AND output_json->>'text'=p_text)
 THEN RETURN false; END IF;
 INSERT INTO banking.paid_agent_observations(project_id,plan_id,stage_index,action_sha256,observation,observation_sha256)
 VALUES(project,p_plan,p_stage,p_action_sha,p_observation,p_observation_sha);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION banking.record_paid_agent_turn(uuid,uuid,uuid,integer,text,text,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.record_paid_agent_turn(uuid,uuid,uuid,integer,text,text,jsonb,text) TO anvil_golden_scheduler;

-- API sees hashes and closure only, never the sealed evaluator state/token.
CREATE FUNCTION banking.paid_agent_capture(p_plan uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,banking,pg_temp AS $$
 SELECT jsonb_build_object('trial_id',b.trial_id,'generation',b.generation,
 'closed',t.closed,'state_sha256',s.state_sha256,'runtime_sha256',b.runtime_sha256,
 'resolved_task_id',b.resolved_task_id,'application_id',b.application_id,
 'turns',(SELECT count(*) FROM banking.paid_agent_observations o WHERE o.plan_id=b.plan_id))
 FROM banking.paid_agent_bindings b JOIN banking.trials t ON t.id=b.trial_id AND t.project_id=b.project_id
 LEFT JOIN banking.seals s ON s.trial_id=b.trial_id AND s.project_id=b.project_id AND s.generation=b.generation
 WHERE b.plan_id=p_plan AND b.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND t.generation=b.generation AND anvil.golden_engineer(b.project_id)
$$;
REVOKE ALL ON FUNCTION banking.paid_agent_capture(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.paid_agent_capture(uuid) TO anvil_app;

GRANT SELECT ON banking.paid_agent_bindings TO anvil_golden_grader;
CREATE POLICY paid_binding_grader ON banking.paid_agent_bindings FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
CREATE FUNCTION banking.paid_agent_provenance(p_plan uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,banking,pg_temp AS $$
 SELECT jsonb_build_object('provider_calls',count(*) FILTER(WHERE a.usage->>'dispatch_origin'='provider'),
 'mock_calls',count(*) FILTER(WHERE a.usage->>'dispatch_origin'='sdk_mock'),
 'completed_calls',count(*) FILTER(WHERE a.status='completed'),
 'total_calls',count(*))
 FROM anvil.harbor_agent_calls a WHERE a.plan_id=p_plan
 AND a.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND EXISTS(SELECT 1 FROM banking.paid_agent_bindings b WHERE b.plan_id=p_plan AND b.project_id=a.project_id)
$$;
REVOKE ALL ON FUNCTION banking.paid_agent_provenance(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.paid_agent_provenance(uuid) TO anvil_golden_grader;

CREATE TABLE banking.paid_agent_captures(
 project_id uuid NOT NULL,plan_id uuid PRIMARY KEY,trial_id uuid NOT NULL,generation integer NOT NULL,
 state_sha256 text NOT NULL,turn_count integer NOT NULL CHECK(turn_count>0),job_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(plan_id) REFERENCES banking.paid_agent_bindings(plan_id),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id),
 FOREIGN KEY(job_id) REFERENCES anvil.jobs(id));
ALTER TABLE banking.paid_agent_captures ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking.paid_agent_captures FORCE ROW LEVEL SECURITY;
CREATE POLICY paid_capture_app ON banking.paid_agent_captures FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY paid_capture_grader ON banking.paid_agent_captures FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT ON banking.paid_agent_captures TO anvil_app,anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.paid_agent_captures FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE FUNCTION banking.finalize_paid_agent_capture(p_job uuid,p_token uuid,p_plan uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,banking,pg_temp AS $$
DECLARE b banking.paid_agent_bindings%ROWTYPE;s banking.seals%ROWTYPE;n integer;
BEGIN
 SELECT x.* INTO b FROM banking.paid_agent_bindings x
 JOIN anvil.harbor_agent_plans p ON p.id=x.plan_id AND p.project_id=x.project_id
 JOIN anvil.jobs j ON j.target_id=p.check_id AND j.project_id=p.project_id
 JOIN anvil.harbor_checks h ON h.id=p.check_id AND h.project_id=p.project_id
 WHERE x.plan_id=p_plan AND x.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND p.created_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.golden_engineer(x.project_id)
 AND p.state='launched' AND p.config->>'golden_kyc_paid'='true'
 AND j.id=p_job AND j.kind='benchmark_golden_paid' AND j.status='leased'
 AND j.lease_token=p_token AND j.lease_until>now() AND h.state='running' AND NOT h.cancel_requested;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM banking.trials t WHERE t.id=b.trial_id AND t.project_id=b.project_id AND t.generation=b.generation AND t.closed) THEN RETURN false; END IF;
 SELECT * INTO s FROM banking.seals WHERE trial_id=b.trial_id AND project_id=b.project_id AND generation=b.generation;
 IF NOT FOUND OR s.state->'final' IS NULL OR s.state->'final'='null'::jsonb THEN RETURN false; END IF;
 SELECT count(*) INTO n FROM anvil.harbor_agent_calls WHERE project_id=b.project_id AND plan_id=b.plan_id;
 IF n=0 OR EXISTS(SELECT 1 FROM anvil.harbor_agent_calls a WHERE a.plan_id=b.plan_id
 AND (a.status<>'completed' OR NOT EXISTS(SELECT 1 FROM banking.paid_agent_observations o WHERE o.project_id=b.project_id AND o.plan_id=b.plan_id AND o.stage_index=a.stage_index)))
 OR n<>(SELECT count(*) FROM banking.paid_agent_observations WHERE plan_id=b.plan_id) THEN RETURN false; END IF;
 INSERT INTO banking.paid_agent_captures(project_id,plan_id,trial_id,generation,state_sha256,turn_count,job_id)
 VALUES(b.project_id,b.plan_id,b.trial_id,b.generation,s.state_sha256,n,p_job);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION banking.finalize_paid_agent_capture(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.finalize_paid_agent_capture(uuid,uuid,uuid) TO anvil_app;
