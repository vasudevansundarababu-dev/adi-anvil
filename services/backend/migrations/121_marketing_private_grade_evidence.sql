-- Protected API-only original evidence for the separate private verifier.
-- No public route, private-grade profile qualification, source seed or Run grant.
CREATE FUNCTION marketing_runtime.private_grade_attestation_key(p_enrollment uuid)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT marketing_runtime.capture_attestation_key(e.id)||jsonb_build_object(
 'private_grade_transport',q.qualification_canonical::jsonb->'private_grade_transport',
 'identity',peer.os_receipt_canonical::jsonb->'framework_identity',
 'peer_binding_id',peer.id,'private_grade_profile',q.qualification_canonical::jsonb->'private_grade_profile',
 'manifest_id',m.manifest_id,'descriptor',m.ready_descriptor)
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.capture_channel_qualifications q ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 JOIN campaign_private.capture_evidence_slots slot ON slot.project_id=e.project_id AND slot.enrollment_id=e.id
 JOIN campaign_private.capture_evidence_manifests m ON m.project_id=e.project_id AND m.manifest_id=slot.id
 JOIN campaign_private.capture_attester_peer_bindings peer ON peer.project_id=e.project_id AND peer.enrollment_id=e.id
 WHERE e.id=p_enrollment AND marketing_runtime.capture_attestation_key(e.id) IS NOT NULL
 AND jsonb_typeof(q.qualification_canonical::jsonb->'private_grade_transport')='object'
 AND jsonb_typeof(peer.os_receipt_canonical::jsonb->'framework_identity')='object'
 AND peer.os_receipt_canonical::jsonb#>>'{preG_actor_observation,schema_version}'='anvil.marketing-original-actors-before-G.v1'
 AND peer.os_receipt_canonical::jsonb#>>'{preG_actor_observation,children,framework,pid}'=
  peer.os_receipt_canonical::jsonb#>>'{framework_identity_provenance,sdk_pid}'
 AND peer.os_receipt_canonical::jsonb#>>'{preG_actor_observation,children,framework,start_ticks}'=
  peer.os_receipt_canonical::jsonb#>>'{framework_identity_provenance,sdk_start_ticks}'
 AND peer.os_receipt_canonical::jsonb#>>'{preG_actor_observation,plan_sha256}'=
  peer.os_receipt_canonical::jsonb#>>'{framework_identity,plan_sha256}'
 AND peer.os_receipt_canonical::jsonb#>>'{framework_identity_provenance,stage}'='post_sdk_G_pre_graph_work'
 AND peer.os_receipt_canonical::jsonb#>>'{framework_identity_provenance,boot_id}'=e.attester_boot_id::text
 AND peer.os_receipt_canonical::jsonb#>>'{framework_identity_provenance,original_plan_sha256}'=
  peer.os_receipt_canonical::jsonb#>>'{framework_identity,plan_sha256}'
 AND peer.os_receipt_canonical::jsonb#>>'{framework_identity,job_id}'=e.job_id::text
 AND peer.os_receipt_canonical::jsonb#>>'{framework_identity,request_sha256}'=e.request_sha256
 AND peer.os_receipt_canonical::jsonb#>>'{framework_identity,operation_nonce}'=e.operation_nonce
 AND NOT EXISTS(SELECT 1 FROM campaign_private.capture_attester_peer_revocations revoked
  WHERE revoked.project_id=peer.project_id AND revoked.peer_binding_id=peer.id)
 AND m.ready_descriptor->'scope'=e.scope;
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_grade_attestation_key(uuid)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_grade_attestation_key(uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_grade_evidence(p_enrollment uuid,p_manifest uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 e campaign_private.capture_enrollments;m campaign_private.capture_evidence_manifests;
 q campaign_private.world_quiescence_receipts;peer campaign_private.capture_attester_peer_bindings;
 ch campaign_private.capture_channel_qualifications;j anvil.jobs;
 identity jsonb;provenance jsonb;BEGIN
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_enrollment;
 IF e.id IS NULL THEN RETURN NULL;END IF;
 SELECT * INTO ch FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=e.channel_qualification_id;
 SELECT * INTO j FROM anvil.jobs WHERE project_id=project AND id=e.job_id;
 IF ch.id IS NULL OR j.id IS NULL OR j.lease_token IS NULL
 OR marketing_runtime.capture_enrollment_scope(e.id,ch.auth_kind,ch.subject,ch.account_email) IS NULL
 OR NOT marketing_runtime.paid_job_current(j.id,j.lease_token,e.plan_id)
 OR encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex') IS DISTINCT FROM e.scope->>'lease_sha256'
 OR NOT EXISTS(SELECT 1 FROM campaign_private.capture_evidence_slots slot
  WHERE slot.project_id=project AND slot.enrollment_id=e.id AND slot.id=p_manifest) THEN RETURN NULL;END IF;
 SELECT * INTO m FROM campaign_private.capture_evidence_manifests WHERE project_id=project AND manifest_id=p_manifest;
 IF e.id IS NULL OR m.manifest_id IS NULL OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true)
 OR e.expires_at<=clock_timestamp() OR octet_length(m.canonical_body)>16777216
 OR m.body_sha256 IS DISTINCT FROM encode(sha256(convert_to(m.canonical_body,'UTF8')),'hex')
 OR m.ready_descriptor->'scope' IS DISTINCT FROM e.scope
 OR NOT marketing_runtime.world_session_before_quiescence(e.plan_id) THEN RETURN NULL;END IF;
 SELECT * INTO q FROM campaign_private.world_quiescence_receipts WHERE project_id=project AND plan_id=e.plan_id;
 SELECT * INTO peer FROM campaign_private.capture_attester_peer_bindings WHERE project_id=project AND enrollment_id=e.id;
 IF peer.id IS NULL OR EXISTS(SELECT 1 FROM campaign_private.capture_attester_peer_revocations revoked
  WHERE revoked.project_id=project AND revoked.peer_binding_id=peer.id) THEN RETURN NULL;END IF;
 identity=peer.os_receipt_canonical::jsonb->'framework_identity';
 provenance=peer.os_receipt_canonical::jsonb->'framework_identity_provenance';
 IF jsonb_typeof(identity) IS DISTINCT FROM 'object' OR jsonb_typeof(provenance) IS DISTINCT FROM 'object'
 OR identity->>'job_id' IS DISTINCT FROM e.job_id::text OR identity->>'request_sha256' IS DISTINCT FROM e.request_sha256
 OR identity->>'operation_nonce' IS DISTINCT FROM e.operation_nonce
 OR provenance->>'stage' IS DISTINCT FROM 'post_sdk_G_pre_graph_work'
 OR provenance->>'boot_id' IS DISTINCT FROM e.attester_boot_id::text
 OR provenance->>'original_plan_sha256' IS DISTINCT FROM identity->>'plan_sha256' THEN RETURN NULL;END IF;
 IF peer.os_receipt_canonical::jsonb#>>'{preG_actor_observation,schema_version}'
  IS DISTINCT FROM 'anvil.marketing-original-actors-before-G.v1'
 OR peer.os_receipt_canonical::jsonb#>>'{preG_actor_observation,children,framework,pid}' IS DISTINCT FROM provenance->>'sdk_pid'
 OR peer.os_receipt_canonical::jsonb#>>'{preG_actor_observation,children,framework,start_ticks}' IS DISTINCT FROM provenance->>'sdk_start_ticks'
 OR peer.os_receipt_canonical::jsonb#>>'{preG_actor_observation,plan_sha256}' IS DISTINCT FROM identity->>'plan_sha256'
 THEN RETURN NULL;END IF;
 IF q.plan_id IS NULL OR m.ready_descriptor->>'quiescence_id' IS DISTINCT FROM q.receipt->>'quiescence_id'
 OR m.ready_descriptor->>'quiescence_receipt_sha256' IS DISTINCT FROM q.receipt->>'receipt_sha256'
 OR m.ready_descriptor->>'graph_ledger_sha256' IS DISTINCT FROM q.receipt->>'graph_ledger_sha256'
 THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('schema_version','anvil.marketing-private-grade-evidence.v1',
 'origin','api_immutable_native_records','enrollment_id',e.id,'manifest_id',p_manifest,
 'identity',identity,'framework_identity_provenance',provenance,
 'canonical_body',m.canonical_body,'manifest_sha256',m.body_sha256,'descriptor',m.ready_descriptor,
 'quiescence',q.receipt,'quiescence_stored_sha256',q.body_sha256,
 'capture_accepted',false,'native_qualified',false,'run_authority','not_granted');
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_grade_evidence(uuid,uuid)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_grade_evidence(uuid,uuid) TO anvil_app;

-- Same fixed original-record projection as116, with a distinct enrollment/
-- issued-manifest gate. Does not fabricate the later upload intent to read data.
CREATE FUNCTION marketing_runtime.private_grade_read_authorized(p_enrollment uuid,p_manifest uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;metadata jsonb;
 e campaign_private.capture_enrollments;j anvil.jobs;q campaign_private.world_quiescence_receipts;BEGIN
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_enrollment;
 IF e.id IS NULL OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true) THEN RETURN false;END IF;
 metadata=marketing_runtime.private_grade_attestation_key(e.id);
 IF metadata IS NULL OR metadata->>'manifest_id' IS DISTINCT FROM p_manifest::text THEN RETURN false;END IF;
 SELECT * INTO j FROM anvil.jobs WHERE project_id=project AND id=e.job_id;
 SELECT * INTO q FROM campaign_private.world_quiescence_receipts WHERE project_id=project AND plan_id=e.plan_id;
 IF j.id IS NULL OR j.lease_token IS NULL OR q.plan_id IS NULL
 OR NOT marketing_runtime.paid_job_current(j.id,j.lease_token,e.plan_id)
 OR encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex') IS DISTINCT FROM e.scope->>'lease_sha256'
 OR NOT marketing_runtime.world_session_before_quiescence(e.plan_id)
 OR metadata#>>'{descriptor,quiescence_id}' IS DISTINCT FROM q.receipt->>'quiescence_id'
 OR metadata#>>'{descriptor,quiescence_receipt_sha256}' IS DISTINCT FROM q.receipt->>'receipt_sha256'
 OR metadata#>>'{descriptor,graph_ledger_sha256}' IS DISTINCT FROM q.receipt->>'graph_ledger_sha256'
 THEN RETURN false;END IF;
 -- Initial load verifies the complete immutable manifest bytes once. Per-row
 -- authorization rechecks current identity/revocation/Q/lease WITHOUT copying
 -- and hashing a16MiB manifest for every one of up to30000 original entries.
 RETURN true;END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_grade_read_authorized(uuid,uuid)
 FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;

CREATE FUNCTION marketing_runtime.private_grade_original(p_enrollment uuid,p_manifest uuid,p_category text,p_source text)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 e campaign_private.capture_enrollments;s campaign_private.world_sessions;d campaign_private.world_sources;
 ch campaign_private.capture_channel_qualifications;slot campaign_private.capture_evidence_slots;body jsonb;raw text;
BEGIN
 IF marketing_runtime.private_grade_read_authorized(p_enrollment,p_manifest) IS DISTINCT FROM true THEN RETURN NULL;END IF;
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
REVOKE ALL ON FUNCTION marketing_runtime.private_grade_original(uuid,uuid,text,text) FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_grade_original(uuid,uuid,text,text) TO anvil_app;
-- A distinct restricted function owner avoids relying on migration-user
-- superuser/BYPASSRLS semantics for the new private reader. No login/member grant.
DO $$ DECLARE consumer text;pair text[];s text;t text;BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_private_grade_owner') THEN
  CREATE ROLE anvil_private_grade_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_private_grade_owner'
  AND(rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
 THEN RAISE EXCEPTION 'isolated restricted private grade owner required';END IF;
 FOREACH consumer IN ARRAY ARRAY['anvil_app','anvil_worker','anvil_golden_scheduler','anvil_golden_grader',
  'anvil_capture_registrar','anvil_capture_peer_writer','anvil_capture_enrollment_owner'] LOOP
  IF pg_has_role(consumer,'anvil_private_grade_owner','MEMBER')
  THEN RAISE EXCEPTION 'private grade owner must not be an operational capability';END IF;
 END LOOP;
 FOREACH pair SLICE 1 IN ARRAY ARRAY[
 ['campaign_private','capture_enrollments'],['campaign_private','capture_channel_qualifications'],
 ['campaign_private','capture_attester_peer_bindings'],['campaign_private','capture_attester_peer_revocations'],
 ['campaign_private','capture_evidence_slots'],['campaign_private','capture_evidence_manifests'],
 ['campaign_private','capture_evidence_snapshots'],['campaign_private','world_quiescence_receipts'],
 ['campaign_private','world_sessions'],['campaign_private','world_sources'],['campaign_private','world_qualifications'],
 ['campaign_private','world_releases'],['campaign_private','capture_actor_prompts'],
 ['campaign_private','tool_effect_states'],['campaign_private','world_service_effects'],
 ['campaign_private','world_campaign_effect_states'],['campaign_private','world_fences'],
 ['anvil','jobs'],['anvil','campaign_dataset_versions'],['anvil','runtime_role_allowlist'],
 ['marketing_runtime','paid_agent_bindings'],['marketing_runtime','workflow_effects'],
 ['marketing_runtime','paid_turn_intents'],['marketing_runtime','paid_turn_observations'],
 ['marketing_runtime','paid_tool_action_intents'],['marketing_runtime','tool_receipts']] LOOP
  s=pair[1];t=pair[2];
  EXECUTE format('GRANT SELECT ON %I.%I TO anvil_private_grade_owner',s,t);
  -- Public verification metadata can be located before signature verification;
  -- complete body readers still require original project/actor/manifest joins.
  IF t IN('capture_enrollments','capture_channel_qualifications','capture_attester_peer_bindings',
    'capture_attester_peer_revocations','capture_evidence_slots','capture_evidence_manifests') THEN
   EXECUTE format('CREATE POLICY private_grade_read ON %I.%I FOR SELECT TO anvil_private_grade_owner USING(nullif(current_setting(''anvil.project'',true),'''') IS NULL OR project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',s,t);
  ELSE
   EXECUTE format('CREATE POLICY private_grade_read ON %I.%I FOR SELECT TO anvil_private_grade_owner USING(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',s,t);
  END IF;
 END LOOP;
END $$;
GRANT USAGE ON SCHEMA anvil,campaign_private,marketing_runtime TO anvil_private_grade_owner;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_attestation_key(uuid),
 marketing_runtime.capture_enrollment_scope(uuid,text,text,text),marketing_runtime.paid_job_current(uuid,uuid,uuid),
 marketing_runtime.world_session_before_quiescence(uuid) TO anvil_private_grade_owner;
GRANT CREATE ON SCHEMA marketing_runtime TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_grade_attestation_key(uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_grade_evidence(uuid,uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_grade_original(uuid,uuid,text,text) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_grade_read_authorized(uuid,uuid) OWNER TO anvil_private_grade_owner;
REVOKE CREATE ON SCHEMA marketing_runtime FROM anvil_private_grade_owner;
INSERT INTO anvil.schema_versions(version) VALUES(121);
