-- A completed candidate protocol rejection is distinct from ambiguous dispatch
-- and valid-turn tool failure. Findings are private observations, never awards.
CREATE TABLE campaign_private.response_protocol_findings(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,stage_index integer NOT NULL,
 call_id uuid NOT NULL,job_id uuid NOT NULL,effect_id uuid NOT NULL,
 episode_id uuid NOT NULL,generation integer NOT NULL,
 role text NOT NULL,node_id text NOT NULL,week integer NOT NULL,visit integer NOT NULL,
 lease_sha256 text NOT NULL CHECK(lease_sha256~'^[a-f0-9]{64}$'),
 execution_sha256 text NOT NULL CHECK(execution_sha256~'^[a-f0-9]{64}$'),
 bound_source_sha256 text NOT NULL CHECK(bound_source_sha256~'^[a-f0-9]{64}$'),
 response_sha256 text NOT NULL CHECK(response_sha256~'^[a-f0-9]{64}$'),
 finding jsonb NOT NULL CHECK(octet_length(finding::text)<=8192),
 no_claimed_tool_actions boolean NOT NULL CHECK(no_claimed_tool_actions),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(plan_id,stage_index),
 FOREIGN KEY(project_id,plan_id,stage_index) REFERENCES marketing_runtime.paid_turn_intents(project_id,plan_id,stage_index),
 FOREIGN KEY(project_id,call_id) REFERENCES anvil.harbor_agent_calls(project_id,id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.jobs(project_id,id),
 FOREIGN KEY(project_id,episode_id) REFERENCES marketing_runtime.episodes(project_id,id),
 FOREIGN KEY(effect_id) REFERENCES marketing_runtime.workflow_effects(id));
ALTER TABLE campaign_private.response_protocol_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.response_protocol_findings FORCE ROW LEVEL SECURITY;
CREATE POLICY private_read ON campaign_private.response_protocol_findings
 FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT ON campaign_private.response_protocol_findings TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.response_protocol_findings
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE FUNCTION marketing_runtime.record_response_protocol_failure(
 p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_call uuid,p_finding jsonb
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE t marketing_runtime.paid_turn_intents;b marketing_runtime.paid_agent_bindings;
 e marketing_runtime.workflow_effects;l marketing_runtime.paid_episode_links;r jsonb;
BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) THEN RETURN false;END IF;
 SELECT * INTO t FROM marketing_runtime.paid_turn_intents WHERE plan_id=p_plan AND stage_index=p_stage FOR UPDATE;
 SELECT * INTO b FROM marketing_runtime.paid_agent_bindings WHERE plan_id=p_plan;
 SELECT * INTO l FROM marketing_runtime.paid_episode_links WHERE plan_id=p_plan;
 SELECT * INTO e FROM marketing_runtime.workflow_effects WHERE id=t.effect_id;
 r=marketing_runtime.paid_agent_response(p_job,p_lease,p_plan,p_stage);
 IF t.plan_id IS NULL OR b.plan_id IS NULL OR l.plan_id IS NULL OR e.id IS NULL OR r IS NULL
 OR t.project_id<>b.project_id OR l.project_id<>b.project_id OR e.project_id<>b.project_id
 OR t.job_id<>p_job OR l.job_id<>p_job OR e.episode_id<>l.episode_id OR e.generation<>l.generation
 OR t.lease_sha256<>encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
 OR e.execution_sha256<>b.execution_sha256 OR e.state<>'claimed'
 OR e.node_id<>t.node_id OR e.week<>t.week OR e.visit<>t.visit
 OR r->>'id' IS DISTINCT FROM p_call::text OR (r->>'origin' IS DISTINCT FROM 'provider' AND r->>'origin' IS DISTINCT FROM 'sdk_mock')
 OR jsonb_typeof(p_finding) IS DISTINCT FROM 'object' OR octet_length(p_finding::text)>8192
 OR (SELECT count(*) FROM jsonb_object_keys(p_finding))<>14
 OR NOT p_finding ?& ARRAY['schema_version','classifier_source_sha256','execution_sha256','role','response_text_sha256','protocol_status','observed_failure','known_requested_tool_ids','tool_request_list_complete','effects_assessed','model_performance_validated','internal_reasoning_assessed','provenance_limitation','scope']
 OR p_finding->>'schema_version' IS DISTINCT FROM 'anvil.marketing-response-protocol-finding.v1'
 OR p_finding->>'protocol_status' IS DISTINCT FROM 'invalid'
 OR p_finding->>'role' IS DISTINCT FROM t.role
 OR p_finding->>'execution_sha256' IS DISTINCT FROM b.execution_sha256
 OR p_finding->>'response_text_sha256' IS DISTINCT FROM encode(sha256(convert_to(r->>'text','UTF8')),'hex')
 OR (p_finding->>'classifier_source_sha256' ~ '^[a-f0-9]{64}$') IS DISTINCT FROM true
 OR (p_finding->>'observed_failure' IN('invalid_json','invalid_control_envelope','invalid_node_artifact','invalid_action_population','invalid_tool_arguments','invalid_action_envelope','unoffered_tool_requested','tool_requested_outside_assigned_role')) IS DISTINCT FROM true
 OR p_finding->'effects_assessed' IS DISTINCT FROM 'false'::jsonb
 OR p_finding->'model_performance_validated' IS DISTINCT FROM 'false'::jsonb
 OR p_finding->'internal_reasoning_assessed' IS DISTINCT FROM 'false'::jsonb
 OR p_finding->'tool_request_list_complete' IS DISTINCT FROM 'false'::jsonb
 OR jsonb_typeof(p_finding->'known_requested_tool_ids') IS DISTINCT FROM 'array'
 OR jsonb_array_length(p_finding->'known_requested_tool_ids')>8
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(p_finding->'known_requested_tool_ids') v WHERE jsonb_typeof(v)<>'string' OR octet_length(v::text)>256)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_tool_action_intents WHERE plan_id=p_plan AND stage_index=p_stage)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_turn_observations WHERE plan_id=p_plan AND stage_index=p_stage)
 OR EXISTS(SELECT 1 FROM campaign_private.response_protocol_findings WHERE plan_id=p_plan AND stage_index=p_stage)
 THEN RETURN false;END IF;
 INSERT INTO campaign_private.response_protocol_findings(project_id,plan_id,stage_index,call_id,job_id,effect_id,episode_id,generation,role,node_id,week,visit,lease_sha256,execution_sha256,bound_source_sha256,response_sha256,finding,no_claimed_tool_actions)
 VALUES(b.project_id,p_plan,p_stage,p_call,p_job,e.id,l.episode_id,l.generation,t.role,t.node_id,t.week,t.visit,t.lease_sha256,b.execution_sha256,b.native_binding->>'runtime_sha256',p_finding->>'response_text_sha256',p_finding,true);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.record_response_protocol_failure(uuid,uuid,uuid,integer,uuid,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.record_response_protocol_failure(uuid,uuid,uuid,integer,uuid,jsonb) TO anvil_golden_scheduler;

-- Serialize failure capture against tool admission and normal turn completion.
-- No new direct table write grant; callers cannot execute the old entry points.
ALTER FUNCTION marketing_runtime.claim_paid_tool_action(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text) RENAME TO claim_paid_tool_action_before_protocol_failure;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_tool_action_before_protocol_failure(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text) FROM PUBLIC,anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.claim_paid_tool_action(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_action integer,p_call uuid,p_request uuid,p_operation text,p_arguments jsonb,p_hash text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) THEN RETURN false;END IF;
 PERFORM 1 FROM marketing_runtime.paid_turn_intents WHERE plan_id=p_plan AND stage_index=p_stage FOR UPDATE;
 IF EXISTS(SELECT 1 FROM campaign_private.response_protocol_findings WHERE plan_id=p_plan AND stage_index=p_stage) THEN RETURN false;END IF;
 RETURN marketing_runtime.claim_paid_tool_action_before_protocol_failure(p_job,p_lease,p_plan,p_stage,p_action,p_call,p_request,p_operation,p_arguments,p_hash);
END $$;
ALTER FUNCTION marketing_runtime.record_paid_turn(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) RENAME TO record_paid_turn_before_protocol_failure;
REVOKE ALL ON FUNCTION marketing_runtime.record_paid_turn_before_protocol_failure(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) FROM PUBLIC,anvil_golden_scheduler;
CREATE FUNCTION marketing_runtime.record_paid_turn(p_job uuid,p_lease uuid,p_plan uuid,p_stage integer,p_call uuid,p_text text,p_response_hash text,p_observation jsonb,p_observation_hash text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) THEN RETURN false;END IF;
 PERFORM 1 FROM marketing_runtime.paid_turn_intents WHERE plan_id=p_plan AND stage_index=p_stage FOR UPDATE;
 IF EXISTS(SELECT 1 FROM campaign_private.response_protocol_findings WHERE plan_id=p_plan AND stage_index=p_stage) THEN RETURN false;END IF;
 RETURN marketing_runtime.record_paid_turn_before_protocol_failure(p_job,p_lease,p_plan,p_stage,p_call,p_text,p_response_hash,p_observation,p_observation_hash);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_tool_action(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text),marketing_runtime.record_paid_turn(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.claim_paid_tool_action(uuid,uuid,uuid,integer,integer,uuid,uuid,text,jsonb,text),marketing_runtime.record_paid_turn(uuid,uuid,uuid,integer,uuid,text,text,jsonb,text) TO anvil_golden_scheduler;

-- Read-only grader projection. One item per stored observation; a broken link
-- yields NULL so the consumer must fail, never silently shrink the population.
-- No raw response, credentials, private fixture or provider metadata is exposed.
CREATE FUNCTION marketing_runtime.reconstruction_turns(p_project uuid,p_plan uuid)
 RETURNS SETOF jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT CASE WHEN c.status='completed' AND c.project_id=o.project_id AND c.plan_id=o.plan_id
 AND c.stage_index=o.stage_index AND c.usage->>'dispatch_origin' IN('provider','sdk_mock')
 AND c.usage->>'worker_broker_job'=t.job_id::text
 AND c.usage->>'worker_broker_lease_sha256'=t.lease_sha256 AND t.lease_sha256=l.lease_sha256
 AND t.job_id=l.job_id AND e.episode_id=l.episode_id AND e.generation=l.generation
 AND e.execution_sha256=b.execution_sha256 AND e.node_id=t.node_id AND e.week=t.week AND e.visit=t.visit
 AND o.response_sha256=encode(sha256(convert_to(c.output_json->>'text','UTF8')),'hex')
 AND NOT EXISTS(SELECT 1 FROM campaign_private.response_protocol_findings f WHERE f.plan_id=o.plan_id AND f.stage_index=o.stage_index)
 AND NOT EXISTS(SELECT 1 FROM marketing_runtime.paid_tool_action_intents i
  LEFT JOIN marketing_runtime.tool_receipts r ON r.project_id=i.project_id AND r.id=i.request_id
  LEFT JOIN campaign_private.tool_effect_states s ON s.project_id=r.project_id AND s.request_id=r.id
  WHERE i.plan_id=o.plan_id AND i.stage_index=o.stage_index
   AND (r.id IS NULL OR s.request_id IS NULL OR r.role<>t.role OR r.operation<>i.operation
    OR r.arguments_sha256<>i.arguments_sha256 OR s.full_state_sha256<>r.state_sha256))
 THEN jsonb_build_object(
  'project_id',o.project_id,'plan_id',o.plan_id,'job_id',t.job_id,'episode_id',l.episode_id,
  'generation',l.generation,'stage_index',o.stage_index,'effect_id',t.effect_id,'call_id',o.call_id,
  'role',t.role,'origin',c.usage->>'dispatch_origin','response_sha256',o.response_sha256,
  'observation',o.observation,'observation_sha256',o.observation_sha256)
 ELSE NULL END
 FROM marketing_runtime.paid_turn_observations o
 LEFT JOIN marketing_runtime.paid_turn_intents t ON t.project_id=o.project_id AND t.plan_id=o.plan_id AND t.stage_index=o.stage_index
 LEFT JOIN marketing_runtime.paid_agent_bindings b ON b.project_id=o.project_id AND b.plan_id=o.plan_id
 LEFT JOIN marketing_runtime.paid_episode_links l ON l.project_id=o.project_id AND l.plan_id=o.plan_id
 LEFT JOIN marketing_runtime.workflow_effects e ON e.project_id=o.project_id AND e.id=t.effect_id
 LEFT JOIN anvil.harbor_agent_calls c ON c.project_id=o.project_id AND c.id=o.call_id
 WHERE o.project_id=p_project AND o.plan_id=p_plan AND banking.runtime_scope(o.project_id)
 ORDER BY o.stage_index;
$$;
REVOKE ALL ON FUNCTION marketing_runtime.reconstruction_turns(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.reconstruction_turns(uuid,uuid) TO anvil_golden_grader;
