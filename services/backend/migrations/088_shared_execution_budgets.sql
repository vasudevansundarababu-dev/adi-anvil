-- One non-refundable envelope covers governed AI purposes AND benchmark runs.
-- No policy, authorization, model credential or paid activation is seeded.
CREATE TABLE anvil.shared_execution_budgets(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,
 source_sha256 text NOT NULL CHECK(source_sha256~'^[a-f0-9]{64}$'),
 models jsonb NOT NULL CHECK(jsonb_typeof(models)='array' AND jsonb_array_length(models) BETWEEN 1 AND 8),
 cap_micro_usd bigint NOT NULL CHECK(cap_micro_usd>0 AND cap_micro_usd<=2000000),
 created_by uuid NOT NULL REFERENCES anvil.users(id),rights_confirmed boolean NOT NULL CHECK(rights_confirmed),
 created_at timestamptz NOT NULL DEFAULT now(),expires_at timestamptz NOT NULL,
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),
 UNIQUE(project_id,id),UNIQUE(task_group_id),CHECK(expires_at>created_at AND expires_at<=created_at+interval '30 days' AND expires_at<='2026-12-11T05:48:04Z'));
CREATE TABLE anvil.shared_execution_budget_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,budget_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,budget_id) REFERENCES anvil.shared_execution_budgets(project_id,id),UNIQUE(budget_id));
CREATE TABLE anvil.shared_execution_budget_reservations(
 project_id uuid NOT NULL,budget_id uuid PRIMARY KEY,environment text NOT NULL CHECK(environment='qa'),
 amount_micro_usd bigint NOT NULL CHECK(amount_micro_usd>0),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,budget_id) REFERENCES anvil.shared_execution_budgets(project_id,id));
CREATE TABLE anvil.shared_execution_group_allocations(
 project_id uuid NOT NULL,budget_id uuid NOT NULL,group_id uuid PRIMARY KEY,
 amount_micro_usd bigint NOT NULL CHECK(amount_micro_usd>0),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,budget_id) REFERENCES anvil.shared_execution_budgets(project_id,id),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id));
CREATE TABLE anvil.governed_ai_calls(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,budget_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 purpose text NOT NULL CHECK(purpose IN('evaluator_recommendation','method_recommendation','safety_generation','custom_code_generation')),
 request_key text NOT NULL,request jsonb NOT NULL CHECK(octet_length(request::text)<=131072),
 request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),model_binding jsonb NOT NULL,
 bound_micro_usd bigint NOT NULL CHECK(bound_micro_usd>0),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN('queued','dispatching','completed','error','execution_unknown')),
 broker_claimed boolean NOT NULL DEFAULT false,dispatch_token uuid,result jsonb,result_sha256 text,
 actual_micro_usd bigint CHECK(actual_micro_usd>=0),created_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
 FOREIGN KEY(project_id,budget_id) REFERENCES anvil.shared_execution_budgets(project_id,id),
 UNIQUE(project_id,id),UNIQUE(budget_id,request_key));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['shared_execution_budgets','shared_execution_budget_revocations','shared_execution_budget_reservations','shared_execution_group_allocations','governed_ai_calls'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['shared_execution_budgets','shared_execution_budget_revocations'] LOOP
  EXECUTE format('CREATE POLICY admin_insert ON anvil.%I FOR INSERT TO anvil_app WITH CHECK(anvil.benchmark_is_admin(project_id,nullif(current_setting(''anvil.user'',true),'''')::uuid) AND created_by=nullif(current_setting(''anvil.user'',true),'''')::uuid)',t);
  EXECUTE format('GRANT INSERT ON anvil.%I TO anvil_app',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['shared_execution_budgets','shared_execution_budget_revocations','shared_execution_budget_reservations','shared_execution_group_allocations'] LOOP
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;

CREATE FUNCTION anvil.shared_execution_budget_active(p_id uuid) RETURNS boolean
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM anvil.shared_execution_budgets b JOIN anvil.benchmark_task_groups g ON g.id=b.task_group_id AND g.project_id=b.project_id
 JOIN anvil.users u ON u.id=b.created_by AND u.active
 JOIN anvil.memberships m ON m.user_id=b.created_by AND m.project_id=b.project_id AND m.role='admin' AND m.active
 WHERE b.id=p_id AND b.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND b.rights_confirmed AND b.expires_at>clock_timestamp() AND b.source_sha256=g.content_sha256
 AND NOT EXISTS(SELECT 1 FROM anvil.shared_execution_budget_revocations r WHERE r.budget_id=b.id))
 $$;

CREATE FUNCTION anvil.reserve_shared_execution_budget(p_id uuid) RETURNS bigint
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE b anvil.shared_execution_budgets%ROWTYPE;p anvil.pilot_budget_policies%ROWTYPE;r anvil.shared_execution_budget_reservations%ROWTYPE;m jsonb;
BEGIN
 SELECT * INTO b FROM anvil.shared_execution_budgets WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR NOT anvil.shared_execution_budget_active(p_id)
 OR NOT anvil.golden_engineer(b.project_id)
 THEN RAISE EXCEPTION 'current scoped shared budget Admin authority required';END IF;
 SELECT * INTO p FROM anvil.pilot_budget_policies WHERE environment='qa' FOR UPDATE;
 IF NOT FOUND OR p.status<>'active' OR clock_timestamp()<p.start_at OR clock_timestamp()>=p.end_at OR b.cap_micro_usd>p.run_micro_usd THEN RAISE EXCEPTION 'current QA pilot policy required';END IF;
 FOR m IN SELECT value FROM jsonb_array_elements(b.models) LOOP
  IF NOT '[{"provider":"openai","model_id":"gpt-6.1-sol"},{"provider":"anthropic","model_id":"claude-opus-5-5"},{"provider":"gemini","model_id":"gemini-4-argon"}]'::jsonb
   @> jsonb_build_array(jsonb_build_object('provider',m->>'provider','model_id',m->>'model_id')) THEN RAISE EXCEPTION 'unapproved shared budget model';END IF;
 END LOOP;
 SELECT * INTO r FROM anvil.shared_execution_budget_reservations WHERE budget_id=b.id;
 IF FOUND THEN
  IF r.project_id<>b.project_id OR r.environment<>'qa' OR r.amount_micro_usd<>b.cap_micro_usd THEN RAISE EXCEPTION 'shared reservation binding differs';END IF;RETURN b.cap_micro_usd;
 END IF;
 IF p.committed_micro_usd+b.cap_micro_usd>p.total_micro_usd THEN RAISE EXCEPTION 'QA pilot total exhausted';END IF;
 INSERT INTO anvil.shared_execution_budget_reservations(project_id,budget_id,environment,amount_micro_usd) VALUES(b.project_id,b.id,'qa',b.cap_micro_usd);
 UPDATE anvil.pilot_budget_policies SET committed_micro_usd=committed_micro_usd+b.cap_micro_usd WHERE environment='qa';
 RETURN b.cap_micro_usd;
END $$;

CREATE FUNCTION anvil.reserve_governed_ai_call(p_budget uuid,p_id uuid,p_purpose text,p_key text,p_request jsonb,p_hash text,p_model jsonb,p_bound bigint)
 RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE b anvil.shared_execution_budgets%ROWTYPE;old anvil.governed_ai_calls%ROWTYPE;used bigint;BEGIN
 PERFORM anvil.reserve_shared_execution_budget(p_budget);
 SELECT * INTO b FROM anvil.shared_execution_budgets WHERE id=p_budget FOR UPDATE;
 IF NOT anvil.benchmark_is_admin(b.project_id,nullif(current_setting('anvil.user',true),'')::uuid) THEN RAISE EXCEPTION 'current Admin AI processing authority required';END IF;
 IF NOT b.models @> jsonb_build_array(p_model) OR p_bound IS NULL OR p_bound<=0 THEN RAISE EXCEPTION 'exact approved model and bounded purpose required';END IF;
 SELECT * INTO old FROM anvil.governed_ai_calls WHERE budget_id=p_budget AND request_key=p_key;
 IF FOUND THEN
  IF old.request_sha256<>p_hash OR old.purpose<>p_purpose OR old.model_binding<>p_model OR old.bound_micro_usd<>p_bound THEN RAISE EXCEPTION 'immutable AI request replay differs';END IF;RETURN old.id;
 END IF;
 SELECT coalesce(sum(bound_micro_usd),0) INTO used FROM anvil.governed_ai_calls WHERE budget_id=p_budget;
 used=used+(SELECT coalesce(sum(amount_micro_usd),0) FROM anvil.shared_execution_group_allocations WHERE budget_id=p_budget);
 IF used+p_bound>b.cap_micro_usd THEN RAISE EXCEPTION 'shared AI and benchmark budget exhausted';END IF;
 INSERT INTO anvil.governed_ai_calls(id,project_id,budget_id,created_by,purpose,request_key,request,request_sha256,model_binding,bound_micro_usd)
 VALUES(p_id,b.project_id,b.id,nullif(current_setting('anvil.user',true),'')::uuid,p_purpose,p_key,p_request,p_hash,p_model,p_bound);
 RETURN p_id;
END $$;

-- Preserve071's original authorization/model/policy checks for all groups. A
-- parent-funded group takes its allocation from the SAME already-held envelope.
CREATE OR REPLACE FUNCTION anvil.reserve_pilot_budget(p_environment text,p_group uuid) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE g anvil.workspace_execution_groups%ROWTYPE;p anvil.pilot_budget_policies%ROWTYPE;r anvil.pilot_budget_reservations%ROWTYPE;
 b anvil.shared_execution_budgets%ROWTYPE;budget uuid;required_budget uuid;binding anvil.project_binding_versions%ROWTYPE;cap bigint;used bigint;m jsonb;allowed jsonb;
BEGIN
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE id=p_group FOR UPDATE;
 IF NOT FOUND OR g.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid OR NOT anvil.golden_engineer(g.project_id) THEN RAISE EXCEPTION 'scoped pilot group required';END IF;
 budget=(g.snapshot->'preparation'->>'execution_budget_id')::uuid;
 IF (g.snapshot->'preparation'->>'candidate_runtime' IN('golden-kyc-openenv-tool-agent-v1','marketing-task2-five-role-v1')
 OR g.snapshot->'preparation'->'preset'->>'candidate_runtime' IN('golden-kyc-openenv-tool-agent-v1','marketing-task2-five-role-v1')
 OR g.snapshot->'preparation'->'package'->'manifest'->>'binding' IN('golden-kyc-openenv-tool-agent-v1','marketing-task2-five-role-v1')
 OR EXISTS(SELECT 1 FROM anvil.workspace_execution_models m JOIN anvil.harbor_agent_plans a ON a.id=m.plan_id AND a.project_id=m.project_id WHERE m.project_id=g.project_id AND m.group_id=g.id AND (a.config->>'golden_kyc_paid'='true' OR a.config->>'marketing_task2_paid'='true')))
 AND budget IS NULL THEN RAISE EXCEPTION 'Golden execution requires its frozen shared aggregate budget';END IF;
 SELECT * INTO binding FROM anvil.project_binding_versions WHERE project_id=g.project_id AND id=(g.snapshot->'preparation'->'project_binding'->>'id')::uuid;
 IF FOUND THEN
  SELECT id INTO required_budget FROM anvil.shared_execution_budgets WHERE project_id=g.project_id AND task_group_id=binding.task_group_id;
  IF required_budget IS NOT NULL AND budget IS DISTINCT FROM required_budget THEN RAISE EXCEPTION 'existing shared budget cannot be bypassed';END IF;
 END IF;
 IF budget IS NOT NULL THEN
  IF p_environment<>'qa' THEN RAISE EXCEPTION 'shared budget restricted to QA';END IF;
  PERFORM anvil.reserve_shared_execution_budget(budget);
  SELECT * INTO b FROM anvil.shared_execution_budgets WHERE id=budget FOR UPDATE;
  IF binding.id IS NULL OR binding.task_group_id<>b.task_group_id OR binding.snapshot->>'source_sha256'<>b.source_sha256
   OR g.snapshot->'preparation'->'project_binding'->>'snapshot_sha256'<>binding.snapshot_sha256
   THEN RAISE EXCEPTION 'shared budget source binding differs';END IF;
 END IF;
 SELECT * INTO p FROM anvil.pilot_budget_policies WHERE environment=p_environment FOR UPDATE;
 IF NOT FOUND OR p.status<>'active' OR now()<p.start_at OR now()>=p.end_at THEN RAISE EXCEPTION 'pilot authority absent expired or closed';END IF;
 cap=(g.snapshot->'preparation'->>'aggregate_cap_micro_usd')::bigint;
 IF cap IS NULL OR cap<=0 OR cap>p.run_micro_usd THEN RAISE EXCEPTION 'pilot per-Run ceiling exceeded';END IF;
 IF NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_authorizations a JOIN anvil.users u ON u.id=a.admin_id AND u.active JOIN anvil.memberships m ON m.project_id=a.project_id AND m.user_id=a.admin_id AND m.active AND m.role='admin' WHERE a.group_id=g.id AND a.project_id=g.project_id AND a.subject_hash=g.subject_hash AND a.cap_micro_usd=cap AND a.rights_confirmed AND a.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_revocations v WHERE v.authorization_id=a.id)) THEN RAISE EXCEPTION 'current exact Admin run authority required';END IF;
 allowed=CASE p_environment WHEN 'qa' THEN '[{"provider":"openai","model_id":"gpt-6.1-sol"},{"provider":"anthropic","model_id":"claude-opus-5-5"},{"provider":"gemini","model_id":"gemini-4-argon"}]'::jsonb ELSE '[{"provider":"openai","model_id":"gpt-6.1-sol"},{"provider":"openai","model_id":"gpt-6-astra"},{"provider":"anthropic","model_id":"claude-opus-5-5"},{"provider":"anthropic","model_id":"claude-fable-5-2"},{"provider":"gemini","model_id":"gemini-4-argon"},{"provider":"gemini","model_id":"gemini-4-carbon"}]'::jsonb END;
 IF jsonb_typeof(g.snapshot->'preparation'->'models') IS DISTINCT FROM 'array' OR jsonb_array_length(g.snapshot->'preparation'->'models')=0 THEN RAISE EXCEPTION 'exact pilot models required';END IF;
 FOR m IN SELECT value FROM jsonb_array_elements(g.snapshot->'preparation'->'models') LOOP
  IF NOT allowed @> jsonb_build_array(jsonb_build_object('provider',m->>'provider','model_id',m->>'model_id')) OR (budget IS NOT NULL AND NOT b.models @> jsonb_build_array(m)) THEN RAISE EXCEPTION 'unapproved pilot model';END IF;
 END LOOP;
 SELECT * INTO r FROM anvil.pilot_budget_reservations WHERE group_id=g.id;
 IF FOUND THEN
  IF r.environment<>p_environment OR r.project_id<>g.project_id OR r.subject_hash<>g.subject_hash OR r.amount_micro_usd<>cap THEN RAISE EXCEPTION 'pilot reservation replay differs';END IF;RETURN cap;
 END IF;
 IF budget IS NOT NULL THEN
  SELECT coalesce(sum(bound_micro_usd),0) INTO used FROM anvil.governed_ai_calls WHERE budget_id=budget;
  used=used+(SELECT coalesce(sum(amount_micro_usd),0) FROM anvil.shared_execution_group_allocations WHERE budget_id=budget);
  IF used+cap>b.cap_micro_usd THEN RAISE EXCEPTION 'shared AI and benchmark budget exhausted';END IF;
  INSERT INTO anvil.shared_execution_group_allocations(project_id,budget_id,group_id,amount_micro_usd) VALUES(g.project_id,budget,g.id,cap);
 ELSE
  IF p.committed_micro_usd+cap>p.total_micro_usd THEN RAISE EXCEPTION 'pilot total exhausted';END IF;
  UPDATE anvil.pilot_budget_policies SET committed_micro_usd=committed_micro_usd+cap WHERE environment=p_environment;
 END IF;
 INSERT INTO anvil.pilot_budget_reservations(environment,project_id,group_id,subject_hash,amount_micro_usd) VALUES(p_environment,g.project_id,g.id,g.subject_hash,cap);
 RETURN cap;
END $$;

CREATE FUNCTION anvil.shared_budget_dispatch_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE budget uuid;BEGIN
 SELECT budget_id INTO budget FROM anvil.shared_execution_group_allocations WHERE group_id=NEW.group_id AND project_id=NEW.project_id;
 IF budget IS NULL OR NOT anvil.shared_execution_budget_active(budget) THEN RAISE EXCEPTION 'Golden physical dispatch requires current shared aggregate budget';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER shared_budget_authority BEFORE INSERT ON anvil.golden_paid_call_claims FOR EACH ROW EXECUTE FUNCTION anvil.shared_budget_dispatch_guard();

CREATE FUNCTION anvil.shared_budget_revocation_lock() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 PERFORM 1 FROM anvil.shared_execution_budgets WHERE id=NEW.budget_id AND project_id=NEW.project_id FOR UPDATE;
 RETURN NEW;END $$;
CREATE TRIGGER serialize_revocation BEFORE INSERT ON anvil.shared_execution_budget_revocations FOR EACH ROW EXECUTE FUNCTION anvil.shared_budget_revocation_lock();

REVOKE ALL ON FUNCTION anvil.shared_execution_budget_active(uuid),anvil.reserve_shared_execution_budget(uuid),anvil.reserve_governed_ai_call(uuid,uuid,text,text,jsonb,text,jsonb,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.shared_execution_budget_active(uuid),anvil.reserve_shared_execution_budget(uuid),anvil.reserve_governed_ai_call(uuid,uuid,text,text,jsonb,text,jsonb,bigint) TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(88);
