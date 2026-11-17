-- SOURCE CANDIDATE ONLY: original opening0 + twelve report reviews.
-- No rows, qualification, runtime admission or paid dispatch are created.
ALTER TABLE campaign_private.world_releases DROP CONSTRAINT world_releases_week_check;
ALTER TABLE campaign_private.world_releases ADD CHECK(week BETWEEN 0 AND 12);
ALTER TABLE marketing_runtime.workflow_effects DROP CONSTRAINT workflow_effects_week_check;
ALTER TABLE marketing_runtime.workflow_effects ADD CHECK(week BETWEEN 0 AND 12);
ALTER TABLE marketing_runtime.paid_turn_intents DROP CONSTRAINT paid_turn_intents_week_check;
ALTER TABLE marketing_runtime.paid_turn_intents ADD CHECK(week BETWEEN 0 AND 12);

CREATE FUNCTION campaign_private.opening_program(p_project uuid,p_plan uuid) RETURNS text
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT d.definition->>'operator_program_id' FROM campaign_private.world_sessions s
 JOIN campaign_private.world_sources d ON d.project_id=s.project_id AND d.id=s.source_id
 WHERE s.project_id=p_project AND s.plan_id=p_plan
 AND d.definition->>'schema_version'='anvil.marketing-private-world-definition.v5'
 AND d.definition->>'operator_program_id'='marketing-opening0-and-twelve-reviews-v1';
$$;
REVOKE ALL ON FUNCTION campaign_private.opening_program(uuid,uuid) FROM PUBLIC,anvil_app,anvil_golden_scheduler,anvil_golden_grader;

CREATE OR REPLACE FUNCTION marketing_runtime.private_world_runtime_receipt(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('source',jsonb_build_object(
  'id',d.id,'definition_sha256',d.definition_sha256,'source_sha256',d.source_sha256,
  'case_id',d.case_id,'case_snapshot_sha256',d.case_snapshot_sha256,'execution_sha256',d.execution_sha256,
  'rights_receipt_sha256',d.definition->>'rights_receipt_sha256','definition_schema',d.definition->>'schema_version','operator_program_id',d.definition->>'operator_program_id','operator_program_sha256',d.definition->>'operator_program_sha256'),'qualification',to_jsonb(q))
 FROM campaign_private.world_sessions s
 JOIN campaign_private.world_sources d ON d.project_id=s.project_id AND d.id=s.source_id
 JOIN campaign_private.world_qualifications q ON q.project_id=s.project_id AND q.id=s.qualification_id
 WHERE s.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND s.plan_id=p_plan AND s.job_id=p_job
 AND s.lease_sha256=encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
 AND marketing_runtime.paid_job_current(p_job,p_lease,p_plan) AND marketing_runtime.world_session_current(p_plan);
$$;


CREATE OR REPLACE FUNCTION marketing_runtime.commit_private_world_campaign_release(
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
 AND d.id=(s->>'source_id')::uuid AND d.definition->>'schema_version' IN('anvil.marketing-private-world-definition.v4','anvil.marketing-private-world-definition.v5')) THEN RETURN false;END IF;
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


CREATE FUNCTION campaign_private.opening_index_guard() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s campaign_private.world_sessions;program text;
BEGIN
 IF TG_TABLE_NAME='workflow_effects' THEN
  SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=NEW.project_id
  AND episode_id=NEW.episode_id AND generation=NEW.generation AND attachment->>'execution_sha256'=NEW.execution_sha256;
 ELSE
  SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=NEW.project_id AND plan_id=NEW.plan_id;
 END IF;
 IF TG_TABLE_NAME='world_releases' AND NEW.week=0 THEN
  IF s.plan_id IS NULL OR campaign_private.opening_program(s.project_id,s.plan_id) IS NULL
   OR NEW.reply->>'schema_version' IS DISTINCT FROM 'anvil.marketing-world-opening-release.v1'
   OR NEW.reply->>'phase' IS DISTINCT FROM 'opening'
   OR NEW.reply->>'operator_program_id' IS DISTINCT FROM 'marketing-opening0-and-twelve-reviews-v1'
   OR s.last_week<>0 THEN RAISE EXCEPTION 'original opening source required';END IF;
  RETURN NEW;
 END IF;
 IF s.plan_id IS NULL THEN
  IF NEW.week=0 THEN RAISE EXCEPTION 'opening index requires original world session';END IF;
  RETURN NEW;
 END IF;
 program=campaign_private.opening_program(s.project_id,s.plan_id);
 IF NEW.week=0 AND program IS NULL THEN RAISE EXCEPTION 'legacy world cannot use opening index';END IF;
 IF program IS NOT NULL AND NOT EXISTS(SELECT 1 FROM campaign_private.world_releases r
  WHERE r.project_id=s.project_id AND r.plan_id=s.plan_id AND r.week=0) THEN
  RAISE EXCEPTION 'actual immutable opening release required before effects or reviews';
 END IF;
 IF TG_TABLE_NAME<>'world_releases' AND program IS NOT NULL AND NEW.week<>s.last_week THEN
  RAISE EXCEPTION 'effect must match actual current opening or review';
 END IF;
 IF TG_TABLE_NAME='paid_turn_intents' THEN
  IF NEW.week=0 AND NEW.public_context->>'schema_version' IS DISTINCT FROM 'anvil.marketing-opening-role-phase.v1' THEN
   RAISE EXCEPTION 'incorrect opening role context';
  END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION campaign_private.opening_index_guard() FROM PUBLIC;
CREATE TRIGGER opening_source BEFORE INSERT ON campaign_private.world_releases
 FOR EACH ROW EXECUTE FUNCTION campaign_private.opening_index_guard();
CREATE TRIGGER opening_source BEFORE INSERT ON marketing_runtime.workflow_effects
 FOR EACH ROW EXECUTE FUNCTION campaign_private.opening_index_guard();
CREATE TRIGGER opening_source BEFORE INSERT ON marketing_runtime.paid_turn_intents
 FOR EACH ROW EXECUTE FUNCTION campaign_private.opening_index_guard();

CREATE FUNCTION marketing_runtime.commit_private_world_opening(
 p_job uuid,p_lease uuid,p_plan uuid,p_before text,p_reply text,p_hash text,p_inventory text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s jsonb;d jsonb;r jsonb;v jsonb;key text;
BEGIN
 IF p_reply IS NULL OR p_inventory IS NULL OR octet_length(p_reply)>65536 OR octet_length(p_inventory)>65536
 OR p_hash IS DISTINCT FROM encode(sha256(convert_to(p_reply,'UTF8')),'hex') THEN RETURN false;END IF;
 s=marketing_runtime.private_world_session(p_job,p_lease,p_plan);
 IF s IS NULL OR s->>'controller_state_sha256' IS DISTINCT FROM p_before OR (s->>'last_week')::integer<>0
 OR campaign_private.opening_program((s->>'project_id')::uuid,p_plan) IS NULL THEN RETURN false;END IF;
 SELECT definition INTO d FROM campaign_private.world_sources
 WHERE project_id=(s->>'project_id')::uuid AND id=(s->>'source_id')::uuid;
 r=p_reply::jsonb;v=p_inventory::jsonb;
 IF jsonb_typeof(v) IS DISTINCT FROM 'array' OR jsonb_array_length(v)>50
 OR (s->'controller_state'->>'clock')::timestamptz IS DISTINCT FROM (d->'opening'->>'instant')::timestamptz
 OR (r->>'released_at')::timestamptz IS DISTINCT FROM (d->'opening'->>'instant')::timestamptz
 OR r->>'window_ref' IS DISTINCT FROM d->'opening'->>'window_ref'
 OR r->>'schema_version' IS DISTINCT FROM 'anvil.marketing-world-opening-release.v1'
 OR r->>'week' IS DISTINCT FROM '0' OR r->>'phase' IS DISTINCT FROM 'opening'
 OR r->>'operator_program_id' IS DISTINCT FROM d->>'operator_program_id'
 OR EXISTS(SELECT 1 FROM campaign_private.world_releases WHERE project_id=(s->>'project_id')::uuid AND plan_id=p_plan)
 OR EXISTS(SELECT 1 FROM marketing_runtime.workflow_effects WHERE project_id=(s->>'project_id')::uuid
  AND episode_id=(s->>'episode_id')::uuid AND generation=(s->>'generation')::integer)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_turn_intents WHERE project_id=(s->>'project_id')::uuid AND plan_id=p_plan)
 THEN RETURN false;END IF;
 FOREACH key IN ARRAY ARRAY['world_binding_id','world_binding_sha256','episode_id','generation','case_id','case_snapshot_sha256'] LOOP
  IF r->key IS DISTINCT FROM s->'attachment'->key THEN RETURN false;END IF;
 END LOOP;
 INSERT INTO campaign_private.world_releases(project_id,plan_id,week,reply,reply_sha256,inventory,post_state_sha256)
 VALUES((s->>'project_id')::uuid,p_plan,0,r,p_hash,v,p_before);
 -- Opening is an observation of the original clock/state, never a reset or
 -- finance/report mutation. last_week stays0 until real review1 is released.
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.commit_private_world_opening(uuid,uuid,uuid,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.commit_private_world_opening(uuid,uuid,uuid,text,text,text,text) TO anvil_app;
CREATE OR REPLACE FUNCTION marketing_runtime.private_world_graph_records(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s jsonb;releases jsonb;effects jsonb;turns jsonb;BEGIN
 s=marketing_runtime.private_world_session(p_job,p_lease,p_plan);
 IF s IS NULL THEN RETURN NULL;END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.week),'[]'::jsonb) INTO releases
 FROM campaign_private.world_releases r WHERE r.project_id=(s->>'project_id')::uuid AND r.plan_id=p_plan;
 SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY e.week,e.node_id,e.visit),'[]'::jsonb) INTO effects
 FROM marketing_runtime.workflow_effects e WHERE e.project_id=(s->>'project_id')::uuid AND e.episode_id=(s->>'episode_id')::uuid
 AND e.generation=(s->>'generation')::integer AND e.execution_sha256=s->'attachment'->>'execution_sha256';
 SELECT coalesce(jsonb_agg(value),'[]'::jsonb) INTO turns FROM marketing_runtime.reconstruction_turns((s->>'project_id')::uuid,p_plan) value;
 RETURN jsonb_build_object('attachment',s->'attachment','releases',releases,'effects',effects,'turns',turns,'operator_program_id',campaign_private.opening_program((s->>'project_id')::uuid,p_plan));
END $$;

CREATE OR REPLACE FUNCTION marketing_runtime.world_stop_context(p_job uuid,p_lease uuid,p_plan uuid)
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
 records=jsonb_build_object('attachment',s.attachment,'releases',releases,'effects',effects,'turns',turns,'operator_program_id',campaign_private.opening_program(project,p_plan));
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

CREATE OR REPLACE FUNCTION marketing_runtime.private_world_service_context(
 p_job uuid,p_lease uuid,p_plan uuid,p_node text,p_week integer,p_visit integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 s campaign_private.world_sessions;e marketing_runtime.workflow_effects;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' OR p_node<>'task3'
 OR p_week NOT BETWEEN 0 AND 12 OR p_visit NOT BETWEEN 1 AND 400 THEN RETURN NULL;END IF;
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
 IF p_week=0 AND(campaign_private.opening_program(project,p_plan) IS NULL OR NOT EXISTS(SELECT 1 FROM campaign_private.world_releases r WHERE r.project_id=project AND r.plan_id=p_plan AND r.week=0)) THEN RETURN NULL;END IF;
 -- Only an actual already-committed workflow intent may complete after fencing.
 -- No new role, model, workflow intent or source authority is admitted here.
 SELECT * INTO e FROM marketing_runtime.workflow_effects
 WHERE project_id=project AND episode_id=s.episode_id AND generation=s.generation
 AND execution_sha256=s.attachment->>'execution_sha256' AND node_id=p_node AND week=p_week AND visit=p_visit FOR UPDATE;
 IF NOT FOUND OR e.state<>'claimed'
 OR EXISTS(SELECT 1 FROM campaign_private.world_service_effects WHERE effect_id=e.id) THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('session',to_jsonb(s),'effect',to_jsonb(e));
END $$;

CREATE OR REPLACE FUNCTION marketing_runtime.private_world_campaign_context(
 p_job uuid,p_lease uuid,p_plan uuid,p_week integer,p_visit integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 s campaign_private.world_sessions;e marketing_runtime.workflow_effects;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR p_week NOT BETWEEN 0 AND 12 OR p_visit NOT BETWEEN 1 AND 400 THEN RETURN NULL;END IF;
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
 WHERE d.project_id=project AND d.id=s.source_id AND d.definition->>'schema_version' IN('anvil.marketing-private-world-definition.v4','anvil.marketing-private-world-definition.v5')) THEN RETURN NULL;END IF;
 IF p_week=0 AND(campaign_private.opening_program(project,p_plan) IS NULL OR NOT EXISTS(SELECT 1 FROM campaign_private.world_releases r WHERE r.project_id=project AND r.plan_id=p_plan AND r.week=0)) THEN RETURN NULL;END IF;
 -- Completion of one actual already-claimed approver intent, not new work.
 SELECT * INTO e FROM marketing_runtime.workflow_effects
 WHERE project_id=project AND episode_id=s.episode_id AND generation=s.generation
 AND execution_sha256=s.attachment->>'execution_sha256' AND node_id='approver' AND week=p_week AND visit=p_visit FOR UPDATE;
 IF NOT FOUND OR e.state<>'claimed'
 OR EXISTS(SELECT 1 FROM campaign_private.world_service_effects WHERE effect_id=e.id) THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('session',to_jsonb(s),'effect',to_jsonb(e));
END $$;
