-- API fencing is not physical process/container shutdown or native admission.
CREATE TABLE campaign_private.world_fences(
 project_id uuid NOT NULL,plan_id uuid PRIMARY KEY,fence_id uuid NOT NULL UNIQUE,
 receipt jsonb NOT NULL CHECK(octet_length(receipt::text)<=65536),
 body_sha256 text NOT NULL CHECK(body_sha256~'^[a-f0-9]{64}$'),
 terminal jsonb NOT NULL CHECK(octet_length(terminal::text)<=8192),
 graph_ledger_sha256 text NOT NULL CHECK(graph_ledger_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES campaign_private.world_sessions(project_id,plan_id));
CREATE TABLE campaign_private.world_quiescence_receipts(
 project_id uuid NOT NULL,plan_id uuid PRIMARY KEY,
 receipt jsonb NOT NULL CHECK(octet_length(receipt::text)<=65536),
 body_sha256 text NOT NULL CHECK(body_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES campaign_private.world_sessions(project_id,plan_id));
DO $$DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['world_fences','world_quiescence_receipts'] LOOP
  EXECUTE format('ALTER TABLE campaign_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE campaign_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
-- No app/scheduler/worker/grader table grants. Only current leased API functions.

ALTER FUNCTION marketing_runtime.world_session_current(uuid) RENAME TO world_session_before_quiescence;
REVOKE ALL ON FUNCTION marketing_runtime.world_session_before_quiescence(uuid) FROM PUBLIC,anvil_app;
CREATE FUNCTION marketing_runtime.world_session_current(p_plan uuid) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN false;END IF;
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('marketing-world-stop:'||project::text||':'||p_plan::text,0));
 RETURN NOT EXISTS(SELECT 1 FROM campaign_private.world_fences WHERE project_id=project AND plan_id=p_plan)
 AND marketing_runtime.world_session_before_quiescence(p_plan);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.world_session_current(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.world_session_current(uuid) TO anvil_app;

ALTER FUNCTION marketing_runtime.paid_episode_current(uuid,uuid,uuid,uuid,integer,text) RENAME TO paid_episode_before_world_stop;
REVOKE ALL ON FUNCTION marketing_runtime.paid_episode_before_world_stop(uuid,uuid,uuid,uuid,integer,text) FROM PUBLIC,anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.paid_episode_current(p_job uuid,p_lease uuid,p_plan uuid,p_episode uuid,p_generation integer,p_execution text)
 RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT marketing_runtime.world_session_current(p_plan)
 AND marketing_runtime.paid_episode_before_world_stop(p_job,p_lease,p_plan,p_episode,p_generation,p_execution);
$$;
REVOKE ALL ON FUNCTION marketing_runtime.paid_episode_current(uuid,uuid,uuid,uuid,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.paid_episode_current(uuid,uuid,uuid,uuid,integer,text) TO anvil_golden_scheduler;

CREATE FUNCTION marketing_runtime.paid_episode_completion_current(p_job uuid,p_lease uuid,p_plan uuid,p_episode uuid,p_generation integer,p_execution text,p_effect uuid)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN false;END IF;
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('marketing-world-stop:'||nullif(current_setting('anvil.project',true),'')||':'||p_plan::text,0));
 RETURN marketing_runtime.world_session_before_quiescence(p_plan)
 AND marketing_runtime.paid_episode_before_world_stop(p_job,p_lease,p_plan,p_episode,p_generation,p_execution)
 AND EXISTS(SELECT 1 FROM marketing_runtime.workflow_effects e
 WHERE e.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND e.id=p_effect AND e.episode_id=p_episode AND e.generation=p_generation AND e.execution_sha256=p_execution AND e.state='claimed');
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.paid_episode_completion_current(uuid,uuid,uuid,uuid,integer,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.paid_episode_completion_current(uuid,uuid,uuid,uuid,integer,text,uuid) TO anvil_golden_scheduler;

-- Only an ALREADY admitted tool request can drain. This does not create an
-- intent, admit an SDK call, attach a new role or bypass current tool authority.
CREATE FUNCTION marketing_runtime.private_world_session_for_existing_tool(p_job uuid,p_lease uuid,p_plan uuid,p_request uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s campaign_private.world_sessions;BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('marketing-world-stop:'||nullif(current_setting('anvil.project',true),'')||':'||p_plan::text,0));
 IF NOT EXISTS(SELECT 1 FROM campaign_private.world_fences WHERE project_id=nullif(current_setting('anvil.project',true),'')::uuid AND plan_id=p_plan)
 THEN RETURN marketing_runtime.private_world_session(p_job,p_lease,p_plan);END IF;
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) OR NOT marketing_runtime.world_session_before_quiescence(p_plan)
 OR EXISTS(SELECT 1 FROM campaign_private.world_quiescence_receipts WHERE project_id=nullif(current_setting('anvil.project',true),'')::uuid AND plan_id=p_plan) THEN RETURN NULL;END IF;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=nullif(current_setting('anvil.project',true),'')::uuid AND plan_id=p_plan FOR UPDATE;
 IF NOT FOUND OR s.job_id<>p_job OR s.lease_sha256<>encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
 OR NOT EXISTS(SELECT 1 FROM marketing_runtime.paid_tool_action_intents i WHERE i.project_id=s.project_id AND i.plan_id=p_plan AND i.request_id=p_request)
 OR EXISTS(SELECT 1 FROM marketing_runtime.tool_receipts r WHERE r.project_id=s.project_id AND r.id=p_request) THEN RETURN NULL;END IF;
 RETURN to_jsonb(s);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_session_for_existing_tool(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_session_for_existing_tool(uuid,uuid,uuid,uuid) TO anvil_app;

CREATE OR REPLACE FUNCTION marketing_runtime.private_world_tool_context(p_job uuid,p_lease uuid,p_plan uuid,p_request uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s jsonb;answer jsonb;BEGIN
 s=marketing_runtime.private_world_session_for_existing_tool(p_job,p_lease,p_plan,p_request);
 IF s IS NULL THEN RETURN NULL;END IF;
 SELECT jsonb_build_object('session',s,'intent',jsonb_build_object(
  'request_id',i.request_id,'call_id',i.call_id,'stage_index',i.stage_index,'action_index',i.action_index,
  'operation',i.operation,'arguments',i.arguments,'arguments_sha256',i.arguments_sha256,
  'role',t.role,'node_id',t.node_id,'week',t.week,'visit',t.visit)) INTO answer
 FROM marketing_runtime.paid_tool_action_intents i
 JOIN marketing_runtime.paid_turn_intents t ON t.project_id=i.project_id AND t.plan_id=i.plan_id AND t.stage_index=i.stage_index
 JOIN marketing_runtime.paid_agent_bindings b ON b.project_id=i.project_id AND b.plan_id=i.plan_id
 JOIN marketing_runtime.workflow_effects e ON e.project_id=t.project_id AND e.id=t.effect_id
 JOIN anvil.harbor_agent_calls c ON c.project_id=i.project_id AND c.id=i.call_id AND c.plan_id=i.plan_id AND c.stage_index=i.stage_index
 WHERE i.project_id=(s->>'project_id')::uuid AND i.plan_id=p_plan AND i.request_id=p_request
 AND t.job_id=p_job AND t.lease_sha256=s->>'lease_sha256'
 AND e.episode_id=(s->>'episode_id')::uuid AND e.generation=(s->>'generation')::integer
 AND e.execution_sha256=b.execution_sha256 AND e.node_id=t.node_id AND e.week=t.week AND e.visit=t.visit AND e.state='claimed'
 AND c.status='completed' AND c.usage->>'worker_broker_job'=p_job::text
 AND c.usage->>'worker_broker_lease_sha256'=s->>'lease_sha256'
 AND c.usage->>'dispatch_origin' IN('provider','sdk_mock')
 AND NOT EXISTS(SELECT 1 FROM marketing_runtime.tool_receipts r WHERE r.project_id=i.project_id AND r.id=p_request)
 AND NOT EXISTS(SELECT 1 FROM campaign_private.response_protocol_findings f WHERE f.plan_id=i.plan_id AND f.stage_index=i.stage_index);
 RETURN answer;
END $$;

ALTER FUNCTION marketing_runtime.claim_paid_tool_action(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text) RENAME TO claim_paid_tool_before_world_stop;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_tool_before_world_stop(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text) FROM PUBLIC,anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.claim_paid_tool_action(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_action integer,p_call uuid,p_request uuid,p_operation text,p_arguments jsonb,p_hash text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF NOT marketing_runtime.world_session_current(p_plan) THEN RETURN false;END IF;
 RETURN marketing_runtime.claim_paid_tool_before_world_stop(p_job,p_lease,p_plan,p_stage,p_action,p_call,p_request,p_operation,p_arguments,p_hash);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_tool_action(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.claim_paid_tool_action(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text) TO anvil_golden_scheduler;

-- Existing in-flight response metadata may still be retained after a fence;
-- serialize it against the snapshot without authorizing another SDK/tool call.
ALTER FUNCTION marketing_runtime.record_paid_turn(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) RENAME TO record_paid_turn_before_world_stop;
REVOKE ALL ON FUNCTION marketing_runtime.record_paid_turn_before_world_stop(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) FROM PUBLIC,anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.record_paid_turn(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_call uuid,p_text text,p_response_hash text,p_observation jsonb,p_observation_hash text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('marketing-world-stop:'||nullif(current_setting('anvil.project',true),'')||':'||p_plan::text,0));
 RETURN marketing_runtime.record_paid_turn_before_world_stop(p_job,p_lease,p_plan,p_stage,p_call,p_text,p_response_hash,p_observation,p_observation_hash);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.record_paid_turn(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.record_paid_turn(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) TO anvil_golden_scheduler;
ALTER FUNCTION marketing_runtime.record_response_protocol_failure(uuid,uuid,uuid,integer,uuid,jsonb) RENAME TO record_protocol_before_world_stop;
REVOKE ALL ON FUNCTION marketing_runtime.record_protocol_before_world_stop(uuid,uuid,uuid,integer,uuid,jsonb) FROM PUBLIC,anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.record_response_protocol_failure(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_call uuid,p_finding jsonb)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('marketing-world-stop:'||nullif(current_setting('anvil.project',true),'')||':'||p_plan::text,0));
 RETURN marketing_runtime.record_protocol_before_world_stop(p_job,p_lease,p_plan,p_stage,p_call,p_finding);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.record_response_protocol_failure(uuid,uuid,uuid,integer,uuid,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.record_response_protocol_failure(uuid,uuid,uuid,integer,uuid,jsonb) TO anvil_golden_scheduler;

-- Fence direct scheduler effect writes as well as the normal Python journal.
CREATE FUNCTION marketing_runtime.world_effect_stop_guard() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE plan uuid;BEGIN
 SELECT s.plan_id INTO plan FROM campaign_private.world_sessions s
 WHERE s.project_id=NEW.project_id AND s.episode_id=NEW.episode_id AND s.generation=NEW.generation;
 IF FOUND THEN
  IF current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'read committed world custody required';END IF;
  PERFORM pg_advisory_xact_lock_shared(hashtextextended('marketing-world-stop:'||NEW.project_id::text||':'||plan::text,0));
  IF EXISTS(SELECT 1 FROM campaign_private.world_fences WHERE project_id=NEW.project_id AND plan_id=plan) THEN
   IF TG_OP<>'UPDATE' THEN RAISE EXCEPTION 'fenced world cannot admit new effects';END IF;
   IF OLD.state<>'claimed' OR NEW.state NOT IN('completed','execution_unknown')
   OR EXISTS(SELECT 1 FROM campaign_private.world_quiescence_receipts WHERE project_id=NEW.project_id AND plan_id=plan)
   THEN RAISE EXCEPTION 'fenced world permits only already claimed effect completion';END IF;
  ELSIF NOT marketing_runtime.world_session_current(plan) THEN
   RAISE EXCEPTION 'private world cannot admit workflow effect writes';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER world_stop BEFORE INSERT OR UPDATE ON marketing_runtime.workflow_effects
 FOR EACH ROW EXECUTE FUNCTION marketing_runtime.world_effect_stop_guard();

CREATE FUNCTION marketing_runtime.world_stop_context(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 s campaign_private.world_sessions;records jsonb;releases jsonb;effects jsonb;turns jsonb;pending jsonb;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN NULL;END IF;
 -- Match candidate SDK group-before-world/source order, then serialize EVERY
 -- guarded SDK/tool/effect admission through the conflicting exclusive fence.
 PERFORM 1 FROM anvil.workspace_execution_groups g JOIN anvil.harbor_agent_plans p
 ON p.project_id=g.project_id AND (p.config->>'workspace_execution_group')::uuid=g.id
 WHERE p.project_id=project AND p.id=p_plan FOR UPDATE OF g;
 IF NOT FOUND THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('marketing-world-stop:'||project::text||':'||p_plan::text,0));
 -- Denial-only cleanup must survive paid/budget/membership/source expiry. It
 -- never admits work or an award. Bind the original private capability and
 -- immutable job/plan/actor snapshot; a replacement lease cannot stop it.
 IF NOT EXISTS(SELECT 1 FROM campaign_private.world_sessions w
 JOIN marketing_runtime.paid_agent_bindings b ON b.project_id=w.project_id AND b.plan_id=w.plan_id
 JOIN anvil.harbor_agent_plans p ON p.project_id=b.project_id AND p.id=b.plan_id
 JOIN anvil.jobs j ON j.project_id=w.project_id AND j.id=w.job_id AND j.target_id=p.check_id
 WHERE w.project_id=project AND w.plan_id=p_plan AND w.job_id=p_job
 AND w.lease_sha256=encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
 AND(j.lease_token IS NULL OR j.lease_token=p_lease)
 AND j.kind='benchmark_marketing_paid' AND b.created_by=nullif(current_setting('anvil.user',true),'')::uuid
 AND p.created_by=b.created_by AND p.config->>'marketing_paid'='true'
 AND coalesce(p.config->>'golden_kyc_paid','false')<>'true'
 AND b.execution_sha256=w.attachment->>'execution_sha256') THEN RETURN NULL;END IF;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=project AND plan_id=p_plan FOR UPDATE;
 IF NOT FOUND OR s.job_id<>p_job OR s.lease_sha256<>encode(sha256(convert_to(p_lease::text,'UTF8')),'hex') THEN RETURN NULL;END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.week),'[]'::jsonb) INTO releases
 FROM campaign_private.world_releases r WHERE r.project_id=project AND r.plan_id=p_plan;
 SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY e.week,e.node_id,e.visit),'[]'::jsonb) INTO effects
 FROM marketing_runtime.workflow_effects e WHERE e.project_id=project AND e.episode_id=s.episode_id AND e.generation=s.generation;
 SELECT coalesce(jsonb_agg(value),'[]'::jsonb) INTO turns FROM marketing_runtime.reconstruction_turns(project,p_plan) value;
 records=jsonb_build_object('attachment',s.attachment,'releases',releases,'effects',effects,'turns',turns);
 SELECT jsonb_build_object(
  'sdk_dispatching',(SELECT count(*) FROM anvil.harbor_agent_calls c WHERE c.project_id=project AND c.plan_id=p_plan AND c.status='dispatching'),
  'sdk_unknown',(SELECT count(*) FROM anvil.harbor_agent_calls c LEFT JOIN marketing_runtime.paid_turn_intents t ON t.project_id=c.project_id AND t.plan_id=c.plan_id AND t.stage_index=c.stage_index
   WHERE c.project_id=project AND c.plan_id=p_plan AND(c.status='execution_unknown' OR t.stage_index IS NULL))
   +(SELECT count(*) FROM marketing_runtime.paid_turn_intents t LEFT JOIN anvil.harbor_agent_calls c ON c.project_id=t.project_id AND c.plan_id=t.plan_id AND c.stage_index=t.stage_index WHERE t.project_id=project AND t.plan_id=p_plan AND c.id IS NULL),
  'tool_pending',(SELECT count(*) FROM marketing_runtime.paid_tool_action_intents i LEFT JOIN marketing_runtime.tool_receipts r ON r.project_id=i.project_id AND r.id=i.request_id WHERE i.project_id=project AND i.plan_id=p_plan AND r.id IS NULL),
  'workflow_pending',(SELECT count(*) FROM marketing_runtime.workflow_effects e WHERE e.project_id=project AND e.episode_id=s.episode_id AND e.generation=s.generation AND e.state<>'completed'),
  'workflow_unknown',(SELECT count(*) FROM marketing_runtime.workflow_effects e WHERE e.project_id=project AND e.episode_id=s.episode_id AND e.generation=s.generation AND e.state='execution_unknown')
 ) INTO pending;
 RETURN jsonb_build_object('session',to_jsonb(s),'graph_records',records,
 'graph_ledger_sha256',encode(sha256(convert_to(records::text,'UTF8')),'hex'),'pending',pending,
 'source_qualification_sha256',(SELECT receipt_sha256 FROM campaign_private.world_qualifications WHERE project_id=project AND id=s.qualification_id),
 'observed_at',clock_timestamp(),
 'execution',(SELECT execution FROM marketing_runtime.paid_agent_bindings WHERE project_id=project AND plan_id=p_plan),
 'fence',(SELECT to_jsonb(f) FROM campaign_private.world_fences f WHERE f.project_id=project AND f.plan_id=p_plan),
 'quiescence',(SELECT to_jsonb(q) FROM campaign_private.world_quiescence_receipts q WHERE q.project_id=project AND q.plan_id=p_plan));
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.world_stop_context(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.world_stop_context(uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.record_world_fence(p_job uuid,p_lease uuid,p_plan uuid,p_ledger text,p_terminal text,p_receipt text,p_body_hash text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE c jsonb;s jsonb;r jsonb;t jsonb;BEGIN
 IF octet_length(p_receipt)>65536 OR octet_length(p_terminal)>8192
 OR p_body_hash IS NULL OR p_body_hash<>encode(sha256(convert_to(p_receipt,'UTF8')),'hex') THEN RETURN false;END IF;
 c=marketing_runtime.world_stop_context(p_job,p_lease,p_plan);
 IF c IS NULL OR c->'fence'<>'null'::jsonb OR c->>'graph_ledger_sha256'<>p_ledger THEN RETURN false;END IF;
 s=c->'session';r=p_receipt::jsonb;t=p_terminal::jsonb;
 IF r->>'schema_version' IS DISTINCT FROM 'anvil.marketing-world-fence.v1'
 OR r->>'project_id' IS DISTINCT FROM s->>'project_id' OR r->>'plan_id' IS DISTINCT FROM p_plan::text
 OR r->>'job_id' IS DISTINCT FROM p_job::text OR r->>'lease_sha256' IS DISTINCT FROM s->>'lease_sha256'
 OR r->>'world_binding_id' IS DISTINCT FROM s->>'world_binding_id' OR r->>'world_binding_sha256' IS DISTINCT FROM s->>'world_binding_sha256'
 OR r->>'episode_id' IS DISTINCT FROM s->>'episode_id' OR r->'generation' IS DISTINCT FROM s->'generation'
 OR r->>'source_qualification_sha256' IS DISTINCT FROM c->>'source_qualification_sha256'
 OR r->>'execution_sha256' IS DISTINCT FROM s->'attachment'->>'execution_sha256'
 OR r->'fence_epoch' IS DISTINCT FROM '1'::jsonb OR r->'new_work_permitted' IS DISTINCT FROM 'false'::jsonb
 OR r->>'graph_ledger_sha256' IS DISTINCT FROM p_ledger
 OR r->>'reconstruction_sha256' IS DISTINCT FROM t->>'reconstruction_sha256'
 THEN RETURN false;END IF;
 INSERT INTO campaign_private.world_fences(project_id,plan_id,fence_id,receipt,body_sha256,terminal,graph_ledger_sha256)
 VALUES((s->>'project_id')::uuid,p_plan,(r->>'fence_id')::uuid,r,p_body_hash,t,p_ledger);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.record_world_fence(uuid,uuid,uuid,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.record_world_fence(uuid,uuid,uuid,text,text,text,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.record_world_quiescence(p_job uuid,p_lease uuid,p_plan uuid,p_ledger text,p_terminal text,p_receipt text,p_body_hash text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE c jsonb;r jsonb;f jsonb;t jsonb;BEGIN
 IF octet_length(p_receipt)>65536 OR octet_length(p_terminal)>8192 OR p_body_hash IS NULL OR p_body_hash<>encode(sha256(convert_to(p_receipt,'UTF8')),'hex') THEN RETURN false;END IF;
 c=marketing_runtime.world_stop_context(p_job,p_lease,p_plan);
 IF c IS NULL OR c->'fence'='null'::jsonb OR c->'quiescence'<>'null'::jsonb
 OR c->'pending'<>'{"sdk_dispatching":0,"sdk_unknown":0,"tool_pending":0,"workflow_pending":0,"workflow_unknown":0}'::jsonb THEN RETURN false;END IF;
 f=c->'fence'->'receipt';t=p_terminal::jsonb;r=p_receipt::jsonb;
 IF t->>'reconstruction_sha256' IS NULL OR t->>'reconstruction_sha256'!~'^[a-f0-9]{64}$'
 OR t->>'terminal_status' NOT IN('recorded_done','recorded_hold_requires_qualification')
 OR t->>'terminal_status' IS NULL OR c->>'graph_ledger_sha256' IS DISTINCT FROM p_ledger
 OR r->>'schema_version' IS DISTINCT FROM 'anvil.marketing-world-quiescence.v2'
 OR (r-ARRAY['schema_version','quiescence_id','observed_at','fence_receipt_sha256','terminal_status','pending','api_quiescent','physical_stop_verified','native_qualified','receipt_sha256','graph_ledger_sha256','reconstruction_sha256','fenced_graph_ledger_sha256','fenced_reconstruction_sha256'])
 IS DISTINCT FROM (f-ARRAY['schema_version','fenced_at','receipt_sha256','graph_ledger_sha256','reconstruction_sha256'])
 OR r->>'graph_ledger_sha256' IS DISTINCT FROM p_ledger
 OR r->>'reconstruction_sha256' IS DISTINCT FROM t->>'reconstruction_sha256'
 OR r->>'fenced_graph_ledger_sha256' IS DISTINCT FROM f->>'graph_ledger_sha256'
 OR r->>'fenced_reconstruction_sha256' IS DISTINCT FROM f->>'reconstruction_sha256'
 OR r->>'fence_receipt_sha256' IS DISTINCT FROM f->>'receipt_sha256'
 OR r->>'terminal_status' IS DISTINCT FROM t->>'terminal_status' OR r->'pending' IS DISTINCT FROM c->'pending'
 OR r->'api_quiescent' IS DISTINCT FROM 'true'::jsonb
 OR r->'physical_stop_verified' IS DISTINCT FROM 'false'::jsonb OR r->'native_qualified' IS DISTINCT FROM 'false'::jsonb
 THEN RETURN false;END IF;
 INSERT INTO campaign_private.world_quiescence_receipts(project_id,plan_id,receipt,body_sha256)
 VALUES((f->>'project_id')::uuid,p_plan,r,p_body_hash);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.record_world_quiescence(uuid,uuid,uuid,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.record_world_quiescence(uuid,uuid,uuid,text,text,text,text) TO anvil_app;

CREATE FUNCTION campaign_private.world_stop_quota() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE used bigint;BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_stop_quota:'||NEW.project_id::text,0));
 SELECT coalesce(sum(bytes),0) INTO used FROM(
  SELECT octet_length(receipt::text)+octet_length(terminal::text) AS bytes FROM campaign_private.world_fences WHERE project_id=NEW.project_id
  UNION ALL SELECT octet_length(receipt::text) FROM campaign_private.world_quiescence_receipts WHERE project_id=NEW.project_id
 ) stop_bytes;
 IF used+octet_length(to_jsonb(NEW)::text)>536870912 THEN RAISE EXCEPTION 'private world stop receipt quota exhausted';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER quota BEFORE INSERT ON campaign_private.world_fences FOR EACH ROW EXECUTE FUNCTION campaign_private.world_stop_quota();
CREATE TRIGGER quota BEFORE INSERT ON campaign_private.world_quiescence_receipts FOR EACH ROW EXECUTE FUNCTION campaign_private.world_stop_quota();
INSERT INTO anvil.schema_versions(version) VALUES(110);
