-- UNEXECUTED SOURCE: API custody only, never physical capture/finish acceptance.
CREATE OR REPLACE FUNCTION marketing_runtime.world_stop_context(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
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
 RETURN jsonb_build_object('session',to_jsonb(s)-'controller_state','graph_records',records,
 'graph_ledger_sha256',encode(sha256(convert_to(records::text,'UTF8')),'hex'),'pending',pending,
 'source_qualification_sha256',(SELECT receipt_sha256 FROM campaign_private.world_qualifications WHERE project_id=project AND id=s.qualification_id),
 'observed_at',clock_timestamp(),
 'execution',(SELECT execution FROM marketing_runtime.paid_agent_bindings WHERE project_id=project AND plan_id=p_plan),
 'fence',(SELECT to_jsonb(f) FROM campaign_private.world_fences f WHERE f.project_id=project AND f.plan_id=p_plan),
 'quiescence',(SELECT to_jsonb(q) FROM campaign_private.world_quiescence_receipts q WHERE q.project_id=project AND q.plan_id=p_plan));
END $$;
CREATE OR REPLACE FUNCTION marketing_runtime.capture_attestation_key(p_id uuid)
 RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT jsonb_build_object('enrollment_id',e.id,'request_sha256',e.request_sha256,'operation_nonce',e.operation_nonce,
 'boot_id',e.attester_boot_id,'profile_sha256',e.attester_profile_sha256,'producer_qualification_sha256',q.qualification_sha256,
 'public_key_hex',e.attestation_public_key_hex,'expires_at',e.expires_at,'document_limits',e.document_limits,
 'body_schema',e.body_schema,'wire_limit',e.wire_limit,'scope',e.scope,'status_transport',q.qualification_canonical::jsonb->'status_transport')
 FROM campaign_private.capture_enrollments e JOIN campaign_private.capture_channel_qualifications q
 ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 WHERE e.id=p_id AND q.auth_kind='operator_attested_root_peer_v1' AND q.subject=e.attester_profile_sha256
 AND e.attestation_public_key_hex IS NOT NULL AND e.attester_boot_id IS NOT NULL
 AND marketing_runtime.capture_enrollment_scope(e.id,q.auth_kind,q.subject,NULL) IS NOT NULL;
$$;
CREATE TABLE campaign_private.capture_evidence_slots(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),project_id uuid NOT NULL,enrollment_id uuid NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,enrollment_id) REFERENCES campaign_private.capture_enrollments(project_id,id),UNIQUE(project_id,id));
CREATE TABLE campaign_private.capture_actor_prompts(
 project_id uuid NOT NULL,plan_id uuid NOT NULL,stage_index integer NOT NULL,manifest_id uuid NOT NULL,
 prompt_utf8 text NOT NULL CHECK(octet_length(prompt_utf8) BETWEEN 1 AND 32768),
 prompt_sha256 text NOT NULL CHECK(prompt_sha256=encode(sha256(convert_to(prompt_utf8,'UTF8')),'hex')),
 byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 32768),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(plan_id,stage_index),FOREIGN KEY(project_id,plan_id,stage_index) REFERENCES marketing_runtime.paid_turn_intents(project_id,plan_id,stage_index),
 FOREIGN KEY(project_id,manifest_id) REFERENCES campaign_private.capture_evidence_slots(project_id,id));
CREATE TABLE campaign_private.capture_evidence_intents(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,manifest_id uuid NOT NULL UNIQUE,
 original_context jsonb NOT NULL CHECK(octet_length(original_context::text)<=16384),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,manifest_id) REFERENCES campaign_private.capture_evidence_slots(project_id,id),UNIQUE(project_id,id));
CREATE TABLE campaign_private.capture_evidence_snapshots(
 project_id uuid NOT NULL,manifest_id uuid NOT NULL,category text NOT NULL CHECK(category IN('sdk_calls','final_world_state')),
 source_id text NOT NULL CHECK(length(source_id) BETWEEN 1 AND 200),
 canonical_body text NOT NULL CHECK(octet_length(canonical_body) BETWEEN 1 AND 16777216),
 body_sha256 text NOT NULL CHECK(body_sha256=encode(sha256(convert_to(canonical_body,'UTF8')),'hex')),
 byte_size integer NOT NULL CHECK(byte_size=octet_length(canonical_body)),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(manifest_id,category,source_id),FOREIGN KEY(project_id,manifest_id) REFERENCES campaign_private.capture_evidence_slots(project_id,id));
CREATE TABLE campaign_private.capture_evidence_manifests(
 project_id uuid NOT NULL,manifest_id uuid PRIMARY KEY,intent_id uuid NOT NULL UNIQUE,
 canonical_body text NOT NULL CHECK(octet_length(canonical_body) BETWEEN 1 AND 16777216),
 body_sha256 text NOT NULL CHECK(body_sha256=encode(sha256(convert_to(canonical_body,'UTF8')),'hex')),
 ready_descriptor jsonb NOT NULL CHECK(octet_length(ready_descriptor::text)<=4096),
 byte_size integer NOT NULL CHECK(byte_size=octet_length(canonical_body)+octet_length(ready_descriptor::text)),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,manifest_id) REFERENCES campaign_private.capture_evidence_slots(project_id,id),
 FOREIGN KEY(project_id,intent_id) REFERENCES campaign_private.capture_evidence_intents(project_id,id));
DO $$DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['capture_evidence_slots','capture_actor_prompts','capture_evidence_intents','capture_evidence_snapshots','capture_evidence_manifests'] LOOP
  EXECUTE format('ALTER TABLE campaign_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE campaign_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON campaign_private.%I FROM PUBLIC,anvil_app,anvil_golden_scheduler,anvil_golden_grader',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;

CREATE FUNCTION campaign_private.capture_evidence_quota() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE used bigint;amount bigint;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.capture_combined_quota:'||NEW.project_id::text,0));
 SELECT coalesce(sum(byte_size),0) INTO used FROM (
  SELECT byte_size FROM campaign_private.capture_raw_intakes WHERE project_id=NEW.project_id
  UNION ALL SELECT byte_size FROM campaign_private.capture_actor_prompts WHERE project_id=NEW.project_id
  UNION ALL SELECT byte_size FROM campaign_private.capture_evidence_snapshots WHERE project_id=NEW.project_id
  UNION ALL SELECT byte_size FROM campaign_private.capture_evidence_manifests WHERE project_id=NEW.project_id
 ) records;
 amount=NEW.byte_size;
 IF used+amount>536870912 THEN RAISE EXCEPTION 'original private capture quota exhausted';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION campaign_private.capture_evidence_quota() FROM PUBLIC;
CREATE TRIGGER evidence_quota BEFORE INSERT ON campaign_private.capture_raw_intakes FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_evidence_quota();
CREATE TRIGGER evidence_quota BEFORE INSERT ON campaign_private.capture_actor_prompts FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_evidence_quota();
CREATE TRIGGER evidence_quota BEFORE INSERT ON campaign_private.capture_evidence_snapshots FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_evidence_quota();
CREATE TRIGGER evidence_quota BEFORE INSERT ON campaign_private.capture_evidence_manifests FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_evidence_quota();

CREATE FUNCTION campaign_private.reserve_capture_evidence_slot() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
BEGIN
 IF NEW.body_schema='anvil.marketing-native-capture-submission.v2' THEN
  INSERT INTO campaign_private.capture_evidence_slots(project_id,enrollment_id) VALUES(NEW.project_id,NEW.id);
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION campaign_private.reserve_capture_evidence_slot() FROM PUBLIC;
CREATE TRIGGER reserve_api_slot AFTER INSERT ON campaign_private.capture_enrollments
 FOR EACH ROW EXECUTE FUNCTION campaign_private.reserve_capture_evidence_slot();
-- No backfill: old enrollments/attempts are never silently repinned or retried.

CREATE FUNCTION marketing_runtime.capture_manifest_preflight(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE ctx jsonb;slot campaign_private.capture_evidence_slots;
 e campaign_private.capture_enrollments;q campaign_private.capture_channel_qualifications;BEGIN
 ctx=marketing_runtime.capture_plan_preflight(p_job,p_lease,p_plan);
 IF ctx IS NULL OR ctx->>'body_schema'<>'anvil.marketing-native-capture-submission.v2' THEN RETURN NULL;END IF;
 SELECT * INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=(ctx->>'project_id')::uuid
 AND enrollment_id=(ctx->>'enrollment_id')::uuid;
 IF NOT FOUND OR EXISTS(SELECT 1 FROM campaign_private.capture_evidence_intents WHERE project_id=slot.project_id AND manifest_id=slot.id)
 THEN RETURN NULL;END IF;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=slot.project_id AND id=slot.enrollment_id;
 SELECT * INTO q FROM campaign_private.capture_channel_qualifications WHERE project_id=slot.project_id AND id=e.channel_qualification_id;
 RETURN ctx||jsonb_build_object('manifest_id',slot.id,'content_state','reserved_no_content',
 'expires_at',e.expires_at,'status_transport',q.qualification_canonical::jsonb->'status_transport');
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_manifest_preflight(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_manifest_preflight(uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.retain_capture_actor_prompt(p_plan uuid,p_stage integer,p_prompt text,p_hash text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 t marketing_runtime.paid_turn_intents;j anvil.jobs;ctx jsonb;existing campaign_private.capture_actor_prompts;
BEGIN
 IF p_prompt IS NULL OR octet_length(p_prompt) NOT BETWEEN 1 AND 32768
 OR p_hash IS DISTINCT FROM encode(sha256(convert_to(p_prompt,'UTF8')),'hex') THEN RETURN false;END IF;
 SELECT * INTO t FROM marketing_runtime.paid_turn_intents WHERE project_id=project AND plan_id=p_plan AND stage_index=p_stage;
 IF NOT FOUND THEN RETURN false;END IF;
 SELECT * INTO j FROM anvil.jobs WHERE project_id=project AND id=t.job_id;
 IF NOT FOUND OR j.lease_token IS NULL OR encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex')<>t.lease_sha256 THEN RETURN false;END IF;
 ctx=marketing_runtime.capture_manifest_preflight(j.id,j.lease_token,p_plan);
 IF ctx IS NULL THEN RETURN false;END IF;
 SELECT * INTO existing FROM campaign_private.capture_actor_prompts WHERE project_id=project AND plan_id=p_plan AND stage_index=p_stage;
 IF FOUND THEN RETURN existing.prompt_utf8=p_prompt AND existing.prompt_sha256=p_hash AND existing.manifest_id=(ctx->>'manifest_id')::uuid;END IF;
 INSERT INTO campaign_private.capture_actor_prompts(project_id,plan_id,stage_index,manifest_id,prompt_utf8,prompt_sha256,byte_size)
 VALUES(project,p_plan,p_stage,(ctx->>'manifest_id')::uuid,p_prompt,p_hash,octet_length(p_prompt));
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.retain_capture_actor_prompt(uuid,integer,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.retain_capture_actor_prompt(uuid,integer,text,text) TO anvil_app;

CREATE FUNCTION campaign_private.capture_prompt_before_dispatch() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM anvil.harbor_agent_plans p WHERE p.project_id=NEW.project_id AND p.id=NEW.plan_id AND p.config->>'marketing_paid'='true')
 AND NOT EXISTS(SELECT 1 FROM campaign_private.capture_actor_prompts r WHERE r.project_id=NEW.project_id
  AND r.plan_id=NEW.plan_id AND r.stage_index=NEW.stage_index AND r.prompt_sha256=NEW.request_sha256) THEN
  RAISE EXCEPTION 'exact actor prompt must be retained before Marketing SDK dispatch';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION campaign_private.capture_prompt_before_dispatch() FROM PUBLIC;
CREATE TRIGGER capture_prompt BEFORE INSERT ON anvil.harbor_agent_calls
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_prompt_before_dispatch();

CREATE FUNCTION marketing_runtime.capture_dispatch_prompt(p_plan uuid,p_stage integer,p_call uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 t marketing_runtime.paid_turn_intents;j anvil.jobs;ctx jsonb;
BEGIN
 SELECT * INTO t FROM marketing_runtime.paid_turn_intents WHERE project_id=project AND plan_id=p_plan AND stage_index=p_stage;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT * INTO j FROM anvil.jobs WHERE project_id=project AND id=t.job_id;
 IF NOT FOUND OR j.lease_token IS NULL THEN RETURN NULL;END IF;
 ctx=marketing_runtime.capture_manifest_preflight(j.id,j.lease_token,p_plan);
 IF ctx IS NULL THEN RETURN NULL;END IF;
 RETURN (SELECT jsonb_build_object('plan_id',r.plan_id,'stage_index',r.stage_index,'call_id',c.id,
 'prompt_utf8',r.prompt_utf8,'prompt_sha256',r.prompt_sha256,'request_sha256',c.request_sha256,
 'dispatch_before_utc',(ctx->>'expires_at')::timestamptz-((ctx->'status_transport'->>'cleanup_reserve_seconds')||' seconds')::interval)
 FROM campaign_private.capture_actor_prompts r JOIN anvil.harbor_agent_calls c
 ON c.project_id=r.project_id AND c.plan_id=r.plan_id AND c.stage_index=r.stage_index
 WHERE r.project_id=project AND r.plan_id=p_plan AND r.stage_index=p_stage AND c.id=p_call
 AND c.status='dispatching' AND r.manifest_id=(ctx->>'manifest_id')::uuid AND r.prompt_sha256=c.request_sha256);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_dispatch_prompt(uuid,integer,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_dispatch_prompt(uuid,integer,uuid) TO anvil_app;


-- Private fixed projection, not a caller-selected table/path query.
CREATE FUNCTION campaign_private.capture_evidence_rows(p_project uuid,p_enrollment uuid)
 RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE e campaign_private.capture_enrollments;s campaign_private.world_sessions;
 d campaign_private.world_sources;ch campaign_private.capture_channel_qualifications;slot campaign_private.capture_evidence_slots;
BEGIN
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=p_project AND id=p_enrollment;
 IF NOT FOUND THEN RETURN;END IF;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=p_project AND plan_id=e.plan_id AND job_id=e.job_id;
 IF NOT FOUND THEN RETURN;END IF;
 SELECT * INTO d FROM campaign_private.world_sources WHERE project_id=p_project AND id=s.source_id;
 SELECT * INTO ch FROM campaign_private.capture_channel_qualifications WHERE project_id=p_project AND id=e.channel_qualification_id;
 SELECT * INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=p_project AND enrollment_id=e.id;
 RETURN QUERY SELECT jsonb_build_object('category','world_source','source_id',v.id::text,'body',to_jsonb(v)) FROM campaign_private.world_sources v WHERE v.project_id=p_project AND v.id=s.source_id;
 RETURN QUERY SELECT jsonb_build_object('category','world_qualification','source_id',v.id::text,'body',to_jsonb(v)) FROM campaign_private.world_qualifications v WHERE v.project_id=p_project AND v.id=s.qualification_id;
 RETURN QUERY SELECT jsonb_build_object('category','dataset','source_id',v.id::text,'body',to_jsonb(v)) FROM anvil.campaign_dataset_versions v WHERE v.project_id=p_project AND v.id=d.dataset_id;
 RETURN QUERY SELECT jsonb_build_object('category','runtime_allowlist','source_id',v.id::text,'body',to_jsonb(v)) FROM anvil.runtime_role_allowlist v WHERE v.project_id=p_project AND v.id=ch.runtime_allowlist_id;
 RETURN QUERY SELECT jsonb_build_object('category','channel_qualification','source_id',v.id::text,'body',to_jsonb(v)) FROM campaign_private.capture_channel_qualifications v WHERE v.project_id=p_project AND v.id=e.channel_qualification_id;
 RETURN QUERY SELECT jsonb_build_object('category','capture_enrollment','source_id',v.id::text,'body',to_jsonb(v)) FROM campaign_private.capture_enrollments v WHERE v.project_id=p_project AND v.id=e.id;
 RETURN QUERY SELECT jsonb_build_object('category','agent_binding','source_id',v.plan_id::text,'body',to_jsonb(v)) FROM marketing_runtime.paid_agent_bindings v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','world_releases','source_id',v.week::text,'body',to_jsonb(v)) FROM campaign_private.world_releases v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','workflow_effects','source_id',v.id::text,'body',to_jsonb(v)) FROM marketing_runtime.workflow_effects v WHERE v.project_id=p_project AND v.episode_id=s.episode_id AND v.generation=s.generation AND v.execution_sha256=s.attachment->>'execution_sha256';
 RETURN QUERY SELECT jsonb_build_object('category','turn_intents','source_id',v.stage_index::text,'body',to_jsonb(v)) FROM marketing_runtime.paid_turn_intents v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','turn_observations','source_id',v.stage_index::text,'body',to_jsonb(v)) FROM marketing_runtime.paid_turn_observations v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','sdk_calls','source_id',v.id::text,'body',to_jsonb(v)) FROM anvil.harbor_agent_calls v WHERE v.project_id=p_project AND v.plan_id=e.plan_id FOR SHARE OF v;
 RETURN QUERY SELECT jsonb_build_object('category','sdk_prompts','source_id',v.stage_index::text,'body',to_jsonb(v)) FROM campaign_private.capture_actor_prompts v WHERE v.project_id=p_project AND v.plan_id=e.plan_id AND v.manifest_id=slot.id;
 RETURN QUERY SELECT jsonb_build_object('category','tool_intents','source_id',v.request_id::text,'body',to_jsonb(v)) FROM marketing_runtime.paid_tool_action_intents v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','tool_receipts','source_id',v.id::text,'body',to_jsonb(v)) FROM marketing_runtime.tool_receipts v WHERE v.project_id=p_project AND v.episode_id=s.episode_id AND v.generation=s.generation;
 RETURN QUERY SELECT jsonb_build_object('category','tool_states','source_id',v.request_id::text,'body',to_jsonb(v)) FROM campaign_private.tool_effect_states v WHERE v.project_id=p_project AND v.episode_id=s.episode_id AND v.generation=s.generation;
 RETURN QUERY SELECT jsonb_build_object('category','service_effects','source_id',v.effect_id::text,'body',to_jsonb(v)) FROM campaign_private.world_service_effects v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','campaign_states','source_id',v.effect_id::text,'body',to_jsonb(v)) FROM campaign_private.world_campaign_effect_states v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','fence','source_id',v.fence_id::text,'body',to_jsonb(v)) FROM campaign_private.world_fences v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','quiescence','source_id',v.receipt->>'quiescence_id','body',to_jsonb(v)) FROM campaign_private.world_quiescence_receipts v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN NEXT jsonb_build_object('category','world_attachment','source_id',s.world_binding_id::text,'body',s.attachment);
 RETURN NEXT jsonb_build_object('category','final_world_state','source_id',s.plan_id::text,'body',s.controller_state);
END $$;
REVOKE ALL ON FUNCTION campaign_private.capture_evidence_rows(uuid,uuid) FROM PUBLIC,anvil_app,anvil_golden_scheduler,anvil_golden_grader;

CREATE FUNCTION campaign_private.capture_evidence_identities(p_project uuid,p_enrollment uuid)
 RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE e campaign_private.capture_enrollments;s campaign_private.world_sessions;
 d campaign_private.world_sources;ch campaign_private.capture_channel_qualifications;slot campaign_private.capture_evidence_slots;
BEGIN
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=p_project AND id=p_enrollment;
 IF NOT FOUND THEN RETURN;END IF;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=p_project AND plan_id=e.plan_id AND job_id=e.job_id;
 IF NOT FOUND THEN RETURN;END IF;
 SELECT * INTO d FROM campaign_private.world_sources WHERE project_id=p_project AND id=s.source_id;
 SELECT * INTO ch FROM campaign_private.capture_channel_qualifications WHERE project_id=p_project AND id=e.channel_qualification_id;
 SELECT * INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=p_project AND enrollment_id=e.id;
 RETURN QUERY SELECT jsonb_build_object('category','world_source','source_id',v.id::text) FROM campaign_private.world_sources v WHERE v.project_id=p_project AND v.id=s.source_id;
 RETURN QUERY SELECT jsonb_build_object('category','world_qualification','source_id',v.id::text) FROM campaign_private.world_qualifications v WHERE v.project_id=p_project AND v.id=s.qualification_id;
 RETURN QUERY SELECT jsonb_build_object('category','dataset','source_id',v.id::text) FROM anvil.campaign_dataset_versions v WHERE v.project_id=p_project AND v.id=d.dataset_id;
 RETURN QUERY SELECT jsonb_build_object('category','runtime_allowlist','source_id',v.id::text) FROM anvil.runtime_role_allowlist v WHERE v.project_id=p_project AND v.id=ch.runtime_allowlist_id;
 RETURN QUERY SELECT jsonb_build_object('category','channel_qualification','source_id',v.id::text) FROM campaign_private.capture_channel_qualifications v WHERE v.project_id=p_project AND v.id=e.channel_qualification_id;
 RETURN QUERY SELECT jsonb_build_object('category','capture_enrollment','source_id',v.id::text) FROM campaign_private.capture_enrollments v WHERE v.project_id=p_project AND v.id=e.id;
 RETURN QUERY SELECT jsonb_build_object('category','agent_binding','source_id',v.plan_id::text) FROM marketing_runtime.paid_agent_bindings v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','world_releases','source_id',v.week::text) FROM campaign_private.world_releases v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','workflow_effects','source_id',v.id::text) FROM marketing_runtime.workflow_effects v WHERE v.project_id=p_project AND v.episode_id=s.episode_id AND v.generation=s.generation AND v.execution_sha256=s.attachment->>'execution_sha256';
 RETURN QUERY SELECT jsonb_build_object('category','turn_intents','source_id',v.stage_index::text) FROM marketing_runtime.paid_turn_intents v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','turn_observations','source_id',v.stage_index::text) FROM marketing_runtime.paid_turn_observations v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','sdk_calls','source_id',v.id::text) FROM anvil.harbor_agent_calls v WHERE v.project_id=p_project AND v.plan_id=e.plan_id FOR SHARE OF v;
 RETURN QUERY SELECT jsonb_build_object('category','sdk_prompts','source_id',v.stage_index::text) FROM campaign_private.capture_actor_prompts v WHERE v.project_id=p_project AND v.plan_id=e.plan_id AND v.manifest_id=slot.id;
 RETURN QUERY SELECT jsonb_build_object('category','tool_intents','source_id',v.request_id::text) FROM marketing_runtime.paid_tool_action_intents v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','tool_receipts','source_id',v.id::text) FROM marketing_runtime.tool_receipts v WHERE v.project_id=p_project AND v.episode_id=s.episode_id AND v.generation=s.generation;
 RETURN QUERY SELECT jsonb_build_object('category','tool_states','source_id',v.request_id::text) FROM campaign_private.tool_effect_states v WHERE v.project_id=p_project AND v.episode_id=s.episode_id AND v.generation=s.generation;
 RETURN QUERY SELECT jsonb_build_object('category','service_effects','source_id',v.effect_id::text) FROM campaign_private.world_service_effects v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','campaign_states','source_id',v.effect_id::text) FROM campaign_private.world_campaign_effect_states v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','fence','source_id',v.fence_id::text) FROM campaign_private.world_fences v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN QUERY SELECT jsonb_build_object('category','quiescence','source_id',v.receipt->>'quiescence_id') FROM campaign_private.world_quiescence_receipts v WHERE v.project_id=p_project AND v.plan_id=e.plan_id;
 RETURN NEXT jsonb_build_object('category','world_attachment','source_id',s.world_binding_id::text);
 RETURN NEXT jsonb_build_object('category','final_world_state','source_id',s.plan_id::text);
END $$;
REVOKE ALL ON FUNCTION campaign_private.capture_evidence_identities(uuid,uuid) FROM PUBLIC,anvil_app,anvil_golden_scheduler,anvil_golden_grader;

CREATE FUNCTION campaign_private.capture_evidence_context(p_job uuid,p_lease uuid,p_plan uuid,p_enrollment uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 e campaign_private.capture_enrollments;s campaign_private.world_sessions;
 d campaign_private.world_sources;ch campaign_private.capture_channel_qualifications;slot campaign_private.capture_evidence_slots;
 ctx jsonb;q jsonb;scope_value jsonb;counts jsonb;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN NULL;END IF;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_enrollment;
 IF NOT FOUND OR e.job_id<>p_job OR e.plan_id<>p_plan OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true)
 OR e.body_schema<>'anvil.marketing-native-capture-submission.v2' THEN RETURN NULL;END IF;
 SELECT * INTO ch FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=e.channel_qualification_id;
 IF NOT FOUND OR marketing_runtime.capture_enrollment_scope(e.id,ch.auth_kind,ch.subject,ch.account_email) IS NULL THEN RETURN NULL;END IF;
 ctx=marketing_runtime.world_stop_context(p_job,p_lease,p_plan);
 IF ctx IS NULL OR ctx->'quiescence' IS NULL OR ctx->'quiescence'='null'::jsonb
 OR ctx->'pending'<>'{"sdk_dispatching":0,"sdk_unknown":0,"tool_pending":0,"workflow_pending":0,"workflow_unknown":0}'::jsonb
 OR NOT marketing_runtime.world_session_before_quiescence(p_plan) THEN RETURN NULL;END IF;
 q=ctx->'quiescence'->'receipt';
 IF q->>'graph_ledger_sha256' IS DISTINCT FROM ctx->>'graph_ledger_sha256' THEN RETURN NULL;END IF;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=project AND plan_id=p_plan;
 SELECT * INTO d FROM campaign_private.world_sources WHERE project_id=project AND id=s.source_id;
 SELECT * INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=project AND enrollment_id=e.id;
 IF slot.id IS NULL OR d.definition->>'schema_version'<>'anvil.marketing-private-world-definition.v6'
 OR clock_timestamp()>=e.expires_at-((ch.qualification_canonical::jsonb->'status_transport'->>'cleanup_reserve_seconds')||' seconds')::interval
 OR ch.qualification_canonical::jsonb->'status_transport'->>'cleanup_reserve_seconds' IS NULL THEN RETURN NULL;END IF;
 scope_value=jsonb_build_object('project_id',s.project_id,'job_id',s.job_id,'plan_id',s.plan_id,
 'world_binding_id',s.world_binding_id,'world_binding_sha256',s.world_binding_sha256,'episode_id',s.episode_id,'generation',s.generation,
 'lease_sha256',s.lease_sha256,'source_qualification_sha256',ctx->>'source_qualification_sha256','execution_sha256',s.attachment->>'execution_sha256');
 IF e.scope IS DISTINCT FROM scope_value THEN RETURN NULL;END IF;
 counts=jsonb_build_object(
 'world_source',(SELECT count(*) FROM campaign_private.world_sources v WHERE v.project_id=project AND v.id=s.source_id),
 'world_qualification',(SELECT count(*) FROM campaign_private.world_qualifications v WHERE v.project_id=project AND v.id=s.qualification_id),
 'dataset',(SELECT count(*) FROM anvil.campaign_dataset_versions v WHERE v.project_id=project AND v.id=d.dataset_id),
 'runtime_allowlist',(SELECT count(*) FROM anvil.runtime_role_allowlist v WHERE v.project_id=project AND v.id=ch.runtime_allowlist_id),
 'channel_qualification',(SELECT count(*) FROM campaign_private.capture_channel_qualifications v WHERE v.project_id=project AND v.id=e.channel_qualification_id),
 'capture_enrollment',(SELECT count(*) FROM campaign_private.capture_enrollments v WHERE v.project_id=project AND v.id=e.id),
 'agent_binding',(SELECT count(*) FROM marketing_runtime.paid_agent_bindings v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'world_releases',(SELECT count(*) FROM campaign_private.world_releases v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'workflow_effects',(SELECT count(*) FROM marketing_runtime.workflow_effects v WHERE v.project_id=project AND v.episode_id=s.episode_id AND v.generation=s.generation AND v.execution_sha256=s.attachment->>'execution_sha256'),
 'turn_intents',(SELECT count(*) FROM marketing_runtime.paid_turn_intents v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'turn_observations',(SELECT count(*) FROM marketing_runtime.paid_turn_observations v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'sdk_calls',(SELECT count(*) FROM anvil.harbor_agent_calls v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'sdk_prompts',(SELECT count(*) FROM campaign_private.capture_actor_prompts v WHERE v.project_id=project AND v.plan_id=e.plan_id AND v.manifest_id=slot.id),
 'tool_intents',(SELECT count(*) FROM marketing_runtime.paid_tool_action_intents v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'tool_receipts',(SELECT count(*) FROM marketing_runtime.tool_receipts v WHERE v.project_id=project AND v.episode_id=s.episode_id AND v.generation=s.generation),
 'tool_states',(SELECT count(*) FROM campaign_private.tool_effect_states v WHERE v.project_id=project AND v.episode_id=s.episode_id AND v.generation=s.generation),
 'service_effects',(SELECT count(*) FROM campaign_private.world_service_effects v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'campaign_states',(SELECT count(*) FROM campaign_private.world_campaign_effect_states v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'fence',(SELECT count(*) FROM campaign_private.world_fences v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'quiescence',(SELECT count(*) FROM campaign_private.world_quiescence_receipts v WHERE v.project_id=project AND v.plan_id=e.plan_id),
 'world_attachment',1,'final_world_state',1);
 IF (SELECT sum(value::integer) FROM jsonb_each_text(counts))>30000 THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('manifest_id',slot.id,'enrollment_id',e.id,'request_sha256',e.request_sha256,'operation_nonce',e.operation_nonce,
 'scope',scope_value,'expires_at',e.expires_at,'quiescence',q,'category_counts',counts,
 'materialize_before',e.expires_at-((ch.qualification_canonical::jsonb->'status_transport'->>'cleanup_reserve_seconds')||' seconds')::interval);
END $$;
REVOKE ALL ON FUNCTION campaign_private.capture_evidence_context(uuid,uuid,uuid,uuid) FROM PUBLIC,anvil_app,anvil_golden_scheduler,anvil_golden_grader;

CREATE FUNCTION marketing_runtime.begin_capture_evidence(p_job uuid,p_lease uuid,p_plan uuid,p_enrollment uuid,p_intent uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE ctx jsonb;project uuid=nullif(current_setting('anvil.project',true),'')::uuid;BEGIN
 ctx=campaign_private.capture_evidence_context(p_job,p_lease,p_plan,p_enrollment);
 IF ctx IS NULL THEN RETURN NULL;END IF;
 ctx=ctx||jsonb_build_object('intent_id',p_intent);
 INSERT INTO campaign_private.capture_evidence_intents(id,project_id,manifest_id,original_context)
 VALUES(p_intent,project,(ctx->>'manifest_id')::uuid,ctx);
 RETURN ctx;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.begin_capture_evidence(uuid,uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.begin_capture_evidence(uuid,uuid,uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.capture_evidence_rows(p_job uuid,p_lease uuid,p_plan uuid,p_enrollment uuid,p_intent uuid)
 RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE ctx jsonb;i campaign_private.capture_evidence_intents;BEGIN
 ctx=campaign_private.capture_evidence_context(p_job,p_lease,p_plan,p_enrollment);
 IF ctx IS NULL THEN RETURN;END IF;
 SELECT * INTO i FROM campaign_private.capture_evidence_intents
 WHERE project_id=(ctx->'scope'->>'project_id')::uuid AND id=p_intent AND manifest_id=(ctx->>'manifest_id')::uuid;
 IF NOT FOUND OR i.original_context IS DISTINCT FROM ctx||jsonb_build_object('intent_id',p_intent)
 OR EXISTS(SELECT 1 FROM campaign_private.capture_evidence_manifests WHERE project_id=i.project_id AND manifest_id=i.manifest_id) THEN RETURN;END IF;
 RETURN QUERY SELECT * FROM campaign_private.capture_evidence_rows(i.project_id,p_enrollment);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_evidence_rows(uuid,uuid,uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_evidence_rows(uuid,uuid,uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.retain_capture_evidence_snapshot(p_intent uuid,p_category text,p_source text,p_body text,p_hash text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 i campaign_private.capture_evidence_intents;e campaign_private.capture_enrollments;ch campaign_private.capture_channel_qualifications;
 slot campaign_private.capture_evidence_slots;actual jsonb;body jsonb;
BEGIN
 IF p_body IS NULL OR octet_length(p_body) NOT BETWEEN 1 AND 16777216
 OR p_hash IS DISTINCT FROM encode(sha256(convert_to(p_body,'UTF8')),'hex') THEN RETURN false;END IF;
 SELECT * INTO i FROM campaign_private.capture_evidence_intents WHERE project_id=project AND id=p_intent FOR UPDATE;
 IF NOT FOUND OR EXISTS(SELECT 1 FROM campaign_private.capture_evidence_manifests WHERE manifest_id=i.manifest_id) THEN RETURN false;END IF;
 SELECT * INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=project AND id=i.manifest_id;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=slot.enrollment_id;
 SELECT * INTO ch FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=e.channel_qualification_id;
 IF e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true)
 OR marketing_runtime.capture_enrollment_scope(e.id,ch.auth_kind,ch.subject,ch.account_email) IS NULL
 OR clock_timestamp()>=(i.original_context->>'materialize_before')::timestamptz THEN RETURN false;END IF;
 body=p_body::jsonb;
 IF p_category='sdk_calls' THEN
  SELECT to_jsonb(v) INTO actual FROM anvil.harbor_agent_calls v
  WHERE v.project_id=project AND v.plan_id=e.plan_id AND v.id::text=p_source AND v.status='completed' FOR SHARE OF v;
 ELSIF p_category='final_world_state' THEN
  SELECT s.controller_state INTO actual FROM campaign_private.world_sessions s
  WHERE s.project_id=project AND s.plan_id=e.plan_id AND s.plan_id::text=p_source
  AND s.controller_state_sha256=p_hash FOR UPDATE OF s;
 ELSE RETURN false;END IF;
 IF actual IS NULL OR body IS DISTINCT FROM actual THEN RETURN false;END IF;
 INSERT INTO campaign_private.capture_evidence_snapshots(project_id,manifest_id,category,source_id,canonical_body,body_sha256,byte_size)
 VALUES(project,i.manifest_id,p_category,p_source,p_body,p_hash,octet_length(p_body));
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.retain_capture_evidence_snapshot(uuid,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.retain_capture_evidence_snapshot(uuid,text,text,text,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.commit_capture_evidence(p_job uuid,p_lease uuid,p_plan uuid,p_enrollment uuid,p_intent uuid,p_body text,p_hash text,p_descriptor text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE ctx jsonb;i campaign_private.capture_evidence_intents;b jsonb;d jsonb;counts jsonb;expected jsonb;size integer;key text;
BEGIN
 IF p_body IS NULL OR p_descriptor IS NULL OR octet_length(p_body) NOT BETWEEN 1 AND 16777216
 OR octet_length(p_descriptor) NOT BETWEEN 1 AND 3072 OR p_hash IS DISTINCT FROM encode(sha256(convert_to(p_body,'UTF8')),'hex') THEN RETURN false;END IF;
 ctx=campaign_private.capture_evidence_context(p_job,p_lease,p_plan,p_enrollment);
 IF ctx IS NULL THEN RETURN false;END IF;
 SELECT * INTO i FROM campaign_private.capture_evidence_intents WHERE project_id=(ctx->'scope'->>'project_id')::uuid
 AND id=p_intent AND manifest_id=(ctx->>'manifest_id')::uuid FOR UPDATE;
 IF NOT FOUND OR i.original_context IS DISTINCT FROM ctx||jsonb_build_object('intent_id',p_intent)
 OR EXISTS(SELECT 1 FROM campaign_private.capture_evidence_manifests WHERE manifest_id=i.manifest_id) THEN RETURN false;END IF;
 b=p_body::jsonb;d=p_descriptor::jsonb;
 IF jsonb_typeof(b) IS DISTINCT FROM 'object' OR jsonb_typeof(d) IS DISTINCT FROM 'object'
 OR NOT(b ?& ARRAY['schema_version','manifest_id','enrollment_id','request_sha256','operation_nonce','scope','expires_at',
 'quiescence_id','quiescence_receipt_sha256','fence_epoch','graph_ledger_sha256','reconstruction_sha256','category_counts',
 'entry_count','raw_bytes_total','entries','capture_accepted','model_performance_validated'])
 OR b-ARRAY['schema_version','manifest_id','enrollment_id','request_sha256','operation_nonce','scope','expires_at',
 'quiescence_id','quiescence_receipt_sha256','fence_epoch','graph_ledger_sha256','reconstruction_sha256','category_counts',
 'entry_count','raw_bytes_total','entries','capture_accepted','model_performance_validated']<>'{}'::jsonb
 OR b->>'entry_count'!~'^[0-9]+$' OR b->>'raw_bytes_total'!~'^[0-9]+$'
 OR b->>'schema_version' IS DISTINCT FROM 'anvil.marketing-api-evidence-manifest.v1'
 OR d->>'schema_version' IS DISTINCT FROM 'anvil.marketing-api-evidence-ready.v1'
 OR b->'capture_accepted' IS DISTINCT FROM 'false'::jsonb OR b->'model_performance_validated' IS DISTINCT FROM 'false'::jsonb
 OR b->>'manifest_id' IS DISTINCT FROM i.manifest_id::text OR b->'category_counts' IS DISTINCT FROM ctx->'category_counts'
 OR (b->>'expires_at')::timestamptz IS DISTINCT FROM (ctx->>'expires_at')::timestamptz
 OR b->>'quiescence_id' IS DISTINCT FROM ctx->'quiescence'->>'quiescence_id'
 OR b->>'quiescence_receipt_sha256' IS DISTINCT FROM ctx->'quiescence'->>'receipt_sha256'
 OR b->>'graph_ledger_sha256' IS DISTINCT FROM ctx->'quiescence'->>'graph_ledger_sha256'
 OR b->>'reconstruction_sha256' IS DISTINCT FROM ctx->'quiescence'->>'reconstruction_sha256'
 OR b->'fence_epoch' IS DISTINCT FROM ctx->'quiescence'->'fence_epoch'
 OR jsonb_typeof(b->'entries') IS DISTINCT FROM 'array' THEN RETURN false;END IF;
 FOREACH key IN ARRAY ARRAY['enrollment_id','request_sha256','operation_nonce','scope'] LOOP
  IF b->key IS DISTINCT FROM ctx->key THEN RETURN false;END IF;
 END LOOP;
 expected=(b-'entries')||jsonb_build_object('schema_version','anvil.marketing-api-evidence-ready.v1','manifest_sha256',p_hash);
 IF d IS DISTINCT FROM expected OR jsonb_array_length(b->'entries')>30000
 OR jsonb_array_length(b->'entries')<>(SELECT sum(value::integer) FROM jsonb_each_text(ctx->'category_counts'))
 OR (b->>'entry_count')::integer<>jsonb_array_length(b->'entries')
 OR (SELECT count(DISTINCT jsonb_build_array(v->>'category',v->>'source_id')) FROM jsonb_array_elements(b->'entries') v)<>jsonb_array_length(b->'entries')
 OR (b->>'raw_bytes_total')::bigint<>(SELECT sum((v->>'canonical_bytes')::bigint) FROM jsonb_array_elements(b->'entries') v)
 OR (b->>'raw_bytes_total')::bigint>4294967296 THEN RETURN false;END IF;
 SELECT jsonb_object_agg(name,amount) INTO counts FROM (
  SELECT key AS name,(SELECT count(*) FROM jsonb_array_elements(b->'entries') v WHERE v->>'category'=key) AS amount
  FROM jsonb_each(ctx->'category_counts')
 ) values_by_category;
 IF counts IS DISTINCT FROM ctx->'category_counts' THEN RETURN false;END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(b->'entries') v
  WHERE jsonb_typeof(v) IS DISTINCT FROM 'object'
  OR NOT(v ?& ARRAY['category','source_id','canonical_bytes','canonical_sha256','encoding','custody'])
  OR v-ARRAY['category','source_id','canonical_bytes','canonical_sha256','encoding','custody']<>'{}'::jsonb
  OR NOT(ctx->'category_counts' ? (v->>'category')) OR v->>'encoding'<>'anvil.canonical-json.v1'
  OR v->>'canonical_bytes'!~'^[0-9]+$'
  OR (v->>'canonical_bytes')::bigint NOT BETWEEN 1 AND 67174400 OR v->>'canonical_sha256'!~'^[a-f0-9]{64}$'
  OR v->>'custody' IS DISTINCT FROM CASE WHEN v->>'category' IN('sdk_calls','final_world_state') THEN 'immutable_api_snapshot' ELSE 'immutable_api_record' END)
 THEN RETURN false;END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(b->'entries') v WHERE v->>'category' IN('sdk_calls','final_world_state')
  AND NOT EXISTS(SELECT 1 FROM campaign_private.capture_evidence_snapshots r WHERE r.project_id=i.project_id AND r.manifest_id=i.manifest_id
  AND r.category=v->>'category' AND r.source_id=v->>'source_id' AND r.body_sha256=v->>'canonical_sha256'
  AND r.byte_size=(v->>'canonical_bytes')::integer)) THEN RETURN false;END IF;
 -- Original row identities must actually exist. Independent API verification
 -- re-reads exact immutable canonical content/hash before any native acceptance.
 -- Enumerate only fixed identities once, without bulk bodies or per-entry reloads.
 IF EXISTS(WITH actual AS MATERIALIZED(
  SELECT r->>'category' AS category,r->>'source_id' AS source_id
  FROM campaign_private.capture_evidence_identities(i.project_id,p_enrollment) r)
  SELECT 1 FROM jsonb_array_elements(b->'entries') v WHERE NOT EXISTS(
   SELECT 1 FROM actual r WHERE r.category=v->>'category' AND r.source_id=v->>'source_id'))
 THEN RETURN false;END IF;
 size=octet_length(p_body)+octet_length(d::text);
 INSERT INTO campaign_private.capture_evidence_manifests(project_id,manifest_id,intent_id,canonical_body,body_sha256,ready_descriptor,byte_size)
 VALUES(i.project_id,i.manifest_id,i.id,p_body,p_hash,d,size);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.commit_capture_evidence(uuid,uuid,uuid,uuid,uuid,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.commit_capture_evidence(uuid,uuid,uuid,uuid,uuid,text,text,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.capture_evidence_status(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 e campaign_private.capture_enrollments;slot campaign_private.capture_evidence_slots;
 i campaign_private.capture_evidence_intents;m campaign_private.capture_evidence_manifests;ctx jsonb;state_value text;
BEGIN
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND job_id=p_job AND plan_id=p_plan;
 IF NOT FOUND THEN RETURN NULL;END IF;
 ctx=campaign_private.capture_evidence_context(p_job,p_lease,p_plan,e.id);
 IF ctx IS NULL THEN
  ctx=marketing_runtime.capture_manifest_preflight(p_job,p_lease,p_plan);
  IF ctx IS NULL THEN RETURN NULL;END IF;
 END IF;
 SELECT * INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=project AND enrollment_id=e.id;
 SELECT * INTO i FROM campaign_private.capture_evidence_intents WHERE project_id=project AND manifest_id=slot.id;
 SELECT * INTO m FROM campaign_private.capture_evidence_manifests WHERE project_id=project AND manifest_id=slot.id;
 IF m.manifest_id IS NOT NULL THEN
  IF i.original_context IS DISTINCT FROM ctx||jsonb_build_object('intent_id',i.id) THEN RETURN NULL;END IF;
  state_value='ready';
 ELSIF i.id IS NOT NULL THEN state_value='materialization_unknown';
 ELSE state_value='reserved_no_content';END IF;
 RETURN jsonb_build_object('schema_version','anvil.marketing-api-evidence-status.v1','scope',ctx->'scope',
 'manifest_id',slot.id,'enrollment_id',e.id,'request_sha256',e.request_sha256,'operation_nonce',e.operation_nonce,
 'state',state_value,'descriptor',CASE WHEN state_value='ready' THEN m.ready_descriptor ELSE NULL END,
 'capture_accepted',false,'native_qualified',false);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_evidence_status(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_evidence_status(uuid,uuid,uuid) TO anvil_app;


CREATE FUNCTION marketing_runtime.capture_evidence_for_intake(p_capture uuid,p_manifest uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 i campaign_private.capture_intents;e campaign_private.capture_enrollments;slot campaign_private.capture_evidence_slots;
 m campaign_private.capture_evidence_manifests;ch campaign_private.capture_channel_qualifications;s campaign_private.world_sessions;q campaign_private.world_quiescence_receipts;
BEGIN
 SELECT * INTO i FROM campaign_private.capture_intents WHERE project_id=project AND id=p_capture;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=i.enrollment_id;
 IF NOT FOUND OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true) THEN RETURN NULL;END IF;
 SELECT * INTO ch FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=e.channel_qualification_id;
 IF NOT FOUND OR marketing_runtime.capture_enrollment_scope(e.id,ch.auth_kind,ch.subject,ch.account_email) IS NULL THEN RETURN NULL;END IF;
 SELECT * INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=project AND enrollment_id=e.id AND id=p_manifest;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT * INTO m FROM campaign_private.capture_evidence_manifests WHERE project_id=project AND manifest_id=p_manifest;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=project AND plan_id=e.plan_id;
 SELECT * INTO q FROM campaign_private.world_quiescence_receipts WHERE project_id=project AND plan_id=e.plan_id;
 IF q.plan_id IS NULL OR m.ready_descriptor->'scope' IS DISTINCT FROM e.scope
 OR m.ready_descriptor->>'quiescence_id' IS DISTINCT FROM q.receipt->>'quiescence_id'
 OR m.ready_descriptor->>'quiescence_receipt_sha256' IS DISTINCT FROM q.receipt->>'receipt_sha256'
 OR m.ready_descriptor->>'graph_ledger_sha256' IS DISTINCT FROM q.receipt->>'graph_ledger_sha256'
 OR NOT marketing_runtime.world_session_before_quiescence(e.plan_id) THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('enrollment_id',e.id,'canonical_body',m.canonical_body,
 'manifest_sha256',m.body_sha256,'descriptor',m.ready_descriptor,
 'quiescence',q.receipt,'quiescence_stored_sha256',q.body_sha256);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_evidence_for_intake(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_evidence_for_intake(uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.capture_evidence_original(p_capture uuid,p_manifest uuid,p_category text,p_source text)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 e campaign_private.capture_enrollments;s campaign_private.world_sessions;d campaign_private.world_sources;
 ch campaign_private.capture_channel_qualifications;slot campaign_private.capture_evidence_slots;body jsonb;raw text;
BEGIN
 IF marketing_runtime.capture_evidence_for_intake(p_capture,p_manifest) IS NULL THEN RETURN NULL;END IF;
 SELECT * INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=project AND id=p_manifest;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=slot.enrollment_id;
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=project AND plan_id=e.plan_id;
 SELECT * INTO d FROM campaign_private.world_sources WHERE project_id=project AND id=s.source_id;
 SELECT * INTO ch FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=e.channel_qualification_id;
 IF p_category IN('sdk_calls','final_world_state') THEN
  SELECT canonical_body INTO raw FROM campaign_private.capture_evidence_snapshots
  WHERE project_id=project AND manifest_id=p_manifest AND category=p_category AND source_id=p_source;
  IF NOT FOUND THEN RETURN NULL;END IF;
  RETURN jsonb_build_object('encoding','retained_canonical_utf8','canonical_body',raw);
 END IF;
 CASE p_category
 WHEN 'world_source' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.world_sources v WHERE v.project_id=project AND v.id=s.source_id AND (v.id::text)=p_source;
 WHEN 'world_qualification' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.world_qualifications v WHERE v.project_id=project AND v.id=s.qualification_id AND (v.id::text)=p_source;
 WHEN 'dataset' THEN SELECT to_jsonb(v) INTO body FROM anvil.campaign_dataset_versions v WHERE v.project_id=project AND v.id=d.dataset_id AND (v.id::text)=p_source;
 WHEN 'runtime_allowlist' THEN SELECT to_jsonb(v) INTO body FROM anvil.runtime_role_allowlist v WHERE v.project_id=project AND v.id=ch.runtime_allowlist_id AND (v.id::text)=p_source;
 WHEN 'channel_qualification' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.capture_channel_qualifications v WHERE v.project_id=project AND v.id=e.channel_qualification_id AND (v.id::text)=p_source;
 WHEN 'capture_enrollment' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.capture_enrollments v WHERE v.project_id=project AND v.id=e.id AND (v.id::text)=p_source;
 WHEN 'agent_binding' THEN SELECT to_jsonb(v) INTO body FROM marketing_runtime.paid_agent_bindings v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.plan_id::text)=p_source;
 WHEN 'world_releases' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.world_releases v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.week::text)=p_source;
 WHEN 'workflow_effects' THEN SELECT to_jsonb(v) INTO body FROM marketing_runtime.workflow_effects v WHERE v.project_id=project AND v.episode_id=s.episode_id AND v.generation=s.generation AND v.execution_sha256=s.attachment->>'execution_sha256' AND (v.id::text)=p_source;
 WHEN 'turn_intents' THEN SELECT to_jsonb(v) INTO body FROM marketing_runtime.paid_turn_intents v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.stage_index::text)=p_source;
 WHEN 'turn_observations' THEN SELECT to_jsonb(v) INTO body FROM marketing_runtime.paid_turn_observations v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.stage_index::text)=p_source;
 WHEN 'sdk_prompts' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.capture_actor_prompts v WHERE v.project_id=project AND v.plan_id=e.plan_id AND v.manifest_id=slot.id AND (v.stage_index::text)=p_source;
 WHEN 'tool_intents' THEN SELECT to_jsonb(v) INTO body FROM marketing_runtime.paid_tool_action_intents v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.request_id::text)=p_source;
 WHEN 'tool_receipts' THEN SELECT to_jsonb(v) INTO body FROM marketing_runtime.tool_receipts v WHERE v.project_id=project AND v.episode_id=s.episode_id AND v.generation=s.generation AND (v.id::text)=p_source;
 WHEN 'tool_states' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.tool_effect_states v WHERE v.project_id=project AND v.episode_id=s.episode_id AND v.generation=s.generation AND (v.request_id::text)=p_source;
 WHEN 'service_effects' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.world_service_effects v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.effect_id::text)=p_source;
 WHEN 'campaign_states' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.world_campaign_effect_states v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.effect_id::text)=p_source;
 WHEN 'fence' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.world_fences v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.fence_id::text)=p_source;
 WHEN 'quiescence' THEN SELECT to_jsonb(v) INTO body FROM campaign_private.world_quiescence_receipts v WHERE v.project_id=project AND v.plan_id=e.plan_id AND (v.receipt->>'quiescence_id')=p_source;
 WHEN 'world_attachment' THEN IF s.world_binding_id::text=p_source THEN body=s.attachment;END IF;
 ELSE RETURN NULL;
 END CASE;
 IF body IS NULL THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('encoding','original_immutable_record','body',body);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_evidence_original(uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_evidence_original(uuid,uuid,text,text) TO anvil_app;

-- Enrollment-authenticated read path: original per-operation key is checked in
-- the API BEFORE this private call. It does not consume/claim/materialize work.
CREATE FUNCTION marketing_runtime.capture_evidence_enrollment_status(p_enrollment uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 e campaign_private.capture_enrollments;j anvil.jobs;ch campaign_private.capture_channel_qualifications;
BEGIN
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_enrollment;
 IF NOT FOUND OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true) THEN RETURN NULL;END IF;
 SELECT * INTO ch FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=e.channel_qualification_id;
 IF NOT FOUND OR marketing_runtime.capture_enrollment_scope(e.id,ch.auth_kind,ch.subject,ch.account_email) IS NULL THEN RETURN NULL;END IF;
 SELECT * INTO j FROM anvil.jobs WHERE project_id=project AND id=e.job_id;
 IF NOT FOUND OR j.lease_token IS NULL OR encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex') IS DISTINCT FROM e.scope->>'lease_sha256'
 THEN RETURN NULL;END IF;
 RETURN marketing_runtime.capture_evidence_status(j.id,j.lease_token,e.plan_id);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_evidence_enrollment_status(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_evidence_enrollment_status(uuid) TO anvil_app;
