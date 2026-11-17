-- SOURCE ONLY: no migration/qualification/activation authority.
-- Independent API custody of the atomic decision/data/finance successor.
CREATE TABLE campaign_private.world_campaign_effect_states(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,effect_id uuid PRIMARY KEY,
 before_canonical text NOT NULL CHECK(octet_length(before_canonical)<=16777216),
 before_sha256 text NOT NULL CHECK(before_sha256=encode(sha256(convert_to(before_canonical,'UTF8')),'hex')),
 after_canonical text NOT NULL CHECK(octet_length(after_canonical)<=16777216),
 after_sha256 text NOT NULL CHECK(after_sha256=encode(sha256(convert_to(after_canonical,'UTF8')),'hex')),
 byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 33554432),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES campaign_private.world_sessions(project_id,plan_id),
 FOREIGN KEY(effect_id) REFERENCES campaign_private.world_service_effects(effect_id));
ALTER TABLE campaign_private.world_campaign_effect_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.world_campaign_effect_states FORCE ROW LEVEL SECURITY;
REVOKE ALL ON campaign_private.world_campaign_effect_states FROM PUBLIC,anvil_app,anvil_golden_scheduler,anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.world_campaign_effect_states
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE FUNCTION marketing_runtime.private_world_campaign_context(
 p_job uuid,p_lease uuid,p_plan uuid,p_week integer,p_visit integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 s campaign_private.world_sessions;e marketing_runtime.workflow_effects;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
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
 OR s.last_week<>p_week OR NOT EXISTS(SELECT 1 FROM campaign_private.world_sources d
 WHERE d.project_id=project AND d.id=s.source_id AND d.definition->>'schema_version'='anvil.marketing-private-world-definition.v4') THEN RETURN NULL;END IF;
 -- Completion of one actual already-claimed approver intent, not new work.
 SELECT * INTO e FROM marketing_runtime.workflow_effects
 WHERE project_id=project AND episode_id=s.episode_id AND generation=s.generation
 AND execution_sha256=s.attachment->>'execution_sha256' AND node_id='approver' AND week=p_week AND visit=p_visit FOR UPDATE;
 IF NOT FOUND OR e.state<>'claimed'
 OR EXISTS(SELECT 1 FROM campaign_private.world_service_effects WHERE effect_id=e.id) THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('session',to_jsonb(s),'effect',to_jsonb(e));
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_campaign_context(uuid,uuid,uuid,integer,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_campaign_context(uuid,uuid,uuid,integer,integer) TO anvil_app;

CREATE FUNCTION marketing_runtime.commit_private_world_campaign(
 p_job uuid,p_lease uuid,p_plan uuid,p_week integer,p_visit integer,p_effect uuid,
 p_before text,p_before_state text,p_after text,p_after_hash text,
 p_reply text,p_hash text,p_contract text,p_request text,p_request_hash text,p_inputs text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE ctx jsonb;s jsonb;e jsonb;r jsonb;q jsonb;request_value jsonb;input_value jsonb;
 old_state jsonb;new_state jsonb;source_hash text;definition_value jsonb;
 baseline_actual bigint;baseline_outstanding bigint;used bigint;size integer;state_size integer;key text;
BEGIN
 IF p_before_state IS NULL OR p_after IS NULL OR p_reply IS NULL OR p_request IS NULL OR p_inputs IS NULL
 OR octet_length(p_before_state)>16777216 OR octet_length(p_after)>16777216
 OR octet_length(p_reply)>60000 OR octet_length(p_request)>49152 OR octet_length(p_inputs)>32768
 OR p_before IS DISTINCT FROM encode(sha256(convert_to(p_before_state,'UTF8')),'hex')
 OR p_after_hash IS DISTINCT FROM encode(sha256(convert_to(p_after,'UTF8')),'hex')
 OR p_hash IS DISTINCT FROM encode(sha256(convert_to(p_reply,'UTF8')),'hex')
 OR p_request_hash IS DISTINCT FROM encode(sha256(convert_to(p_request,'UTF8')),'hex')
 OR p_contract IS NULL OR p_contract!~'^[a-f0-9]{64}$' THEN RETURN false;END IF;
 ctx=marketing_runtime.private_world_campaign_context(p_job,p_lease,p_plan,p_week,p_visit);
 IF ctx IS NULL THEN RETURN false;END IF;
 s=ctx->'session';e=ctx->'effect';r=p_reply::jsonb;q=r->'receipt';
 old_state=p_before_state::jsonb;new_state=p_after::jsonb;request_value=p_request::jsonb;input_value=p_inputs::jsonb;
 SELECT d.definition INTO definition_value FROM campaign_private.world_sources d
 WHERE d.project_id=(s->>'project_id')::uuid AND d.id=(s->>'source_id')::uuid;
 source_hash=definition_value->>'service_contract_sha256';
 IF (e->>'id')::uuid<>p_effect OR s->>'controller_state_sha256' IS DISTINCT FROM p_before
 OR old_state IS DISTINCT FROM s->'controller_state' OR p_contract IS DISTINCT FROM source_hash
 OR jsonb_typeof(r->'artifact') IS DISTINCT FROM 'object'
 OR r->'artifact'->>'source_contract_sha256' IS DISTINCT FROM p_contract
 OR q->>'input_sha256' IS DISTINCT FROM e->>'input_sha256'
 OR q->>'post_state_sha256' IS DISTINCT FROM p_after_hash
 OR q->>'world_binding_sha256' IS DISTINCT FROM s->>'world_binding_sha256'
 OR q->>'episode_id' IS DISTINCT FROM s->>'episode_id' OR q->>'generation' IS DISTINCT FROM s->>'generation'
 OR q->>'node_id' IS DISTINCT FROM 'approver' OR q->>'week' IS DISTINCT FROM p_week::text
 OR q->>'visit' IS DISTINCT FROM p_visit::text OR q->>'origin' IS DISTINCT FROM 'persisted_environment_effect'
 OR q->'simulated_environment' IS DISTINCT FROM 'true'::jsonb THEN RETURN false;END IF;
 IF encode(sha256(convert_to(p_inputs,'UTF8')),'hex') IS DISTINCT FROM e->>'input_sha256'
 OR input_value->'approval_request'->'request_ref' IS DISTINCT FROM r->'artifact'->'request_ref'
 OR request_value->>'id' IS DISTINCT FROM r->'artifact'->'request_ref'->>'id'
 OR request_value->'version' IS DISTINCT FROM r->'artifact'->'request_ref'->'version'
 OR r->'artifact'->'request_ref'->>'sha256' IS DISTINCT FROM p_request_hash
 OR request_value IS DISTINCT FROM old_state->'objects'->(request_value->>'id')
 OR request_value->>'kind' IS DISTINCT FROM 'approval-requests'
 OR request_value->>'created_by_role' IS DISTINCT FROM 'campaign_orchestrator'
 OR request_value->'simulation_only' IS DISTINCT FROM 'true'::jsonb THEN RETURN false;END IF;
 -- No role/capability/clock/request/history mutation by a controller response.
 IF new_state-ARRAY['initial','controller_keys','approvals','approval_bounds','reservations','committed','settled','events','audit']
 IS DISTINCT FROM old_state-ARRAY['initial','controller_keys','approvals','approval_bounds','reservations','committed','settled','events','audit'] THEN RETURN false;END IF;
 FOREACH key IN ARRAY ARRAY['schema_version','profile','case_id','start','outcome','budget_minor','generation','trial_id',
 'role_tokens','controller_token','clock','objects','role_idempotency','revisions','transitions','history'] LOOP
  IF new_state->key IS DISTINCT FROM old_state->key THEN RETURN false;END IF;
 END LOOP;
 IF (new_state->'initial')-ARRAY['reports','ledger','budget-snapshots','budget-envelopes']
 IS DISTINCT FROM (old_state->'initial')-ARRAY['reports','ledger','budget-snapshots','budget-envelopes'] THEN RETURN false;END IF;
 IF r->>'port'='timeout' THEN
  IF new_state IS DISTINCT FROM old_state OR r->'artifact'->>'decision' IS DISTINCT FROM 'pending'
  OR r->'artifact'->'campaign_authority_issued' IS DISTINCT FROM 'false'::jsonb THEN RETURN false;END IF;
 ELSIF r->>'port'='responded' THEN
  SELECT coalesce(sum((j->>'committed_minor')::bigint) FILTER(WHERE (j->>'settled_at')::timestamptz<=(old_state->>'clock')::timestamptz),0),
  coalesce(sum((j->>'committed_minor')::bigint) FILTER(WHERE (j->>'settled_at')::timestamptz>(old_state->>'clock')::timestamptz),0)
  INTO baseline_actual,baseline_outstanding FROM jsonb_array_elements((definition_value->'finance_source_documents'->>
  ('cases/'||(old_state->>'case_id')||'/commitments.json'))::jsonb) j
  WHERE (j->>'created_at')::timestamptz<=(old_state->>'clock')::timestamptz
  AND (j->>'released_at')::timestamptz<=(old_state->>'clock')::timestamptz;
  IF r->'artifact'->>'decision' IS DISTINCT FROM 'approved'
  OR r->'artifact'->'campaign_authority_issued' IS DISTINCT FROM 'true'::jsonb
  OR r->'artifact'->'real_human_approval' IS DISTINCT FROM 'false'::jsonb
  OR r->'artifact'->'simulation_only' IS DISTINCT FROM 'true'::jsonb
  OR r->'artifact'->'amount_bound_minor' IS DISTINCT FROM '200000'::jsonb
  OR new_state->'approvals' IS DISTINCT FROM jsonb_build_array(jsonb_build_object('key',jsonb_build_array(request_value->>'id',request_value->'version'),'value',true))
  OR new_state->'approval_bounds' IS DISTINCT FROM jsonb_build_array(jsonb_build_object('key',jsonb_build_array(request_value->>'id',request_value->'version'),'value',200000))
  OR new_state->'reservations' IS DISTINCT FROM jsonb_build_array(jsonb_build_object('key',jsonb_build_array(request_value->>'id',request_value->'version'),'value',200000))
  OR old_state->'approvals' IS DISTINCT FROM '[]'::jsonb OR old_state->'reservations' IS DISTINCT FROM '[]'::jsonb
  OR old_state->'committed' IS DISTINCT FROM '0'::jsonb OR old_state->'settled' IS DISTINCT FROM '0'::jsonb
  OR new_state->'committed' IS DISTINCT FROM to_jsonb(baseline_outstanding)
  OR new_state->'settled' IS DISTINCT FROM to_jsonb(baseline_actual)
  OR baseline_actual+baseline_outstanding+200000+1500000>20000000 THEN RETURN false;END IF;
 ELSE RETURN false;END IF;
 size=octet_length(r::text)+octet_length(p_request)+octet_length(p_inputs);
 state_size=octet_length(p_before_state)+octet_length(p_after);
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_quota:world_service_effects:'||(s->>'project_id'),0));
 SELECT coalesce(sum(byte_size),0) INTO used FROM campaign_private.world_service_effects WHERE project_id=(s->>'project_id')::uuid;
 IF used+size>536870912 THEN RAISE EXCEPTION 'private Marketing service receipt quota exhausted';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_quota:world_campaign_effect_states:'||(s->>'project_id'),0));
 SELECT coalesce(sum(byte_size),0) INTO used FROM campaign_private.world_campaign_effect_states WHERE project_id=(s->>'project_id')::uuid;
 IF used+state_size>536870912 THEN RAISE EXCEPTION 'private Marketing campaign state quota exhausted';END IF;
 INSERT INTO campaign_private.world_service_effects(project_id,plan_id,effect_id,receipt_id,reply,reply_sha256,source_contract_sha256,post_state_sha256,
 request_canonical,request_sha256,input_canonical,input_sha256,node_sha256,byte_size)
 VALUES((s->>'project_id')::uuid,p_plan,p_effect,(q->>'world_effect_id')::uuid,r,p_hash,p_contract,p_after_hash,
 p_request,p_request_hash,p_inputs,e->>'input_sha256',e->>'node_sha256',size);
 INSERT INTO campaign_private.world_campaign_effect_states(project_id,plan_id,effect_id,before_canonical,before_sha256,after_canonical,after_sha256,byte_size)
 VALUES((s->>'project_id')::uuid,p_plan,p_effect,p_before_state,p_before,p_after,p_after_hash,state_size);
 UPDATE campaign_private.world_sessions SET controller_state=new_state,controller_state_sha256=p_after_hash
 WHERE project_id=(s->>'project_id')::uuid AND plan_id=p_plan;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.commit_private_world_campaign(uuid,uuid,uuid,integer,integer,uuid,text,text,text,text,text,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.commit_private_world_campaign(uuid,uuid,uuid,integer,integer,uuid,text,text,text,text,text,text,text,text,text,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_world_campaign_state(p_job uuid,p_lease uuid,p_plan uuid,p_effect uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE ctx jsonb;value jsonb;BEGIN
 ctx=marketing_runtime.world_stop_context(p_job,p_lease,p_plan);
 IF ctx IS NULL THEN RETURN NULL;END IF;
 SELECT jsonb_build_object('before_canonical',r.before_canonical,'before_sha256',r.before_sha256,
 'after_canonical',r.after_canonical,'after_sha256',r.after_sha256) INTO value
 FROM campaign_private.world_campaign_effect_states r
 WHERE r.project_id=(ctx->'session'->>'project_id')::uuid AND r.plan_id=p_plan AND r.effect_id=p_effect;
 RETURN value;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_campaign_state(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_campaign_state(uuid,uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.commit_private_world_campaign_release(
 p_job uuid,p_lease uuid,p_plan uuid,p_before text,p_week integer,p_state text,p_state_hash text,p_reply text,p_reply_hash text,p_inventory text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s jsonb;old_state jsonb;v jsonb;r jsonb;inventory_value jsonb;key text;old_current jsonb;new_current jsonb;
 old_history jsonb;new_history jsonb;count_value integer;reserved numeric;committed numeric;settled numeric;
BEGIN
 IF p_state IS NULL OR p_reply IS NULL OR p_inventory IS NULL OR p_week NOT BETWEEN 1 AND 12
 OR octet_length(p_state)>16777216 OR octet_length(p_reply)>65536 OR octet_length(p_inventory)>65536
 OR p_state_hash IS DISTINCT FROM encode(sha256(convert_to(p_state,'UTF8')),'hex')
 OR p_reply_hash IS DISTINCT FROM encode(sha256(convert_to(p_reply,'UTF8')),'hex') THEN RETURN false;END IF;
 -- This is new release work: the ordinary session gate still denies fencing.
 s=marketing_runtime.private_world_session(p_job,p_lease,p_plan);
 IF s IS NULL OR s->>'controller_state_sha256' IS DISTINCT FROM p_before OR (s->>'last_week')::integer<>p_week-1
 OR NOT EXISTS(SELECT 1 FROM campaign_private.world_sources d WHERE d.project_id=(s->>'project_id')::uuid
 AND d.id=(s->>'source_id')::uuid AND d.definition->>'schema_version'='anvil.marketing-private-world-definition.v4') THEN RETURN false;END IF;
 old_state=s->'controller_state';v=p_state::jsonb;r=p_reply::jsonb;inventory_value=p_inventory::jsonb;
 IF jsonb_typeof(inventory_value) IS DISTINCT FROM 'array' OR jsonb_array_length(inventory_value)>50
 OR jsonb_typeof(old_state->'approvals') IS DISTINCT FROM 'array' OR jsonb_array_length(old_state->'approvals')<>1
 OR old_state->'approvals'->0->'value' IS DISTINCT FROM 'true'::jsonb
 OR jsonb_typeof(v->'reservations') IS DISTINCT FROM 'array' OR jsonb_array_length(v->'reservations')<>1
 OR v->'reservations'->0->'key' IS DISTINCT FROM old_state->'reservations'->0->'key' THEN RETURN false;END IF;
 IF v-ARRAY['initial','controller_keys','clock','committed','settled','reservations','events','audit']
 IS DISTINCT FROM old_state-ARRAY['initial','controller_keys','clock','committed','settled','reservations','events','audit']
 OR (v->'initial')-'budget-snapshots' IS DISTINCT FROM (old_state->'initial')-'budget-snapshots' THEN RETURN false;END IF;
 SELECT count(*),jsonb_agg(x)->0 INTO count_value,old_current FROM jsonb_array_elements(old_state->'initial'->'budget-snapshots') x
 WHERE x->'public'->>'provenance'='CURRENT_SOURCE_RECONCILED_SIMULATED_CONTROLLER_ACCOUNTING';
 IF count_value<>1 THEN RETURN false;END IF;
 SELECT count(*),jsonb_agg(x)->0 INTO count_value,new_current FROM jsonb_array_elements(v->'initial'->'budget-snapshots') x
 WHERE x->'public'->>'id'=old_current->'public'->>'id';
 IF count_value<>1 OR new_current->'actor_visible' IS DISTINCT FROM 'true'::jsonb
 OR new_current->'outcome_binding' IS DISTINCT FROM 'null'::jsonb THEN RETURN false;END IF;
 SELECT coalesce(jsonb_agg(x ORDER BY x->'public'->>'id'),'[]'::jsonb) INTO old_history
 FROM jsonb_array_elements(old_state->'initial'->'budget-snapshots') x WHERE x->'public'->>'id'<>old_current->'public'->>'id';
 SELECT coalesce(jsonb_agg(x ORDER BY x->'public'->>'id'),'[]'::jsonb) INTO new_history
 FROM jsonb_array_elements(v->'initial'->'budget-snapshots') x WHERE x->'public'->>'id'<>old_current->'public'->>'id';
 IF old_history IS DISTINCT FROM new_history OR jsonb_typeof(v->'committed') IS DISTINCT FROM 'number'
 OR jsonb_typeof(v->'settled') IS DISTINCT FROM 'number'
 OR jsonb_typeof(v->'reservations'->0->'value') IS DISTINCT FROM 'number' OR v->>'committed'!~'^(0|[1-9][0-9]*)$'
 OR v->>'settled'!~'^(0|[1-9][0-9]*)$' OR v->'reservations'->0->>'value'!~'^(0|[1-9][0-9]*)$' THEN RETURN false;END IF;
 committed=(v->>'committed')::numeric;settled=(v->>'settled')::numeric;reserved=(v->'reservations'->0->>'value')::numeric;
 IF committed IS NULL OR settled IS NULL OR reserved IS NULL OR committed+settled+reserved+1500000>20000000
 OR settled<(old_state->>'settled')::numeric OR reserved>(old_state->'reservations'->0->>'value')::numeric
 OR new_current->'public'->'actual_settled_usd_minor' IS DISTINCT FROM v->'settled'
 OR new_current->'public'->'binding_outstanding_usd_minor' IS DISTINCT FROM v->'committed'
 OR new_current->'public'->'active_reservations_usd_minor' IS DISTINCT FROM v->'reservations'->0->'value'
 OR new_current->'public'->'contingency_locked_usd_minor' IS DISTINCT FROM '1500000'::jsonb
 OR new_current->'public'->'media_remaining_authorisable_usd_minor' IS DISTINCT FROM to_jsonb(20000000-1500000-committed-settled-reserved)
 OR new_current->'public'->>'as_of' IS DISTINCT FROM v->>'clock'
 OR new_current->'public'->>'released_at' IS DISTINCT FROM v->>'clock'
 OR new_current->>'released_at' IS DISTINCT FROM v->>'clock' THEN RETURN false;END IF;
 IF (v->>'clock')::timestamptz<(old_state->>'clock')::timestamptz
 OR r->>'world_binding_id' IS DISTINCT FROM s->>'world_binding_id' OR r->>'world_binding_sha256' IS DISTINCT FROM s->>'world_binding_sha256'
 OR r->>'episode_id' IS DISTINCT FROM s->>'episode_id' OR r->>'generation' IS DISTINCT FROM s->>'generation'
 OR r->>'week' IS DISTINCT FROM p_week::text OR r->>'case_id' IS DISTINCT FROM s->'attachment'->>'case_id'
 OR r->>'case_snapshot_sha256' IS DISTINCT FROM s->'attachment'->>'case_snapshot_sha256'
 OR (r->>'released_at')::timestamptz IS DISTINCT FROM (v->>'clock')::timestamptz THEN RETURN false;END IF;
 INSERT INTO campaign_private.world_releases(project_id,plan_id,week,reply,reply_sha256,inventory,post_state_sha256)
 VALUES((s->>'project_id')::uuid,p_plan,p_week,r,p_reply_hash,inventory_value,p_state_hash);
 UPDATE campaign_private.world_sessions SET controller_state=v,controller_state_sha256=p_state_hash,last_week=p_week
 WHERE project_id=(s->>'project_id')::uuid AND plan_id=p_plan;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.commit_private_world_campaign_release(uuid,uuid,uuid,text,integer,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.commit_private_world_campaign_release(uuid,uuid,uuid,text,integer,text,text,text,text,text) TO anvil_app;
