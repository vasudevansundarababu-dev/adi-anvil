-- Operator-only source candidates. No source, qualification or approval seeded.
CREATE TABLE campaign_private.world_sources(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,dataset_id uuid NOT NULL,
 case_id text NOT NULL CHECK(case_id IN('GT2-R01','GT2-R02')),
 case_snapshot_sha256 text NOT NULL CHECK(case_snapshot_sha256~'^[a-f0-9]{64}$'),
 execution_sha256 text NOT NULL CHECK(execution_sha256~'^[a-f0-9]{64}$'),
 source_sha256 text NOT NULL CHECK(source_sha256~'^[a-f0-9]{64}$'),
 definition jsonb NOT NULL CHECK(octet_length(definition::text)<=16777216),
 definition_sha256 text NOT NULL CHECK(definition_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,dataset_id) REFERENCES anvil.campaign_dataset_versions(project_id,id),
 UNIQUE(project_id,id));
CREATE TABLE campaign_private.world_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,source_id uuid NOT NULL,
 receipt jsonb NOT NULL CHECK(octet_length(receipt::text)<=65536),
 receipt_sha256 text NOT NULL CHECK(receipt_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),expires_at timestamptz NOT NULL,
 FOREIGN KEY(project_id,source_id) REFERENCES campaign_private.world_sources(project_id,id),
 CHECK(expires_at>created_at),UNIQUE(project_id,id));
CREATE TABLE campaign_private.world_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,
 reason_code text NOT NULL CHECK(length(reason_code) BETWEEN 1 AND 200),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,qualification_id) REFERENCES campaign_private.world_qualifications(project_id,id));
DO $$DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['world_sources','world_qualifications','world_revocations'] LOOP
  EXECUTE format('ALTER TABLE campaign_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE campaign_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
-- No app, scheduler, grader or worker direct read/write grants. The privileged
-- operator owns candidate/independent receipt insertion; body access is API-only
-- and requires an actual current leased paid job. No arbitrary source ID/path.
CREATE FUNCTION marketing_runtime.private_world_candidates(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS SETOF jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('source',to_jsonb(s),'qualification',to_jsonb(q))
 FROM marketing_runtime.paid_agent_bindings b
 JOIN campaign_private.world_sources s ON s.project_id=b.project_id AND s.dataset_id=b.dataset_id
  AND s.case_id=b.case_id AND s.case_snapshot_sha256=b.native_binding->'case_assignment'->>'snapshot_sha256'
  AND s.execution_sha256=b.execution_sha256
 JOIN LATERAL (
  SELECT v.* FROM campaign_private.world_qualifications v
  WHERE v.project_id=s.project_id AND v.source_id=s.id AND v.expires_at>clock_timestamp()
  AND NOT EXISTS(SELECT 1 FROM campaign_private.world_revocations r WHERE r.project_id=v.project_id AND r.qualification_id=v.id)
  ORDER BY v.created_at DESC,v.id DESC LIMIT 1
 ) q ON true
 WHERE b.plan_id=p_plan AND marketing_runtime.paid_job_current(p_job,p_lease,p_plan)
 ORDER BY s.id LIMIT 101;
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_candidates(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_candidates(uuid,uuid,uuid) TO anvil_app;

-- Paid coordinator journal checks metadata only, never deserializes controller
-- state. Existing non-paid software paths retain their separate legacy guard.
CREATE FUNCTION marketing_runtime.paid_episode_current(p_job uuid,p_lease uuid,p_plan uuid,p_episode uuid,p_generation integer,p_execution text)
 RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) AND EXISTS(
  SELECT 1 FROM marketing_runtime.paid_episode_links l
  JOIN marketing_runtime.paid_agent_bindings b ON b.project_id=l.project_id AND b.plan_id=l.plan_id
  JOIN marketing_runtime.episodes e ON e.project_id=l.project_id AND e.id=l.episode_id
  WHERE l.plan_id=p_plan AND l.job_id=p_job AND l.episode_id=p_episode AND l.generation=p_generation
  AND e.generation=p_generation AND e.assigned_user=b.created_by AND b.execution_sha256=p_execution
  AND l.lease_sha256=encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
  AND NOT EXISTS(SELECT 1 FROM marketing_runtime.seals s WHERE s.project_id=l.project_id AND s.episode_id=l.episode_id AND s.generation=l.generation));
$$;
REVOKE ALL ON FUNCTION marketing_runtime.paid_episode_current(uuid,uuid,uuid,uuid,integer,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.paid_episode_current(uuid,uuid,uuid,uuid,integer,text) TO anvil_golden_scheduler;

CREATE TABLE campaign_private.world_sessions(
 project_id uuid NOT NULL,plan_id uuid PRIMARY KEY,
 source_id uuid NOT NULL,qualification_id uuid NOT NULL,
 world_binding_id uuid NOT NULL UNIQUE,world_binding_sha256 text NOT NULL CHECK(world_binding_sha256~'^[a-f0-9]{64}$'),
 episode_id uuid NOT NULL,generation integer NOT NULL CHECK(generation=0),
 job_id uuid NOT NULL,lease_sha256 text NOT NULL CHECK(lease_sha256~'^[a-f0-9]{64}$'),
 repeat_index integer NOT NULL CHECK(repeat_index BETWEEN 0 AND 999),
 attachment jsonb NOT NULL CHECK(octet_length(attachment::text)<=32768),
 controller_state jsonb NOT NULL CHECK(octet_length(controller_state::text)<=16777216),
 controller_state_sha256 text NOT NULL CHECK(controller_state_sha256~'^[a-f0-9]{64}$'),
 last_week integer NOT NULL DEFAULT 0 CHECK(last_week BETWEEN 0 AND 12),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES marketing_runtime.paid_agent_bindings(project_id,plan_id),
 FOREIGN KEY(project_id,source_id) REFERENCES campaign_private.world_sources(project_id,id),
 FOREIGN KEY(project_id,qualification_id) REFERENCES campaign_private.world_qualifications(project_id,id),
 FOREIGN KEY(project_id,episode_id) REFERENCES marketing_runtime.episodes(project_id,id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.jobs(project_id,id),UNIQUE(project_id,plan_id));
ALTER TABLE campaign_private.world_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.world_sessions FORCE ROW LEVEL SECURITY;
-- No application/scheduler/worker/grader table grants. State is API-only.
CREATE FUNCTION campaign_private.world_review_fence() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE source_key uuid;BEGIN
 IF TG_TABLE_NAME='world_qualifications' THEN source_key=NEW.source_id;
 ELSE SELECT source_id INTO source_key FROM campaign_private.world_qualifications WHERE project_id=NEW.project_id AND id=NEW.qualification_id;END IF;
 PERFORM 1 FROM campaign_private.world_sources WHERE project_id=NEW.project_id AND id=source_key FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'exact private world source required';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER source_fence BEFORE INSERT ON campaign_private.world_qualifications
 FOR EACH ROW EXECUTE FUNCTION campaign_private.world_review_fence();
CREATE TRIGGER source_fence BEFORE INSERT ON campaign_private.world_revocations
 FOR EACH ROW EXECUTE FUNCTION campaign_private.world_review_fence();

CREATE FUNCTION marketing_runtime.world_session_current(p_plan uuid) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s campaign_private.world_sessions;BEGIN
 SELECT * INTO s FROM campaign_private.world_sessions WHERE plan_id=p_plan AND project_id=nullif(current_setting('anvil.project',true),'')::uuid;
 IF NOT FOUND THEN RETURN false;END IF;
 -- Shared source fence is retained through the final SDK/tool claim transaction;
 -- qualification/revocation insertion takes the conflicting source lock above.
 PERFORM 1 FROM campaign_private.world_sources WHERE project_id=s.project_id AND id=s.source_id FOR KEY SHARE;
 IF NOT FOUND THEN RETURN false;END IF;
 RETURN EXISTS(
  SELECT 1 FROM marketing_runtime.paid_agent_bindings b
  JOIN anvil.harbor_agent_plans p ON p.project_id=b.project_id AND p.id=b.plan_id
  JOIN anvil.jobs j ON j.project_id=s.project_id AND j.id=s.job_id
  JOIN campaign_private.world_sources d ON d.project_id=s.project_id AND d.id=s.source_id
  JOIN campaign_private.world_qualifications q ON q.project_id=s.project_id AND q.id=s.qualification_id AND q.source_id=d.id
  WHERE b.project_id=s.project_id AND b.plan_id=s.plan_id
  AND marketing_runtime.paid_job_current(j.id,j.lease_token,p_plan)
  AND s.lease_sha256=encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex')
  AND jsonb_typeof(p.config->'trial')='number' AND (p.config->>'trial')::integer=s.repeat_index+1
  AND d.dataset_id=b.dataset_id AND d.case_id=b.case_id AND d.execution_sha256=b.execution_sha256
  AND d.case_snapshot_sha256=b.native_binding->'case_assignment'->>'snapshot_sha256'
  AND q.expires_at>clock_timestamp() AND q.receipt->>'definition_sha256'=d.definition_sha256
  AND q.receipt->>'source_sha256'=d.source_sha256
  AND q.receipt->>'runtime_sha256'=b.native_binding->>'runtime_sha256'
  AND q.receipt->>'rights_receipt_sha256'=d.definition->>'rights_receipt_sha256'
  AND q.receipt->>'dataset_qualification_sha256'=b.native_binding->'dataset_qualification'->>'receipt_sha256'
  AND NOT EXISTS(SELECT 1 FROM campaign_private.world_revocations r WHERE r.project_id=q.project_id AND r.qualification_id=q.id)
  AND q.id=(SELECT latest.id FROM campaign_private.world_qualifications latest
   WHERE latest.project_id=d.project_id AND latest.source_id=d.id AND latest.expires_at>clock_timestamp()
   AND NOT EXISTS(SELECT 1 FROM campaign_private.world_revocations r WHERE r.project_id=latest.project_id AND r.qualification_id=latest.id)
   ORDER BY latest.created_at DESC,latest.id DESC LIMIT 1));
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.world_session_current(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.world_session_current(uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_world_session(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s campaign_private.world_sessions;BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) OR NOT marketing_runtime.world_session_current(p_plan) THEN RETURN NULL;END IF;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE plan_id=p_plan AND project_id=nullif(current_setting('anvil.project',true),'')::uuid FOR UPDATE;
 IF NOT FOUND OR s.job_id<>p_job OR s.lease_sha256<>encode(sha256(convert_to(p_lease::text,'UTF8')),'hex') THEN RETURN NULL;END IF;
 RETURN to_jsonb(s);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_session(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_session(uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.create_private_world_session(
 p_job uuid,p_lease uuid,p_plan uuid,p_source uuid,p_qualification uuid,p_attachment text,p_state text,p_state_hash text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE b marketing_runtime.paid_agent_bindings;p anvil.harbor_agent_plans;d campaign_private.world_sources;
 q campaign_private.world_qualifications;a jsonb;v jsonb;stub jsonb;episode uuid;BEGIN
 IF NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) OR octet_length(p_attachment)>32768 OR octet_length(p_state)>16777216
 OR p_state_hash IS DISTINCT FROM encode(sha256(convert_to(p_state,'UTF8')),'hex') THEN RETURN false;END IF;
 SELECT * INTO b FROM marketing_runtime.paid_agent_bindings WHERE plan_id=p_plan FOR UPDATE;
 SELECT * INTO p FROM anvil.harbor_agent_plans WHERE project_id=b.project_id AND id=p_plan;
 SELECT * INTO d FROM campaign_private.world_sources WHERE project_id=b.project_id AND id=p_source FOR KEY SHARE;
 SELECT * INTO q FROM campaign_private.world_qualifications WHERE project_id=b.project_id AND id=p_qualification AND source_id=d.id;
 a=p_attachment::jsonb;v=p_state::jsonb;
 IF b.plan_id IS NULL OR d.id IS NULL OR q.id IS NULL OR q.expires_at<=clock_timestamp()
 OR d.dataset_id<>b.dataset_id OR d.case_id<>b.case_id OR d.execution_sha256<>b.execution_sha256
 OR EXISTS(SELECT 1 FROM campaign_private.world_revocations WHERE project_id=b.project_id AND qualification_id=q.id)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_episode_links WHERE plan_id=p_plan)
 OR EXISTS(SELECT 1 FROM campaign_private.world_sessions WHERE plan_id=p_plan)
 OR a->>'project_id' IS DISTINCT FROM b.project_id::text OR a->>'actor_id' IS DISTINCT FROM b.created_by::text
 OR a->>'job_id' IS DISTINCT FROM p_job::text OR a->>'plan_id' IS DISTINCT FROM p_plan::text
 OR a->>'execution_sha256' IS DISTINCT FROM b.execution_sha256
 OR a->>'generation' IS DISTINCT FROM '0' OR v->>'generation' IS DISTINCT FROM '0'
 OR a->>'episode_id' IS DISTINCT FROM v->>'trial_id' OR v->>'case_id' IS DISTINCT FROM b.case_id
 OR jsonb_typeof(p.config->'trial') IS DISTINCT FROM 'number' OR (p.config->>'trial')::integer NOT BETWEEN 1 AND 1000
 THEN RETURN false;END IF;
 episode=(a->>'episode_id')::uuid;
 stub=jsonb_build_object('schema_version','anvil.marketing-private-api-episode.v1','trial_id',episode,'generation',0,'state_owner','private_api');
 INSERT INTO marketing_runtime.episodes(id,project_id,assigned_user,case_id,dataset_id,dataset_version,dataset_sha256,snapshot_sha256,generation,state,state_sha256)
 VALUES(episode,b.project_id,b.created_by,b.case_id,b.native_binding->'case_context'->'caseDataset'->>'id',
 b.native_binding->'case_context'->'caseDataset'->>'version',b.native_binding->>'dataset_sha256',b.native_binding->'case_assignment'->>'snapshot_sha256',0,stub,encode(sha256(convert_to(stub::text,'UTF8')),'hex'));
 IF NOT marketing_runtime.bind_paid_agent_episode(p_job,p_lease,p_plan,episode,0,encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')) THEN RAISE EXCEPTION 'paid world episode binding denied';END IF;
 INSERT INTO campaign_private.world_sessions(project_id,plan_id,source_id,qualification_id,world_binding_id,world_binding_sha256,episode_id,generation,job_id,lease_sha256,repeat_index,attachment,controller_state,controller_state_sha256)
 VALUES(b.project_id,p_plan,d.id,q.id,(a->>'world_binding_id')::uuid,a->>'world_binding_sha256',episode,0,p_job,encode(sha256(convert_to(p_lease::text,'UTF8')),'hex'),(p.config->>'trial')::integer-1,a,v,p_state_hash);
 IF NOT marketing_runtime.world_session_current(p_plan) THEN RAISE EXCEPTION 'current world source qualification required';END IF;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.create_private_world_session(uuid,uuid,uuid,uuid,uuid,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.create_private_world_session(uuid,uuid,uuid,uuid,uuid,text,text,text) TO anvil_app;

-- Every candidate SDK claim also holds the current world source fence. Existing
-- semantic/candidate shared budgeting, lease/model/credential revocation and
-- once-only claim checks remain inside the preserved106 entry point.
ALTER FUNCTION marketing_runtime.claim_paid_call(uuid,uuid,uuid,bigint) RENAME TO claim_paid_candidate_before_world;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_candidate_before_world(uuid,uuid,uuid,bigint) FROM PUBLIC,anvil_app;
CREATE FUNCTION marketing_runtime.claim_paid_call(p_group uuid,p_plan uuid,p_call uuid,p_bound bigint)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 -- Keep the existing group-before-source lock order used by API admission.
 PERFORM 1 FROM anvil.workspace_execution_groups WHERE id=p_group AND project_id=nullif(current_setting('anvil.project',true),'')::uuid FOR UPDATE;
 IF NOT FOUND THEN RETURN false;END IF;
 IF NOT marketing_runtime.world_session_current(p_plan) THEN RETURN false;END IF;
 RETURN marketing_runtime.claim_paid_candidate_before_world(p_group,p_plan,p_call,p_bound);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_call(uuid,uuid,uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.claim_paid_call(uuid,uuid,uuid,bigint) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_world_tool_context(p_job uuid,p_lease uuid,p_plan uuid,p_request uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s jsonb;answer jsonb;BEGIN
 s=marketing_runtime.private_world_session(p_job,p_lease,p_plan);
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
REVOKE ALL ON FUNCTION marketing_runtime.private_world_tool_context(uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_tool_context(uuid,uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.commit_private_world_tool(
 p_job uuid,p_lease uuid,p_plan uuid,p_request uuid,p_before text,
 p_state text,p_state_hash text,p_result text,p_result_hash text,p_view text,p_view_hash text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE ctx jsonb;s jsonb;i jsonb;v jsonb;r jsonb;view_value jsonb;expected jsonb;used bigint;size integer;key text;BEGIN
 IF octet_length(p_state)>16777216 OR octet_length(p_result)>49152 OR octet_length(p_view)>16777216
 OR p_state_hash IS DISTINCT FROM encode(sha256(convert_to(p_state,'UTF8')),'hex')
 OR p_result_hash IS DISTINCT FROM encode(sha256(convert_to(p_result,'UTF8')),'hex')
 OR p_view_hash IS DISTINCT FROM encode(sha256(convert_to(p_view,'UTF8')),'hex') THEN RETURN false;END IF;
 ctx=marketing_runtime.private_world_tool_context(p_job,p_lease,p_plan,p_request);
 IF ctx IS NULL THEN RETURN false;END IF;
 s=ctx->'session';i=ctx->'intent';v=p_state::jsonb;r=p_result::jsonb;view_value=p_view::jsonb;
 IF s->>'controller_state_sha256' IS DISTINCT FROM p_before OR v->>'trial_id' IS DISTINCT FROM s->>'episode_id'
 OR v->>'generation' IS DISTINCT FROM s->>'generation' OR jsonb_typeof(r) IS DISTINCT FROM 'object' THEN RETURN false;END IF;
 FOREACH key IN ARRAY ARRAY['schema_version','profile','case_id','initial','start','outcome','budget_minor','generation','trial_id','role_tokens','controller_token','history'] LOOP
  IF v->key IS DISTINCT FROM s->'controller_state'->key THEN RETURN false;END IF;
 END LOOP;
 expected=jsonb_build_object('schema_version','anvil.marketing-tool-post-state.v1','clock',v->'clock','objects',v->'objects','budget_minor',v->'budget_minor',
 'committed',v->'committed','settled',v->'settled','reservations',v->'reservations','approvals',v->'approvals',
 'approval_bounds',v->'approval_bounds','revisions',v->'revisions','transitions',v->'transitions');
 IF view_value IS DISTINCT FROM expected THEN RETURN false;END IF;
 size=octet_length(view_value::text);
 SELECT coalesce(sum(byte_size),0) INTO used FROM campaign_private.tool_effect_states WHERE project_id=(s->>'project_id')::uuid;
 IF size>16777216 OR used+size>536870912 THEN RETURN false;END IF;
 INSERT INTO marketing_runtime.tool_receipts(id,project_id,episode_id,generation,role,operation,arguments_sha256,catalogue_sha256,source_refs_sha256,result,result_sha256,state_sha256)
 VALUES(p_request,(s->>'project_id')::uuid,(s->>'episode_id')::uuid,(s->>'generation')::integer,i->>'role',i->>'operation',i->>'arguments_sha256',
 s->'attachment'->>'execution_sha256',encode(sha256(convert_to('[]','UTF8')),'hex'),r,p_result_hash,p_state_hash);
 INSERT INTO campaign_private.tool_effect_states(project_id,request_id,episode_id,generation,full_state_sha256,post_state,post_state_sha256,byte_size)
 VALUES((s->>'project_id')::uuid,p_request,(s->>'episode_id')::uuid,(s->>'generation')::integer,p_state_hash,view_value,p_view_hash,size);
 UPDATE campaign_private.world_sessions SET controller_state=v,controller_state_sha256=p_state_hash WHERE plan_id=p_plan;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.commit_private_world_tool(uuid,uuid,uuid,uuid,text,text,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.commit_private_world_tool(uuid,uuid,uuid,uuid,text,text,text,text,text,text,text) TO anvil_app;

-- Serial quota guards cover old and new writers; preflight sizing alone is not
-- a concurrent capacity fence. Shared source bodies and per-plan mutable state
-- have separate explicit512MiB project ceilings, with no historical deletion.
CREATE FUNCTION campaign_private.world_quota_guard() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE used bigint;size bigint;BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_quota:'||TG_TABLE_NAME||':'||NEW.project_id::text,0));
 IF TG_TABLE_NAME='world_sources' THEN
  SELECT coalesce(sum(octet_length(definition::text)),0) INTO used FROM campaign_private.world_sources WHERE project_id=NEW.project_id;
  size=octet_length(NEW.definition::text);
 ELSIF TG_TABLE_NAME='world_sessions' THEN
  SELECT coalesce(sum(octet_length(controller_state::text)),0) INTO used FROM campaign_private.world_sessions WHERE project_id=NEW.project_id AND plan_id<>NEW.plan_id;
  size=octet_length(NEW.controller_state::text);
 ELSE
  SELECT coalesce(sum(byte_size),0) INTO used FROM campaign_private.tool_effect_states WHERE project_id=NEW.project_id;
  size=NEW.byte_size;
 END IF;
 IF used+size>536870912 THEN RAISE EXCEPTION 'private Marketing project quota exhausted';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER quota_guard BEFORE INSERT ON campaign_private.world_sources
 FOR EACH ROW EXECUTE FUNCTION campaign_private.world_quota_guard();
CREATE TRIGGER quota_guard BEFORE INSERT OR UPDATE ON campaign_private.world_sessions
 FOR EACH ROW EXECUTE FUNCTION campaign_private.world_quota_guard();
CREATE TRIGGER quota_guard BEFORE INSERT ON campaign_private.tool_effect_states
 FOR EACH ROW EXECUTE FUNCTION campaign_private.world_quota_guard();

-- Preserve legacy software fixtures while denying coordinator writes to actual
-- API-owned paid episode state, tool receipts and seals. Readable paid episode
-- rows contain only the public stub; private state remains in world_sessions.
CREATE FUNCTION marketing_runtime.private_api_episode(p_project uuid,p_episode uuid)
 RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM campaign_private.world_sessions s WHERE s.project_id=p_project AND s.episode_id=p_episode);
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_api_episode(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_api_episode(uuid,uuid) TO anvil_golden_scheduler;
CREATE POLICY api_world_update ON marketing_runtime.episodes AS RESTRICTIVE FOR UPDATE TO anvil_golden_scheduler
 USING(NOT marketing_runtime.private_api_episode(project_id,id))
 WITH CHECK(NOT marketing_runtime.private_api_episode(project_id,id));
CREATE POLICY api_world_tool_insert ON marketing_runtime.tool_receipts AS RESTRICTIVE FOR INSERT TO anvil_golden_scheduler
 WITH CHECK(NOT marketing_runtime.private_api_episode(project_id,episode_id));
CREATE POLICY api_world_seal_insert ON marketing_runtime.seals AS RESTRICTIVE FOR INSERT TO anvil_golden_scheduler
 WITH CHECK(NOT marketing_runtime.private_api_episode(project_id,episode_id));

CREATE FUNCTION marketing_runtime.private_world_runtime_receipt(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('source',jsonb_build_object(
  'id',d.id,'definition_sha256',d.definition_sha256,'source_sha256',d.source_sha256,
  'case_id',d.case_id,'case_snapshot_sha256',d.case_snapshot_sha256,'execution_sha256',d.execution_sha256,
  'rights_receipt_sha256',d.definition->>'rights_receipt_sha256'),'qualification',to_jsonb(q))
 FROM campaign_private.world_sessions s
 JOIN campaign_private.world_sources d ON d.project_id=s.project_id AND d.id=s.source_id
 JOIN campaign_private.world_qualifications q ON q.project_id=s.project_id AND q.id=s.qualification_id
 WHERE s.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND s.plan_id=p_plan AND s.job_id=p_job
 AND s.lease_sha256=encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
 AND marketing_runtime.paid_job_current(p_job,p_lease,p_plan) AND marketing_runtime.world_session_current(p_plan);
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_runtime_receipt(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_runtime_receipt(uuid,uuid,uuid) TO anvil_app;

CREATE TABLE campaign_private.world_releases(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,week integer NOT NULL CHECK(week BETWEEN 1 AND 12),
 reply jsonb NOT NULL CHECK(octet_length(reply::text)<=65536),
 reply_sha256 text NOT NULL CHECK(reply_sha256~'^[a-f0-9]{64}$'),
 inventory jsonb NOT NULL CHECK(octet_length(inventory::text)<=65536),
 post_state_sha256 text NOT NULL CHECK(post_state_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(plan_id,week),
 FOREIGN KEY(project_id,plan_id) REFERENCES campaign_private.world_sessions(project_id,plan_id));
ALTER TABLE campaign_private.world_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.world_releases FORCE ROW LEVEL SECURITY;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.world_releases
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE FUNCTION marketing_runtime.private_world_graph_records(p_job uuid,p_lease uuid,p_plan uuid)
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
 RETURN jsonb_build_object('attachment',s->'attachment','releases',releases,'effects',effects,'turns',turns);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_world_graph_records(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_world_graph_records(uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.commit_private_world_release(
 p_job uuid,p_lease uuid,p_plan uuid,p_before text,p_week integer,p_state text,p_state_hash text,p_reply text,p_reply_hash text,p_inventory text
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s jsonb;v jsonb;r jsonb;inventory_value jsonb;key text;BEGIN
 IF p_week NOT BETWEEN 1 AND 12 OR octet_length(p_state)>16777216 OR octet_length(p_reply)>65536 OR octet_length(p_inventory)>65536
 OR p_state_hash IS DISTINCT FROM encode(sha256(convert_to(p_state,'UTF8')),'hex')
 OR p_reply_hash IS DISTINCT FROM encode(sha256(convert_to(p_reply,'UTF8')),'hex') THEN RETURN false;END IF;
 s=marketing_runtime.private_world_session(p_job,p_lease,p_plan);
 IF s IS NULL OR s->>'controller_state_sha256' IS DISTINCT FROM p_before OR (s->>'last_week')::integer<>p_week-1 THEN RETURN false;END IF;
 v=p_state::jsonb;r=p_reply::jsonb;inventory_value=p_inventory::jsonb;
 IF jsonb_typeof(inventory_value) IS DISTINCT FROM 'array' OR jsonb_array_length(inventory_value)>50 THEN RETURN false;END IF;
 FOREACH key IN ARRAY ARRAY['schema_version','profile','case_id','initial','start','outcome','budget_minor','generation','trial_id','role_tokens','controller_token','objects','role_idempotency','approval_bounds','approvals','reservations','committed','settled','revisions','history'] LOOP
  IF v->key IS DISTINCT FROM s->'controller_state'->key THEN RETURN false;END IF;
 END LOOP;
 IF (v->>'clock')::timestamptz<(s->'controller_state'->>'clock')::timestamptz
 OR r->>'world_binding_id' IS DISTINCT FROM s->>'world_binding_id' OR r->>'world_binding_sha256' IS DISTINCT FROM s->>'world_binding_sha256'
 OR r->>'episode_id' IS DISTINCT FROM s->>'episode_id' OR r->>'generation' IS DISTINCT FROM s->>'generation'
 OR r->>'week' IS DISTINCT FROM p_week::text OR r->>'case_id' IS DISTINCT FROM s->'attachment'->>'case_id'
 OR r->>'case_snapshot_sha256' IS DISTINCT FROM s->'attachment'->>'case_snapshot_sha256'
 OR (r->>'released_at')::timestamptz IS DISTINCT FROM (v->>'clock')::timestamptz THEN RETURN false;END IF;
 INSERT INTO campaign_private.world_releases(project_id,plan_id,week,reply,reply_sha256,inventory,post_state_sha256)
 VALUES((s->>'project_id')::uuid,p_plan,p_week,r,p_reply_hash,inventory_value,p_state_hash);
 UPDATE campaign_private.world_sessions SET controller_state=v,controller_state_sha256=p_state_hash,last_week=p_week WHERE plan_id=p_plan;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.commit_private_world_release(uuid,uuid,uuid,text,integer,text,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.commit_private_world_release(uuid,uuid,uuid,text,integer,text,text,text,text,text) TO anvil_app;
