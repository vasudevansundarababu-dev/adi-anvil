-- Read-only original native evaluator/calibration context. No qualification or
-- private-reference grant to the ordinary API, worker, actor or scheduler.
ALTER TABLE campaign_private.private_grade_frames ADD COLUMN native_registry_sha256 text
 CHECK(native_registry_sha256 IS NULL OR native_registry_sha256~'^[a-f0-9]{64}$');
ALTER TABLE campaign_private.private_grade_frames ADD COLUMN deployment_release_sha256 text
 CHECK(deployment_release_sha256 IS NULL OR deployment_release_sha256~'^[a-f0-9]{64}$');
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['workspace_execution_groups','benchmark_task_groups','praxis_resolved_tasks',
 'project_binding_versions','project_binding_qualifications','project_binding_qualification_revocations',
 'evaluator_configurations','evaluator_validation_receipts','evaluator_revocations'] LOOP
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_private_grade_owner',t);
  EXECUTE format('CREATE POLICY private_native_registry_read ON anvil.%I FOR SELECT TO anvil_private_grade_owner USING(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',t);
 END LOOP;
END $$;
GRANT SELECT(id,active) ON anvil.users TO anvil_private_grade_owner;
GRANT SELECT(project_id,user_id,active,role) ON anvil.memberships TO anvil_private_grade_owner;
CREATE POLICY private_native_membership_read ON anvil.memberships FOR SELECT TO anvil_private_grade_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
GRANT SELECT ON campaign_private.references TO anvil_private_grade_owner;
CREATE POLICY private_native_reference_read ON campaign_private.references FOR SELECT TO anvil_private_grade_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);

CREATE FUNCTION marketing_runtime.private_native_ordinal_context(p_enrollment uuid,p_manifest uuid,p_release text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;e campaign_private.capture_enrollments;
 paid marketing_runtime.paid_agent_bindings;g anvil.workspace_execution_groups;source anvil.benchmark_task_groups;
 resolved anvil.praxis_resolved_tasks;b anvil.project_binding_versions;q anvil.project_binding_qualifications;
 prepared jsonb;task jsonb;case_value jsonb;ref_manifest jsonb;member jsonb;reference jsonb;
 evaluators jsonb='[]'::jsonb;config anvil.evaluator_configurations;validation anvil.evaluator_validation_receipts;
 rubric jsonb;metadata jsonb;body jsonb;active boolean;BEGIN
 IF p_release IS NULL OR p_release!~'^[a-f0-9]{64}$'
 OR marketing_runtime.private_grade_read_authorized(p_enrollment,p_manifest) IS DISTINCT FROM true THEN RETURN NULL;END IF;
 metadata=marketing_runtime.private_grade_attestation_key(p_enrollment);
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_enrollment;
 SELECT * INTO paid FROM marketing_runtime.paid_agent_bindings WHERE project_id=project AND plan_id=e.plan_id;
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE project_id=project AND id=paid.group_id;
 SELECT * INTO source FROM anvil.benchmark_task_groups WHERE project_id=project AND id=paid.task_group_id;
 SELECT * INTO resolved FROM anvil.praxis_resolved_tasks WHERE project_id=project AND id=paid.resolved_task_id;
 IF e.id IS NULL OR paid.plan_id IS NULL OR g.id IS NULL OR source.id IS NULL OR resolved.id IS NULL
 OR paid.execution_sha256 IS DISTINCT FROM e.scope->>'execution_sha256' THEN RETURN NULL;END IF;
 prepared=g.snapshot->'preparation';
 IF jsonb_typeof(prepared) IS DISTINCT FROM 'object' OR jsonb_typeof(source.content->'tasks') IS DISTINCT FROM 'array'
 OR (SELECT count(*) FROM jsonb_array_elements(source.content->'tasks') row
  WHERE row->>'task_id'=resolved.task_key AND row->>'task_version'=resolved.revision
  AND row->>'payload_sha256'=resolved.private_reference_sha256)<>1 THEN RETURN NULL;END IF;
 SELECT row INTO task FROM jsonb_array_elements(source.content->'tasks') row
 WHERE row->>'task_id'=resolved.task_key AND row->>'task_version'=resolved.revision
 AND row->>'payload_sha256'=resolved.private_reference_sha256;
 case_value=jsonb_build_object('case_id',paid.case_id,'snapshot_sha256',paid.native_binding#>>'{case_assignment,snapshot_sha256}');
 SELECT * INTO b FROM anvil.project_binding_versions WHERE project_id=project
 AND id=(prepared#>>'{project_binding,id}')::uuid AND task_group_id=paid.task_group_id;
 IF b.id IS NULL OR b.snapshot_sha256 IS DISTINCT FROM prepared#>>'{project_binding,snapshot_sha256}'
 OR b.id IS DISTINCT FROM (SELECT latest.id FROM anvil.project_binding_versions latest
  WHERE latest.project_id=project AND latest.task_group_id=b.task_group_id
  ORDER BY latest.version DESC,latest.created_at DESC,latest.id DESC LIMIT 1)
 THEN RETURN NULL;END IF;
 SELECT * INTO q FROM anvil.project_binding_qualifications current
 WHERE current.project_id=project AND current.binding_id=b.id AND current.release_sha256=p_release
 AND current.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r
  WHERE r.project_id=project AND r.qualification_id=current.id)
 ORDER BY current.created_at DESC,current.id DESC LIMIT 1;
 ref_manifest=prepared->'campaign_reference_manifest';
 IF jsonb_typeof(ref_manifest->'cases') IS DISTINCT FROM 'array' THEN RETURN NULL;END IF;
 IF (SELECT count(*) FROM jsonb_array_elements(ref_manifest->'cases') row
  WHERE row->>'case_id'=paid.case_id AND row->>'snapshot_sha256'=case_value->>'snapshot_sha256')<>1 THEN RETURN NULL;END IF;
 SELECT row INTO member FROM jsonb_array_elements(ref_manifest->'cases') row
 WHERE row->>'case_id'=paid.case_id AND row->>'snapshot_sha256'=case_value->>'snapshot_sha256';
 SELECT jsonb_build_object('id',r.id,'content',r.content,'content_sha256',r.content_sha256) INTO reference
 FROM campaign_private.references r WHERE r.project_id=project AND r.id=(member->>'reference_id')::uuid
 AND r.content_sha256=member->>'reference_sha256' AND r.task_id=task->>'task_id'
 AND r.task_version=task->>'task_version' AND r.payload_sha256=task->>'payload_sha256'
 AND r.case_id=paid.case_id AND r.case_sha256=case_value->>'snapshot_sha256';
 IF jsonb_typeof(b.snapshot->'rubric') IS DISTINCT FROM 'array'
 OR (SELECT count(*) FROM jsonb_array_elements(b.snapshot->'rubric') row WHERE row->>'kind'='evaluator')>23
 OR (SELECT count(*) FROM jsonb_array_elements(b.snapshot->'rubric') row WHERE row->>'kind'='evaluator')<>
  (SELECT count(DISTINCT row->>'id') FROM jsonb_array_elements(b.snapshot->'rubric') row WHERE row->>'kind'='evaluator')
 THEN RETURN NULL;END IF;
 FOR rubric IN SELECT row FROM jsonb_array_elements(b.snapshot->'rubric') row WHERE row->>'kind'='evaluator' ORDER BY row->>'id' LOOP
  SELECT * INTO config FROM anvil.evaluator_configurations WHERE project_id=project AND id=(rubric->>'id')::uuid;
  IF config.id IS NULL THEN RETURN NULL;END IF;
  SELECT * INTO validation FROM anvil.evaluator_validation_receipts v WHERE v.project_id=project AND v.configuration_id=config.id
  ORDER BY v.created_at DESC,v.id DESC LIMIT 1;
  SELECT EXISTS(SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id AND m.project_id=project
   WHERE u.id=config.created_by AND u.active AND m.active AND m.role IN('admin','rl-engineer')) INTO active;
  evaluators=evaluators||jsonb_build_array(jsonb_build_object('id',config.id,'adapter',config.adapter,
   'adapter_version',config.adapter_version,'configuration',config.configuration,'configuration_sha256',config.configuration_sha256,
   'revoked',EXISTS(SELECT 1 FROM anvil.evaluator_revocations r WHERE r.project_id=project AND r.configuration_id=config.id),
   'author_active',active,'validation',CASE WHEN validation.id IS NULL THEN NULL ELSE
    jsonb_build_object('id',validation.id,'evidence',validation.evidence,'evidence_sha256',validation.evidence_sha256) END));
 END LOOP;
 SELECT EXISTS(SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id AND m.project_id=project
  WHERE u.id=b.created_by AND u.active AND m.active AND m.role IN('admin','rl-engineer')) INTO active;
 body=jsonb_build_object('schema_version','anvil.marketing-private-native-ordinal-context.v1',
 'identity',metadata->'identity','scope',e.scope,'prepared',prepared,'task',task,'case',case_value,'reference',reference,
 'binding',jsonb_build_object('id',b.id,'snapshot',b.snapshot,'snapshot_sha256',b.snapshot_sha256,'created_by',b.created_by,'author_active',active),
 'qualification',CASE WHEN q.id IS NULL THEN NULL ELSE jsonb_build_object('id',q.id,'binding_id',q.binding_id,
  'release_sha256',q.release_sha256,'evidence',q.evidence,'evidence_sha256',q.evidence_sha256) END,'evaluators',evaluators);
 IF octet_length(body::text)>33554432 THEN RETURN NULL;END IF;
 RETURN body;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_native_ordinal_context(uuid,uuid,text)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_native_ordinal_context(uuid,uuid,text) TO anvil_app;
CREATE OR REPLACE FUNCTION marketing_runtime.record_private_grade_frame(p_enrollment uuid,p_manifest uuid,p_actor uuid,p_raw bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;slot campaign_private.private_grade_artifact_slots;
 identifier uuid=gen_random_uuid();body jsonb;metadata jsonb;profile jsonb;ctx jsonb;registry_sha text;release text;
 actor campaign_private.private_actor_originals;BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR marketing_runtime.private_grade_read_authorized(p_enrollment,p_manifest) IS DISTINCT FROM true THEN RETURN NULL;END IF;
 SELECT * INTO slot FROM campaign_private.private_grade_artifact_slots WHERE project_id=project AND enrollment_id=p_enrollment AND kind='grade_frame';
 SELECT a.* INTO actor FROM campaign_private.private_actor_originals a
 JOIN campaign_private.private_actor_intents i ON i.project_id=a.project_id AND i.id=a.intent_id
 JOIN campaign_private.private_actor_slots s ON s.project_id=i.project_id AND s.id=i.slot_id
 WHERE a.project_id=project AND a.id=p_actor AND s.enrollment_id=p_enrollment AND i.manifest_id=p_manifest;
 IF slot.id IS NULL OR actor.id IS NULL OR p_raw IS NULL OR octet_length(p_raw) NOT BETWEEN 1 AND slot.maximum_wire_bytes
 THEN RETURN NULL;END IF;
 body=convert_from(p_raw,'UTF8')::jsonb;metadata=marketing_runtime.private_grade_attestation_key(p_enrollment);
 IF body->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-grade-input-reply.v1'
 OR body->>'enrollment_id' IS DISTINCT FROM p_enrollment::text OR body->>'manifest_id' IS DISTINCT FROM p_manifest::text
 OR body->'identity' IS DISTINCT FROM metadata->'identity' OR body->'scope' IS DISTINCT FROM metadata->'scope'
 OR body#>>'{file_sha256,actor-output.json}' IS DISTINCT FROM actor.raw_sha256
 OR convert_to(body#>>'{files,actor-output.json}','UTF8') IS DISTINCT FROM actor.raw_body THEN RETURN NULL;END IF;
 IF body->'mapping_qualified'='true'::jsonb THEN
  SELECT q.qualification_canonical::jsonb->'private_capture_profile' INTO profile
  FROM campaign_private.capture_enrollments e JOIN campaign_private.capture_channel_qualifications q
   ON q.project_id=e.project_id AND q.id=e.channel_qualification_id WHERE e.project_id=project AND e.id=p_enrollment;
  IF marketing_runtime.private_capture_profile_current(p_enrollment) IS DISTINCT FROM true THEN RETURN NULL;END IF;
  release=profile->>'deployment_release_sha256';
  ctx=marketing_runtime.private_native_ordinal_context(p_enrollment,p_manifest,release);
  IF ctx IS NULL OR ctx->'qualification'='null'::jsonb
  OR ctx#>>'{qualification,evidence,marketing_private_ordinal_crosswalk,status}' IS DISTINCT FROM 'passed'
  OR ctx#>>'{qualification,evidence,marketing_private_ordinal_crosswalk,source_sha256}' IS DISTINCT FROM profile->>'binding_source_sha256'
  OR ctx#>>'{qualification,evidence,marketing_private_ordinal_crosswalk,mapping_sha256}' IS DISTINCT FROM profile->>'ordinal_mapping_sha256'
  THEN RETURN NULL;END IF;
  registry_sha=encode(sha256(convert_to(ctx::text,'UTF8')),'hex');
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_grade_frame:'||slot.id::text,0));
 IF EXISTS(SELECT 1 FROM campaign_private.private_grade_frames v WHERE v.project_id=project AND v.slot_id=slot.id) THEN RETURN NULL;END IF;
 INSERT INTO campaign_private.private_grade_frames(id,project_id,slot_id,manifest_id,actor_original_id,raw_frame,raw_sha256,
 native_registry_sha256,deployment_release_sha256)
 VALUES(identifier,project,slot.id,p_manifest,p_actor,p_raw,encode(sha256(p_raw),'hex'),registry_sha,release);
 RETURN jsonb_build_object('id',identifier,'enrollment_id',p_enrollment,'manifest_id',p_manifest,
 'raw_sha256',encode(sha256(p_raw),'hex'),'raw_bytes',octet_length(p_raw),'capture_accepted',false,'run_authority','not_granted');
END $$;
GRANT EXECUTE ON FUNCTION anvil.lock_native_ordinal_award(uuid,uuid) TO anvil_private_grade_owner;
CREATE FUNCTION marketing_runtime.private_native_ordinal_acceptance_context(p_enrollment uuid,p_manifest uuid,p_release text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE ctx jsonb;item jsonb;BEGIN
 IF current_setting('transaction_read_only')<>'off' THEN RETURN NULL;END IF;
 ctx=marketing_runtime.private_native_ordinal_context(p_enrollment,p_manifest,p_release);
 IF ctx IS NULL THEN RETURN NULL;END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(ctx#>'{binding,snapshot,rubric}')
  WHERE value->>'kind'='evaluator' ORDER BY value->>'id' LOOP
  IF anvil.lock_native_ordinal_award((ctx#>>'{binding,id}')::uuid,(item->>'id')::uuid) IS DISTINCT FROM true
  THEN RETURN NULL;END IF;
 END LOOP;
 -- The original authority fence/author locks are retained through the caller's
 -- actual acceptance INSERT+COMMIT. Re-read after those locks before comparing.
 RETURN marketing_runtime.private_native_ordinal_context(p_enrollment,p_manifest,p_release);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_native_ordinal_acceptance_context(uuid,uuid,text)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_native_ordinal_acceptance_context(uuid,uuid,text) TO anvil_app;
GRANT CREATE ON SCHEMA marketing_runtime TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_native_ordinal_context(uuid,uuid,text) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_native_ordinal_acceptance_context(uuid,uuid,text) OWNER TO anvil_private_grade_owner;
REVOKE CREATE ON SCHEMA marketing_runtime FROM anvil_private_grade_owner;
INSERT INTO anvil.schema_versions(version) VALUES(125);
