-- SOURCE PROPOSAL ONLY. No runtime/provisioning/qualification authority.
-- Descriptor returns are simulated source effects, never media or spending.
CREATE TABLE campaign_private.world_service_effects(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,effect_id uuid PRIMARY KEY,
 receipt_id uuid NOT NULL UNIQUE,reply jsonb NOT NULL,
 reply_sha256 text NOT NULL CHECK(reply_sha256~'^[a-f0-9]{64}$'),
 source_contract_sha256 text NOT NULL CHECK(source_contract_sha256~'^[a-f0-9]{64}$'),
 post_state_sha256 text NOT NULL CHECK(post_state_sha256~'^[a-f0-9]{64}$'),
 request_canonical text NOT NULL CHECK(octet_length(request_canonical)<=49152),
 request_sha256 text NOT NULL CHECK(request_sha256=encode(sha256(convert_to(request_canonical,'UTF8')),'hex')),
 input_canonical text NOT NULL CHECK(octet_length(input_canonical)<=32768),
 input_sha256 text NOT NULL CHECK(input_sha256=encode(sha256(convert_to(input_canonical,'UTF8')),'hex')),
 node_sha256 text NOT NULL CHECK(node_sha256~'^[a-f0-9]{64}$'),
 byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 196608),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES campaign_private.world_sessions(project_id,plan_id),
 FOREIGN KEY(effect_id) REFERENCES marketing_runtime.workflow_effects(id),
 CHECK(octet_length(reply::text)<=65536));
ALTER TABLE campaign_private.world_service_effects ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.world_service_effects FORCE ROW LEVEL SECURITY;
REVOKE ALL ON campaign_private.world_service_effects FROM PUBLIC,anvil_app,anvil_golden_scheduler,anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.world_service_effects
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE FUNCTION marketing_runtime.private_world_service_context(
 p_job uuid,p_lease uuid,p_plan uuid,p_node text,p_week integer,p_visit integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 s campaign_private.world_sessions;e marketing_runtime.workflow_effects;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' OR p_node<>'task3'
 OR p_week NOT BETWEEN 1 AND 12 OR p_visit NOT BETWEEN 1 AND 400 THEN RETURN NULL;END IF;
 PERFORM 1 FROM anvil.workspace_execution_groups g JOIN anvil.harbor_agent_plans p
 ON p.project_id=g.project_id AND (p.config->>'workspace_execution_group')::uuid=g.id
 WHERE p.project_id=project AND p.id=p_plan FOR UPDATE OF g;
 IF NOT FOUND THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('marketing-world-stop:'||project::text||':'||p_plan::text,0));
 IF NOT marketing_runtime.world_session_before_quiescence(p_plan)
 OR NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan)
 OR EXISTS(SELECT 1 FROM campaign_private.world_quiescence_receipts WHERE project_id=project AND plan_id=p_plan) THEN RETURN NULL;END IF;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=project AND plan_id=p_plan FOR UPDATE;
 IF NOT FOUND OR s.job_id<>p_job OR s.lease_sha256<>encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
 OR s.last_week<>p_week THEN RETURN NULL;END IF;
 -- Only an actual already-committed workflow intent may complete after fencing.
 -- No new role, model, workflow intent or source authority is admitted here.
 SELECT * INTO e FROM marketing_runtime.workflow_effects
 WHERE project_id=project AND episode_id=s.episode_id AND generation=s.generation
 AND execution_sha256=s.attachment->>'execution_sha256' AND node_id=p_node AND week=p_week AND visit=p_visit FOR UPDATE;
 IF NOT FOUND OR e.state<>'claimed'
 OR EXISTS(SELECT 1 FROM campaign_private.world_service_effects WHERE effect_id=e.id) THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('session',to_jsonb(s),'effect',to_jsonb(e));
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_service_context(uuid,uuid,uuid,text,integer,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_service_context(uuid,uuid,uuid,text,integer,integer) TO anvil_app;

CREATE FUNCTION marketing_runtime.commit_private_world_service(
 p_job uuid,p_lease uuid,p_plan uuid,p_node text,p_week integer,p_visit integer,
 p_effect uuid,p_before text,p_reply text,p_hash text,p_contract text,
 p_request text,p_request_hash text,p_inputs text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE ctx jsonb;s jsonb;e jsonb;r jsonb;q jsonb;request_value jsonb;input_value jsonb;used bigint;size integer;
BEGIN
 IF octet_length(p_reply)>60000 OR p_hash IS DISTINCT FROM encode(sha256(convert_to(p_reply,'UTF8')),'hex')
 OR p_contract!~'^[a-f0-9]{64}$' OR octet_length(p_request)>49152 OR octet_length(p_inputs)>32768
 OR p_request_hash IS DISTINCT FROM encode(sha256(convert_to(p_request,'UTF8')),'hex') THEN RETURN false;END IF;
 ctx=marketing_runtime.private_world_service_context(p_job,p_lease,p_plan,p_node,p_week,p_visit);
 IF ctx IS NULL THEN RETURN false;END IF;
 s=ctx->'session';e=ctx->'effect';r=p_reply::jsonb;q=r->'receipt';
 request_value=p_request::jsonb;input_value=p_inputs::jsonb;
 IF (e->>'id')::uuid<>p_effect OR s->>'controller_state_sha256' IS DISTINCT FROM p_before
 OR jsonb_typeof(r->'artifact') IS DISTINCT FROM 'object'
 OR r->'artifact'->>'source_contract_sha256' IS DISTINCT FROM p_contract
 OR q->>'input_sha256' IS DISTINCT FROM e->>'input_sha256'
 OR q->>'post_state_sha256' IS DISTINCT FROM p_before
 OR q->>'world_binding_sha256' IS DISTINCT FROM s->>'world_binding_sha256'
 OR q->>'episode_id' IS DISTINCT FROM s->>'episode_id'
 OR q->>'generation' IS DISTINCT FROM s->>'generation'
 OR q->>'node_id' IS DISTINCT FROM p_node OR q->>'week' IS DISTINCT FROM p_week::text
 OR q->>'visit' IS DISTINCT FROM p_visit::text
 OR q->>'origin' IS DISTINCT FROM 'persisted_environment_effect'
 OR q->'simulated_environment' IS DISTINCT FROM 'true'::jsonb
 OR r->'port' IS DISTINCT FROM 'null'::jsonb THEN RETURN false;END IF;
 IF encode(sha256(convert_to(p_inputs,'UTF8')),'hex') IS DISTINCT FROM e->>'input_sha256'
 OR input_value->'production_request'->'request_ref' IS DISTINCT FROM r->'artifact'->'request_ref'
 OR request_value->>'id' IS DISTINCT FROM r->'artifact'->'request_ref'->>'id'
 OR request_value->'version' IS DISTINCT FROM r->'artifact'->'request_ref'->'version'
 OR r->'artifact'->'request_ref'->>'sha256' IS DISTINCT FROM p_request_hash
 OR request_value->>'kind' IS DISTINCT FROM 'production-requests'
 OR request_value->>'created_by_role' IS DISTINCT FROM 'brief_delivery_coordinator'
 OR request_value->'simulation_only' IS DISTINCT FROM 'true'::jsonb THEN RETURN false;END IF;
 -- Independent immutable API return record; scheduler cannot insert or rewrite.
 size=octet_length(r::text)+octet_length(p_request)+octet_length(p_inputs);
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_quota:world_service_effects:'||(s->>'project_id'),0));
 SELECT coalesce(sum(byte_size),0) INTO used FROM campaign_private.world_service_effects WHERE project_id=(s->>'project_id')::uuid;
 IF used+size>536870912 THEN RAISE EXCEPTION 'private Marketing service receipt quota exhausted';END IF;
 INSERT INTO campaign_private.world_service_effects(project_id,plan_id,effect_id,receipt_id,reply,reply_sha256,source_contract_sha256,post_state_sha256,
 request_canonical,request_sha256,input_canonical,input_sha256,node_sha256,byte_size)
 VALUES((s->>'project_id')::uuid,p_plan,p_effect,(q->>'world_effect_id')::uuid,r,p_hash,p_contract,p_before,
 p_request,p_request_hash,p_inputs,e->>'input_sha256',e->>'node_sha256',size);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.commit_private_world_service(uuid,uuid,uuid,text,integer,integer,uuid,text,text,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.commit_private_world_service(uuid,uuid,uuid,text,integer,integer,uuid,text,text,text,text,text,text,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_world_service_records(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE ctx jsonb;rows jsonb;
BEGIN
 -- Existing denial-only stop context binds original capability and group/plan
 -- locks. This read cannot create work, replay an effect or grant a score.
 ctx=marketing_runtime.world_stop_context(p_job,p_lease,p_plan);
 IF ctx IS NULL THEN RETURN NULL;END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('effect_id',r.effect_id,'receipt_id',r.receipt_id,
  'reply_sha256',r.reply_sha256,'source_contract_sha256',r.source_contract_sha256,
  'post_state_sha256',r.post_state_sha256,'request_sha256',r.request_sha256,
  'request_id',r.request_canonical::jsonb->>'id','request_version',r.request_canonical::jsonb->'version',
  'input_sha256',r.input_sha256,'node_sha256',r.node_sha256) ORDER BY r.effect_id),'[]'::jsonb) INTO rows
 FROM campaign_private.world_service_effects r
 WHERE r.project_id=(ctx->'session'->>'project_id')::uuid AND r.plan_id=p_plan;
 RETURN jsonb_build_object('records',rows,'source_contract_sha256',(
  SELECT d.definition->>'service_contract_sha256' FROM campaign_private.world_sources d
  WHERE d.project_id=(ctx->'session'->>'project_id')::uuid AND d.id=(ctx->'session'->>'source_id')::uuid));
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_service_records(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_service_records(uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_world_service_input(p_job uuid,p_lease uuid,p_plan uuid,p_effect uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE ctx jsonb;value jsonb;BEGIN
 ctx=marketing_runtime.world_stop_context(p_job,p_lease,p_plan);
 IF ctx IS NULL THEN RETURN NULL;END IF;
 SELECT jsonb_build_object('request_canonical',r.request_canonical,'request_sha256',r.request_sha256,
  'input_canonical',r.input_canonical,'input_sha256',r.input_sha256,'node_sha256',r.node_sha256,
  'reply',r.reply,'reply_sha256',r.reply_sha256,'source_contract_sha256',r.source_contract_sha256)
 INTO value FROM campaign_private.world_service_effects r
 WHERE r.project_id=(ctx->'session'->>'project_id')::uuid AND r.plan_id=p_plan AND r.effect_id=p_effect;
 RETURN value;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_service_input(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_service_input(uuid,uuid,uuid,uuid) TO anvil_app;
