-- Marketing has its own case/role custody. No banking trial impersonation,
-- credential, approval, pilot activation or source qualification is seeded.
-- The old8models×10repeats ceiling predates shared case populations. Preserve
-- the explicit1000priced-slot group admission fence, without rejecting ordinal80.
ALTER TABLE anvil.workspace_execution_models DROP CONSTRAINT workspace_execution_models_ordinal_check;
ALTER TABLE anvil.workspace_execution_models ADD CONSTRAINT workspace_execution_models_ordinal_check CHECK(ordinal BETWEEN 0 AND 999);
GRANT USAGE ON SCHEMA marketing_runtime TO anvil_app;
CREATE TABLE marketing_runtime.paid_agent_bindings(
 project_id uuid NOT NULL,plan_id uuid PRIMARY KEY,group_id uuid NOT NULL,task_group_id uuid NOT NULL,
 resolved_task_id uuid NOT NULL,dataset_id uuid NOT NULL,case_id text NOT NULL,
 native_binding jsonb NOT NULL CHECK(octet_length(native_binding::text)<=65536),
 native_binding_sha256 text NOT NULL CHECK(native_binding_sha256~'^[a-f0-9]{64}$'),
 execution jsonb NOT NULL CHECK(octet_length(execution::text)<=131072),
 execution_sha256 text NOT NULL CHECK(execution_sha256~'^[a-f0-9]{64}$'),
 max_calls integer NOT NULL CHECK(max_calls BETWEEN 1 AND 1000),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),
 FOREIGN KEY(project_id,resolved_task_id) REFERENCES anvil.praxis_resolved_tasks(project_id,id),
 FOREIGN KEY(project_id,dataset_id) REFERENCES anvil.campaign_dataset_versions(project_id,id),UNIQUE(project_id,plan_id));
CREATE FUNCTION marketing_runtime.guard_paid_binding() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE p anvil.harbor_agent_plans;r anvil.praxis_resolved_tasks;t anvil.praxis_template_versions;BEGIN
 SELECT * INTO p FROM anvil.harbor_agent_plans WHERE project_id=NEW.project_id AND id=NEW.plan_id;
 SELECT * INTO r FROM anvil.praxis_resolved_tasks WHERE project_id=NEW.project_id AND id=NEW.resolved_task_id;
 SELECT * INTO t FROM anvil.praxis_template_versions WHERE project_id=NEW.project_id AND id=r.template_id;
 IF p.id IS NULL OR r.id IS NULL OR t.id IS NULL OR p.state<>'draft' OR p.created_by IS DISTINCT FROM NEW.created_by
 OR NOT EXISTS(SELECT 1 FROM anvil.workspace_execution_groups g WHERE g.project_id=NEW.project_id AND g.id=NEW.group_id AND g.state='draft')
 OR p.config->>'marketing_paid' IS DISTINCT FROM 'true' OR p.config->>'golden_kyc_paid'='true'
 OR p.config->>'workspace_execution_group' IS DISTINCT FROM NEW.group_id::text
 OR p.config->'marketing_native_binding' IS DISTINCT FROM NEW.native_binding
 OR p.config->>'max_calls' IS DISTINCT FROM NEW.max_calls::text
 OR NEW.native_binding->>'task_group_id' IS DISTINCT FROM NEW.task_group_id::text
 OR NEW.native_binding->>'resolved_task_id' IS DISTINCT FROM r.id::text
 OR NEW.native_binding->>'resolved_binding_sha256' IS DISTINCT FROM r.binding_sha256
 OR NEW.native_binding->>'dataset_import_id' IS DISTINCT FROM NEW.dataset_id::text
 OR NEW.native_binding->'case_assignment'->>'case_id' IS DISTINCT FROM NEW.case_id
 OR NEW.execution IS DISTINCT FROM t.spec->'execution'
 OR NEW.execution_sha256 IS DISTINCT FROM r.binding->>'execution_sha256'
 OR NEW.native_binding->>'execution_sha256' IS DISTINCT FROM NEW.execution_sha256
 OR r.binding->>'task_mode' IS DISTINCT FROM 'reusable_campaign_workflow'
 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.native_binding->'cases') m
  WHERE m->>'id'=NEW.case_id AND m->>'snapshot_sha256'=NEW.native_binding->'case_assignment'->>'snapshot_sha256'
  AND m->>'locale'=NEW.native_binding->'case_assignment'->>'locale')
 THEN RAISE EXCEPTION 'exact Marketing native plan/source binding required';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER exact_source BEFORE INSERT ON marketing_runtime.paid_agent_bindings FOR EACH ROW EXECUTE FUNCTION marketing_runtime.guard_paid_binding();
CREATE TABLE marketing_runtime.paid_episode_links(
 project_id uuid NOT NULL,plan_id uuid PRIMARY KEY,episode_id uuid NOT NULL,generation integer NOT NULL CHECK(generation>=0),
 job_id uuid NOT NULL,lease_sha256 text NOT NULL CHECK(lease_sha256~'^[a-f0-9]{64}$'),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES marketing_runtime.paid_agent_bindings(project_id,plan_id),
 FOREIGN KEY(project_id,episode_id) REFERENCES marketing_runtime.episodes(project_id,id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.jobs(project_id,id),UNIQUE(project_id,episode_id,generation));
CREATE TABLE marketing_runtime.paid_turn_intents(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,stage_index integer NOT NULL CHECK(stage_index BETWEEN 0 AND 999),
 job_id uuid NOT NULL,lease_sha256 text NOT NULL CHECK(lease_sha256~'^[a-f0-9]{64}$'),
 effect_id uuid NOT NULL REFERENCES marketing_runtime.workflow_effects(id),
 role text NOT NULL CHECK(role IN('orchestrator','intent','performance','brief','policy')),
 node_id text NOT NULL,week integer NOT NULL CHECK(week BETWEEN 1 AND 12),visit integer NOT NULL CHECK(visit BETWEEN 1 AND 400),
 public_context jsonb NOT NULL CHECK(octet_length(public_context::text)<=65536),
 public_context_sha256 text NOT NULL CHECK(public_context_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(plan_id,stage_index),
 FOREIGN KEY(project_id,plan_id) REFERENCES marketing_runtime.paid_agent_bindings(project_id,plan_id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.jobs(project_id,id),UNIQUE(project_id,plan_id,stage_index));
CREATE TABLE marketing_runtime.paid_tool_action_intents(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,stage_index integer NOT NULL,action_index integer NOT NULL CHECK(action_index BETWEEN 0 AND 7),
 call_id uuid NOT NULL,request_id uuid NOT NULL UNIQUE,operation text NOT NULL,
 arguments jsonb NOT NULL CHECK(octet_length(arguments::text)<=32768),arguments_sha256 text NOT NULL CHECK(arguments_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(plan_id,stage_index,action_index),
 FOREIGN KEY(project_id,plan_id,stage_index) REFERENCES marketing_runtime.paid_turn_intents(project_id,plan_id,stage_index),
 FOREIGN KEY(project_id,call_id) REFERENCES anvil.harbor_agent_calls(project_id,id));
CREATE TABLE marketing_runtime.paid_turn_observations(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,stage_index integer NOT NULL,call_id uuid NOT NULL,
 response_sha256 text NOT NULL CHECK(response_sha256~'^[a-f0-9]{64}$'),
 observation jsonb NOT NULL CHECK(octet_length(observation::text)<=262144),
 observation_sha256 text NOT NULL CHECK(observation_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(plan_id,stage_index),
 FOREIGN KEY(project_id,plan_id,stage_index) REFERENCES marketing_runtime.paid_turn_intents(project_id,plan_id,stage_index),
 FOREIGN KEY(project_id,call_id) REFERENCES anvil.harbor_agent_calls(project_id,id));
CREATE TABLE marketing_runtime.paid_call_claims(
 project_id uuid NOT NULL,group_id uuid NOT NULL,plan_id uuid NOT NULL,call_id uuid PRIMARY KEY,
 stage_index integer NOT NULL,bound_micro_usd bigint NOT NULL CHECK(bound_micro_usd>0),request_sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(plan_id,stage_index),
 FOREIGN KEY(project_id,plan_id,stage_index) REFERENCES marketing_runtime.paid_turn_intents(project_id,plan_id,stage_index),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id),
 FOREIGN KEY(project_id,call_id) REFERENCES anvil.harbor_agent_calls(project_id,id));
CREATE TABLE campaign_private.tool_effect_states(
 project_id uuid NOT NULL,request_id uuid PRIMARY KEY,episode_id uuid NOT NULL,generation integer NOT NULL,
 full_state_sha256 text NOT NULL CHECK(full_state_sha256~'^[a-f0-9]{64}$'),
 post_state jsonb NOT NULL CHECK(octet_length(post_state::text)<=16777216),
 post_state_sha256 text NOT NULL CHECK(post_state_sha256~'^[a-f0-9]{64}$'),
 byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 16777216),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,request_id) REFERENCES marketing_runtime.tool_receipts(project_id,id),
 FOREIGN KEY(project_id,episode_id) REFERENCES marketing_runtime.episodes(project_id,id));
ALTER TABLE campaign_private.tool_effect_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.tool_effect_states FORCE ROW LEVEL SECURITY;
CREATE POLICY private_read ON campaign_private.tool_effect_states FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT ON campaign_private.tool_effect_states TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.tool_effect_states FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['paid_agent_bindings','paid_episode_links','paid_turn_intents','paid_tool_action_intents','paid_turn_observations','paid_call_claims'] LOOP
  EXECUTE format('ALTER TABLE marketing_runtime.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE marketing_runtime.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY engineer_read ON marketing_runtime.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY runtime_read ON marketing_runtime.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('GRANT SELECT ON marketing_runtime.%I TO anvil_app,anvil_golden_scheduler,anvil_golden_grader',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON marketing_runtime.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE POLICY source_insert ON marketing_runtime.paid_agent_bindings FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
GRANT INSERT ON marketing_runtime.paid_agent_bindings TO anvil_app;
-- Narrow SECURITY DEFINER entry points below own all episode/turn/action writes.
-- Runtime/table read grants never give scheduler access to provider secrets.
CREATE FUNCTION marketing_runtime.claim_paid_agent_job() RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j anvil.jobs;p anvil.harbor_agent_plans;token uuid;BEGIN
 SELECT q.* INTO j FROM anvil.jobs q JOIN anvil.harbor_checks h ON h.id=q.target_id AND h.project_id=q.project_id
 JOIN anvil.harbor_agent_plans a ON a.id=h.agent_plan_id AND a.project_id=q.project_id
 JOIN marketing_runtime.paid_agent_bindings b ON b.plan_id=a.id AND b.project_id=a.project_id
 WHERE q.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND q.kind='benchmark_marketing_paid'
 AND q.status='queued' AND h.state='queued' AND NOT h.cancel_requested AND h.invocation_count=0
 AND a.state='launched' AND a.config->>'marketing_paid'='true'
 ORDER BY q.created_at,q.id FOR UPDATE OF q SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT * INTO p FROM anvil.harbor_agent_plans WHERE id=(SELECT agent_plan_id FROM anvil.harbor_checks WHERE id=j.target_id);
 token=gen_random_uuid();
 UPDATE anvil.jobs SET status='leased',lease_token=token,lease_until=clock_timestamp()+interval '240 seconds' WHERE id=j.id;
 RETURN jsonb_build_object('id',j.id,'project_id',j.project_id,'target_id',j.target_id,'lease_token',token,'actor_id',p.created_by,'plan_id',p.id);
END $$;
CREATE FUNCTION marketing_runtime.paid_job_current(p_job uuid,p_lease uuid,p_plan uuid) RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM anvil.jobs j JOIN anvil.harbor_agent_plans p ON p.check_id=j.target_id AND p.project_id=j.project_id
 JOIN anvil.harbor_checks h ON h.id=p.check_id AND h.project_id=p.project_id
 JOIN anvil.workspace_execution_groups g ON g.id=(p.config->>'workspace_execution_group')::uuid AND g.project_id=p.project_id
 JOIN anvil.users actor ON actor.id=p.created_by AND actor.active
 WHERE j.id=p_job AND j.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND j.kind='benchmark_marketing_paid'
 AND j.status='leased' AND j.lease_token=p_lease AND j.lease_until>clock_timestamp() AND p.id=p_plan
 AND p.state='launched' AND g.state='launched' AND p.config->>'marketing_paid'='true' AND h.state='running' AND NOT h.cancel_requested
 AND (p.config->>'episode_timeout_seconds')::integer BETWEEN 1 AND 600
 AND h.started_at IS NOT NULL AND clock_timestamp()<h.started_at+make_interval(secs=>(p.config->>'episode_timeout_seconds')::integer)
 AND NOT EXISTS(SELECT 1 FROM marketing_runtime.paid_episode_links l WHERE l.plan_id=p.id AND l.project_id=p.project_id
 AND NOT EXISTS(SELECT 1 FROM marketing_runtime.episodes e WHERE e.project_id=l.project_id AND e.id=l.episode_id
 AND e.generation=l.generation AND e.assigned_user=p.created_by))
 AND EXISTS(SELECT 1 FROM anvil.memberships m WHERE m.project_id=p.project_id AND m.user_id=p.created_by AND m.active AND m.role IN('admin','rl-engineer'))
 AND anvil.shared_execution_budget_active((g.snapshot->'preparation'->>'execution_budget_id')::uuid)
 AND EXISTS(SELECT 1 FROM anvil.workspace_admin_run_authorizations a JOIN anvil.users u ON u.id=a.admin_id AND u.active
 JOIN anvil.memberships m ON m.project_id=a.project_id AND m.user_id=a.admin_id AND m.active AND m.role='admin'
 WHERE a.group_id=g.id AND a.project_id=g.project_id AND a.subject_hash=g.subject_hash AND a.rights_confirmed AND a.expires_at>clock_timestamp()
 AND a.cap_micro_usd=(g.snapshot->'preparation'->>'aggregate_cap_micro_usd')::bigint
 AND NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_revocations r WHERE r.authorization_id=a.id)));
$$;
CREATE FUNCTION marketing_runtime.heartbeat_paid_agent_job(p_job uuid,p_lease uuid) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE changed integer;BEGIN
 UPDATE anvil.jobs j SET lease_until=clock_timestamp()+interval '240 seconds'
 WHERE j.id=p_job AND j.lease_token=p_lease AND j.status='leased' AND j.lease_until>clock_timestamp()
 AND j.kind='benchmark_marketing_paid'
 AND EXISTS(SELECT 1 FROM anvil.harbor_agent_plans p WHERE p.project_id=j.project_id AND p.check_id=j.target_id
 AND marketing_runtime.paid_job_current(j.id,p_lease,p.id));
 GET DIAGNOSTICS changed=ROW_COUNT;RETURN changed=1;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.heartbeat_paid_agent_job(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.heartbeat_paid_agent_job(uuid,uuid) TO anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.bind_paid_agent_episode(p_job uuid,p_lease uuid,p_plan uuid,p_episode uuid,p_generation integer,p_lease_sha text) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE b marketing_runtime.paid_agent_bindings;e marketing_runtime.episodes;BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) OR p_lease_sha IS DISTINCT FROM encode(sha256(convert_to(p_lease::text,'UTF8')),'hex') THEN RETURN false;END IF;
 SELECT * INTO b FROM marketing_runtime.paid_agent_bindings WHERE plan_id=p_plan;
 SELECT * INTO e FROM marketing_runtime.episodes WHERE project_id=b.project_id AND id=p_episode AND generation=p_generation;
 IF e.id IS NULL OR e.assigned_user IS DISTINCT FROM b.created_by OR e.case_id IS DISTINCT FROM b.case_id
 OR e.dataset_sha256 IS DISTINCT FROM b.native_binding->>'dataset_sha256'
 OR e.dataset_id IS DISTINCT FROM b.native_binding->'case_context'->'caseDataset'->>'id'
 OR e.dataset_version IS DISTINCT FROM b.native_binding->'case_context'->'caseDataset'->>'version'
 OR e.snapshot_sha256 IS DISTINCT FROM b.native_binding->'case_assignment'->>'snapshot_sha256'
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_episode_links WHERE plan_id=p_plan) THEN RETURN false;END IF;
 INSERT INTO marketing_runtime.paid_episode_links(project_id,plan_id,episode_id,generation,job_id,lease_sha256) VALUES(b.project_id,p_plan,p_episode,p_generation,p_job,p_lease_sha);
 RETURN true;
END $$;
CREATE FUNCTION marketing_runtime.claim_paid_turn(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_effect uuid,p_context jsonb,p_hash text,p_lease_sha text) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE b marketing_runtime.paid_agent_bindings;l marketing_runtime.paid_episode_links;e marketing_runtime.workflow_effects;n jsonb;BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) OR p_stage<0 OR p_stage>999 OR p_hash!~'^[a-f0-9]{64}$' OR p_lease_sha IS DISTINCT FROM encode(sha256(convert_to(p_lease::text,'UTF8')),'hex') THEN RETURN false;END IF;
 SELECT * INTO b FROM marketing_runtime.paid_agent_bindings WHERE plan_id=p_plan FOR SHARE;
 SELECT * INTO l FROM marketing_runtime.paid_episode_links WHERE plan_id=p_plan;
 SELECT * INTO e FROM marketing_runtime.workflow_effects WHERE id=p_effect AND project_id=b.project_id;
 SELECT v INTO n FROM jsonb_array_elements(b.execution->'workflow_graph'->'nodes') v WHERE v->>'id'=e.node_id AND v->>'type'='agent_step';
 IF l.plan_id IS NULL OR e.id IS NULL OR n IS NULL OR p_stage>=b.max_calls OR e.state<>'claimed'
 OR e.episode_id IS DISTINCT FROM l.episode_id OR e.generation IS DISTINCT FROM l.generation OR e.execution_sha256 IS DISTINCT FROM b.execution_sha256
 OR p_context->'node' IS DISTINCT FROM n OR p_context->>'role' IS DISTINCT FROM n->>'roleId'
 OR p_context->>'week' IS DISTINCT FROM e.week::text OR p_context->>'visit' IS DISTINCT FROM e.visit::text
 OR p_context->>'inputs_sha256' IS DISTINCT FROM e.input_sha256 OR p_context->>'execution_sha256' IS DISTINCT FROM b.execution_sha256
 OR p_stage<>(SELECT count(*) FROM marketing_runtime.paid_turn_observations WHERE plan_id=p_plan)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_turn_observations o JOIN marketing_runtime.paid_turn_intents prior ON prior.plan_id=o.plan_id AND prior.stage_index=o.stage_index WHERE o.plan_id=p_plan AND prior.effect_id=p_effect AND o.observation->>'completed_node'='true')
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_turn_intents WHERE plan_id=p_plan AND stage_index=p_stage) THEN RETURN false;END IF;
 INSERT INTO marketing_runtime.paid_turn_intents(project_id,plan_id,stage_index,job_id,lease_sha256,effect_id,role,node_id,week,visit,public_context,public_context_sha256)
 VALUES(b.project_id,p_plan,p_stage,p_job,p_lease_sha,p_effect,n->>'roleId',e.node_id,e.week,e.visit,p_context,p_hash);
 RETURN true;
END $$;
CREATE FUNCTION marketing_runtime.claim_paid_tool_action(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_index integer,p_call uuid,p_request uuid,p_operation text,p_arguments jsonb,p_hash text) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE b marketing_runtime.paid_agent_bindings;t marketing_runtime.paid_turn_intents;c anvil.harbor_agent_calls;v jsonb;BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) OR p_index<0 OR p_index>7 OR p_hash!~'^[a-f0-9]{64}$' THEN RETURN false;END IF;
 SELECT * INTO b FROM marketing_runtime.paid_agent_bindings WHERE plan_id=p_plan;
 SELECT * INTO t FROM marketing_runtime.paid_turn_intents WHERE plan_id=p_plan AND stage_index=p_stage;
 SELECT * INTO c FROM anvil.harbor_agent_calls WHERE id=p_call AND project_id=b.project_id AND plan_id=p_plan AND stage_index=p_stage AND status='completed';
 IF c.id IS NULL THEN RETURN false;END IF;
 v=(c.output_json->>'text')::jsonb;
 IF t.plan_id IS NULL OR jsonb_typeof(v->'actions') IS DISTINCT FROM 'array' OR v ? 'artifact'
 OR v->'actions'->p_index->>'operation' IS DISTINCT FROM p_operation
 OR v->'actions'->p_index->'arguments' IS DISTINCT FROM p_arguments
 OR p_index<>(SELECT count(*) FROM marketing_runtime.paid_tool_action_intents WHERE plan_id=p_plan AND stage_index=p_stage)
 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(b.execution->'tools') AS tool_entry(value) WHERE tool_entry.value->>'id'=p_operation AND tool_entry.value->'role_ids' ? t.role)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_tool_action_intents WHERE plan_id=p_plan AND stage_index=p_stage AND action_index=p_index)
 THEN RETURN false;END IF;
 INSERT INTO marketing_runtime.paid_tool_action_intents(project_id,plan_id,stage_index,action_index,call_id,request_id,operation,arguments,arguments_sha256)
 VALUES(b.project_id,p_plan,p_stage,p_index,p_call,p_request,p_operation,p_arguments,p_hash);
 RETURN true;
END $$;
CREATE FUNCTION marketing_runtime.capture_paid_tool_state(p_request uuid,p_view jsonb,p_hash text,p_full_hash text) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE i marketing_runtime.paid_tool_action_intents;t marketing_runtime.paid_turn_intents;
 l marketing_runtime.paid_episode_links;w marketing_runtime.workflow_effects;b marketing_runtime.paid_agent_bindings;
 r marketing_runtime.tool_receipts;e marketing_runtime.episodes;j anvil.jobs;expected jsonb;used bigint;size integer;BEGIN
 SELECT * INTO i FROM marketing_runtime.paid_tool_action_intents WHERE request_id=p_request AND project_id=nullif(current_setting('anvil.project',true),'')::uuid;
 IF NOT FOUND THEN RETURN NULL;END IF; -- Older/unpaid tool controls are not promoted.
 SELECT * INTO t FROM marketing_runtime.paid_turn_intents WHERE plan_id=i.plan_id AND stage_index=i.stage_index;
 SELECT * INTO j FROM anvil.jobs WHERE id=t.job_id;
 IF NOT marketing_runtime.paid_job_current(j.id,j.lease_token,i.plan_id) OR t.lease_sha256 IS DISTINCT FROM encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex') THEN RETURN false;END IF;
 SELECT * INTO r FROM marketing_runtime.tool_receipts WHERE id=p_request AND project_id=i.project_id;
 SELECT * INTO e FROM marketing_runtime.episodes WHERE id=r.episode_id AND project_id=r.project_id AND generation=r.generation;
 SELECT * INTO l FROM marketing_runtime.paid_episode_links WHERE plan_id=i.plan_id AND project_id=i.project_id;
 SELECT * INTO w FROM marketing_runtime.workflow_effects WHERE id=t.effect_id AND project_id=i.project_id;
 SELECT * INTO b FROM marketing_runtime.paid_agent_bindings WHERE plan_id=i.plan_id AND project_id=i.project_id;
 IF l.plan_id IS NULL OR w.id IS NULL OR b.plan_id IS NULL
 OR l.job_id IS DISTINCT FROM t.job_id OR l.lease_sha256 IS DISTINCT FROM t.lease_sha256
 OR l.episode_id IS DISTINCT FROM r.episode_id OR l.generation IS DISTINCT FROM r.generation
 OR w.episode_id IS DISTINCT FROM l.episode_id OR w.generation IS DISTINCT FROM l.generation OR w.state IS DISTINCT FROM 'claimed'
 OR w.execution_sha256 IS DISTINCT FROM b.execution_sha256 OR w.node_id IS DISTINCT FROM t.node_id
 OR w.week IS DISTINCT FROM t.week OR w.visit IS DISTINCT FROM t.visit
 OR e.assigned_user IS DISTINCT FROM b.created_by OR e.case_id IS DISTINCT FROM b.case_id
 THEN RETURN false;END IF;
 IF r.id IS NULL OR e.id IS NULL OR r.arguments_sha256 IS DISTINCT FROM i.arguments_sha256 OR r.operation IS DISTINCT FROM i.operation OR r.role IS DISTINCT FROM t.role
 OR r.state_sha256 IS DISTINCT FROM e.state_sha256 OR p_full_hash IS DISTINCT FROM e.state_sha256 OR p_hash!~'^[a-f0-9]{64}$' THEN RETURN false;END IF;
 expected=jsonb_build_object('schema_version','anvil.marketing-tool-post-state.v1','clock',e.state->'clock','objects',e.state->'objects','budget_minor',e.state->'budget_minor',
 'committed',e.state->'committed','settled',e.state->'settled','reservations',e.state->'reservations','approvals',e.state->'approvals',
 'approval_bounds',e.state->'approval_bounds','revisions',e.state->'revisions','transitions',e.state->'transitions');
 IF p_view IS DISTINCT FROM expected OR EXISTS(SELECT 1 FROM campaign_private.tool_effect_states WHERE request_id=p_request) THEN RETURN false;END IF;
 size=octet_length(p_view::text);
 PERFORM pg_advisory_xact_lock(hashtextextended('marketing-effect-state:'||i.project_id::text,0));
 SELECT coalesce(sum(byte_size),0) INTO used FROM campaign_private.tool_effect_states WHERE project_id=i.project_id;
 IF size>16777216 OR used+size>536870912 THEN RETURN false;END IF;
 INSERT INTO campaign_private.tool_effect_states(project_id,request_id,episode_id,generation,full_state_sha256,post_state,post_state_sha256,byte_size)
 VALUES(i.project_id,p_request,e.id,e.generation,p_full_hash,p_view,p_hash,size);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_paid_tool_state(uuid,jsonb,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_paid_tool_state(uuid,jsonb,text,text) TO anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.paid_agent_response(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer) RETURNS jsonb
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('id',c.id,'text',c.output_json->>'text','request_sha256',c.request_sha256,'origin',c.usage->>'dispatch_origin')
 FROM anvil.harbor_agent_calls c JOIN marketing_runtime.paid_turn_intents t ON t.project_id=c.project_id AND t.plan_id=c.plan_id AND t.stage_index=c.stage_index
 WHERE marketing_runtime.paid_job_current(p_job,p_lease,p_plan) AND c.plan_id=p_plan AND c.stage_index=p_stage AND c.status='completed'
 AND c.usage->>'worker_broker_job'=p_job::text AND c.usage->>'worker_broker_lease_sha256'=encode(sha256(convert_to(p_lease::text,'UTF8')),'hex');
$$;
CREATE FUNCTION marketing_runtime.paid_turn_value(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer) RETURNS jsonb
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE response jsonb;v jsonb;t marketing_runtime.paid_turn_intents;actions jsonb;BEGIN
 response=marketing_runtime.paid_agent_response(p_job,p_lease,p_plan,p_stage);
 IF response IS NULL THEN RETURN NULL;END IF;
 BEGIN v=(response->>'text')::jsonb;EXCEPTION WHEN invalid_text_representation THEN RETURN NULL;END;
 IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(v))<>1 THEN RETURN NULL;END IF;
 IF v ? 'artifact' AND jsonb_typeof(v->'artifact')='object' THEN
  IF EXISTS(SELECT 1 FROM marketing_runtime.paid_tool_action_intents WHERE plan_id=p_plan AND stage_index=p_stage) THEN RETURN NULL;END IF;
  RETURN jsonb_build_object('artifact',v->'artifact','actions','[]'::jsonb,'completed_node',true);
 END IF;
 IF jsonb_typeof(v->'actions') IS DISTINCT FROM 'array' THEN RETURN NULL;END IF;
 IF jsonb_array_length(v->'actions') NOT BETWEEN 1 AND 8 OR jsonb_array_length(v->'actions')<>(SELECT count(*) FROM marketing_runtime.paid_tool_action_intents WHERE plan_id=p_plan AND stage_index=p_stage) THEN RETURN NULL;END IF;
 SELECT * INTO t FROM marketing_runtime.paid_turn_intents WHERE plan_id=p_plan AND stage_index=p_stage;
 IF EXISTS(SELECT 1 FROM marketing_runtime.paid_tool_action_intents i LEFT JOIN marketing_runtime.tool_receipts r ON r.id=i.request_id AND r.project_id=i.project_id
 LEFT JOIN campaign_private.tool_effect_states s ON s.request_id=r.id AND s.project_id=r.project_id
 WHERE i.plan_id=p_plan AND i.stage_index=p_stage AND (r.id IS NULL OR s.request_id IS NULL OR s.full_state_sha256<>r.state_sha256 OR r.role<>t.role OR r.operation<>i.operation OR r.arguments_sha256<>i.arguments_sha256)) THEN RETURN NULL;END IF;
 SELECT jsonb_agg(jsonb_build_object('operation',i.operation,'request_id',r.id,'receipt_sha256',r.result_sha256,'result',r.result) ORDER BY i.action_index) INTO actions
 FROM marketing_runtime.paid_tool_action_intents i JOIN marketing_runtime.tool_receipts r ON r.id=i.request_id AND r.project_id=i.project_id WHERE i.plan_id=p_plan AND i.stage_index=p_stage;
 RETURN jsonb_build_object('artifact',NULL,'actions',actions,'completed_node',false);
END $$;
CREATE FUNCTION marketing_runtime.record_paid_turn(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_call uuid,p_text text,p_response_hash text,p_observation jsonb,p_observation_hash text) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE b marketing_runtime.paid_agent_bindings;t marketing_runtime.paid_turn_intents;BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) OR p_response_hash IS DISTINCT FROM encode(sha256(convert_to(p_text,'UTF8')),'hex') OR p_observation_hash!~'^[a-f0-9]{64}$' OR octet_length(p_text)>65536 THEN RETURN false;END IF;
 SELECT * INTO b FROM marketing_runtime.paid_agent_bindings WHERE plan_id=p_plan;
 SELECT * INTO t FROM marketing_runtime.paid_turn_intents WHERE plan_id=p_plan AND stage_index=p_stage;
 IF t.plan_id IS NULL OR p_observation IS DISTINCT FROM marketing_runtime.paid_turn_value(p_job,p_lease,p_plan,p_stage) OR p_observation IS NULL
 OR NOT EXISTS(SELECT 1 FROM anvil.harbor_agent_calls c WHERE c.id=p_call AND c.project_id=b.project_id AND c.plan_id=p_plan AND c.stage_index=p_stage AND c.status='completed' AND c.output_json->>'text'=p_text)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_turn_observations WHERE plan_id=p_plan AND stage_index=p_stage)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_tool_action_intents i LEFT JOIN marketing_runtime.tool_receipts r ON r.id=i.request_id AND r.project_id=i.project_id
 WHERE i.plan_id=p_plan AND i.stage_index=p_stage AND (r.id IS NULL OR r.role<>t.role OR r.operation<>i.operation OR r.arguments_sha256<>i.arguments_sha256)) THEN RETURN false;END IF;
 INSERT INTO marketing_runtime.paid_turn_observations(project_id,plan_id,stage_index,call_id,response_sha256,observation,observation_sha256)
 VALUES(b.project_id,p_plan,p_stage,p_call,p_response_hash,p_observation,p_observation_hash);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_agent_job(),marketing_runtime.paid_job_current(uuid,uuid,uuid),marketing_runtime.bind_paid_agent_episode(uuid,uuid,uuid,uuid,integer,text),marketing_runtime.claim_paid_turn(uuid,uuid,uuid,integer,uuid,jsonb,text,text),marketing_runtime.claim_paid_tool_action(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text),marketing_runtime.record_paid_turn(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.claim_paid_agent_job(),marketing_runtime.paid_job_current(uuid,uuid,uuid),marketing_runtime.bind_paid_agent_episode(uuid,uuid,uuid,uuid,integer,text),marketing_runtime.claim_paid_turn(uuid,uuid,uuid,integer,uuid,jsonb,text,text),marketing_runtime.claim_paid_tool_action(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text),marketing_runtime.record_paid_turn(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) TO anvil_golden_scheduler;
GRANT EXECUTE ON FUNCTION marketing_runtime.paid_job_current(uuid,uuid,uuid) TO anvil_app;
-- API failure reconciliation receives status booleans, never raw role receipts,
-- episode contents or the private post-state projection.
CREATE FUNCTION marketing_runtime.paid_attempt_pending(p_job uuid,p_lease uuid,p_plan uuid) RETURNS jsonb
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object(
 'pending_tools',EXISTS(SELECT 1 FROM marketing_runtime.paid_tool_action_intents i
 LEFT JOIN marketing_runtime.tool_receipts r ON r.id=i.request_id AND r.project_id=i.project_id
 WHERE i.project_id=p.project_id AND i.plan_id=p.id AND r.id IS NULL),
 'pending_workflow',EXISTS(SELECT 1 FROM marketing_runtime.workflow_effects w
 JOIN marketing_runtime.paid_episode_links l ON l.episode_id=w.episode_id AND l.generation=w.generation AND l.project_id=w.project_id
 WHERE l.plan_id=p.id AND l.project_id=p.project_id AND w.state IN('claimed','execution_unknown')))
 FROM anvil.jobs j JOIN anvil.harbor_agent_plans p ON p.check_id=j.target_id AND p.project_id=j.project_id
 WHERE j.id=p_job AND j.lease_token=p_lease AND j.kind='benchmark_marketing_paid' AND p.id=p_plan
 AND j.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND p.created_by=nullif(current_setting('anvil.user',true),'')::uuid AND p.config->>'marketing_paid'='true';
$$;
REVOKE ALL ON FUNCTION marketing_runtime.paid_attempt_pending(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.paid_attempt_pending(uuid,uuid,uuid) TO anvil_app;
REVOKE ALL ON FUNCTION marketing_runtime.paid_agent_response(uuid,uuid,uuid,integer),marketing_runtime.paid_turn_value(uuid,uuid,uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.paid_agent_response(uuid,uuid,uuid,integer),marketing_runtime.paid_turn_value(uuid,uuid,uuid,integer) TO anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.claim_paid_call(p_group uuid,p_plan uuid,p_call uuid,p_bound bigint) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE g anvil.workspace_execution_groups;p anvil.harbor_agent_plans;c anvil.harbor_agent_calls;
 t marketing_runtime.paid_turn_intents;b marketing_runtime.paid_agent_bindings;
 r anvil.pilot_budget_reservations;j anvil.jobs;used bigint;cap bigint;budget_id uuid;
BEGIN
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE id=p_group FOR UPDATE;
 IF g.id IS NULL OR g.state<>'launched' OR g.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid
 OR g.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid OR NOT anvil.golden_engineer(g.project_id)
 OR NOT EXISTS(SELECT 1 FROM anvil.users u WHERE u.id=g.created_by AND u.active AND NOT u.is_synthetic) THEN RETURN false;END IF;
 SELECT * INTO p FROM anvil.harbor_agent_plans WHERE id=p_plan AND project_id=g.project_id;
 SELECT * INTO b FROM marketing_runtime.paid_agent_bindings WHERE plan_id=p_plan AND project_id=g.project_id;
 SELECT * INTO c FROM anvil.harbor_agent_calls WHERE id=p_call AND project_id=g.project_id AND plan_id=p_plan FOR UPDATE;
 IF p.id IS NULL OR b.plan_id IS NULL OR c.id IS NULL OR p.state<>'launched' OR p.config->>'marketing_paid' IS DISTINCT FROM 'true'
 OR p.config->>'workspace_execution_group' IS DISTINCT FROM g.id::text OR b.group_id IS DISTINCT FROM g.id
 OR c.status<>'dispatching' OR c.usage->>'pilot_broker_claimed'='true' OR p_bound IS DISTINCT FROM c.reserved_micro_usd
 OR p_bound IS NULL OR p_bound<=0 OR c.stage_index>=b.max_calls THEN RETURN false;END IF;
 SELECT * INTO t FROM marketing_runtime.paid_turn_intents WHERE plan_id=p_plan AND stage_index=c.stage_index;
 SELECT * INTO j FROM anvil.jobs WHERE id=t.job_id AND project_id=g.project_id;
 IF t.plan_id IS NULL OR j.id IS NULL OR j.kind<>'benchmark_marketing_paid' OR j.status<>'leased' OR j.lease_until<=clock_timestamp()
 OR j.target_id IS DISTINCT FROM p.check_id OR c.usage->>'worker_broker_job' IS DISTINCT FROM j.id::text
 OR c.usage->>'worker_broker_lease_sha256' IS DISTINCT FROM encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex')
 OR t.lease_sha256 IS DISTINCT FROM c.usage->>'worker_broker_lease_sha256'
 OR NOT EXISTS(SELECT 1 FROM marketing_runtime.workflow_effects e WHERE e.id=t.effect_id AND e.project_id=g.project_id AND e.state='claimed')
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_call_claims WHERE call_id=p_call OR(plan_id=p_plan AND stage_index=c.stage_index)) THEN RETURN false;END IF;
 cap=(g.snapshot->'preparation'->>'aggregate_cap_micro_usd')::bigint;
 budget_id=(g.snapshot->'preparation'->>'execution_budget_id')::uuid;
 SELECT * INTO r FROM anvil.pilot_budget_reservations WHERE group_id=g.id AND project_id=g.project_id;
 IF r.group_id IS NULL OR r.environment<>'qa' OR r.subject_hash IS DISTINCT FROM g.subject_hash OR r.amount_micro_usd IS DISTINCT FROM cap
 OR cap IS NULL OR cap<=0 OR cap>2000000 OR budget_id IS NULL OR NOT anvil.shared_execution_budget_active(budget_id)
 OR NOT EXISTS(SELECT 1 FROM anvil.shared_execution_group_allocations a WHERE a.group_id=g.id AND a.budget_id=budget_id AND a.amount_micro_usd=cap)
 OR NOT EXISTS(SELECT 1 FROM anvil.pilot_budget_policies q WHERE q.environment='qa' AND q.status='active' AND q.start_at<=clock_timestamp() AND q.end_at>clock_timestamp())
 OR NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_authorizations a JOIN anvil.users u ON u.id=a.admin_id AND u.active AND NOT u.is_synthetic
 JOIN anvil.memberships m ON m.project_id=a.project_id AND m.user_id=a.admin_id AND m.active AND m.role='admin'
 WHERE a.group_id=g.id AND a.project_id=g.project_id AND a.subject_hash=g.subject_hash AND a.cap_micro_usd=cap AND a.rights_confirmed AND a.expires_at>clock_timestamp()
 AND NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_revocations v WHERE v.authorization_id=a.id)) THEN RETURN false;END IF;
 SELECT coalesce(sum(bound_micro_usd),0) INTO used FROM marketing_runtime.paid_call_claims WHERE group_id=g.id;
 IF used+p_bound>cap THEN RETURN false;END IF;
 INSERT INTO marketing_runtime.paid_call_claims(project_id,group_id,plan_id,call_id,stage_index,bound_micro_usd,request_sha256)
 VALUES(g.project_id,g.id,p_plan,p_call,c.stage_index,p_bound,c.request_sha256);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_call(uuid,uuid,uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.claim_paid_call(uuid,uuid,uuid,bigint) TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(105);
