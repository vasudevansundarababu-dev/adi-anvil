-- Durable original capture acceptance. No qualification, run or paid authority
-- is issued by this migration. Metadata fits the original123 result reservation.
ALTER TABLE campaign_private.capture_raw_intakes ADD CONSTRAINT capture_raw_project_identity UNIQUE(project_id,id);
CREATE TABLE campaign_private.private_capture_acceptances(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,enrollment_id uuid NOT NULL UNIQUE,
 raw_intake_id uuid NOT NULL UNIQUE,result_original_id uuid NOT NULL UNIQUE,
 receipt jsonb NOT NULL CHECK(octet_length(receipt::text)<=4096),
 receipt_sha256 text NOT NULL CHECK(receipt_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,enrollment_id) REFERENCES campaign_private.capture_enrollments(project_id,id),
 FOREIGN KEY(project_id,raw_intake_id) REFERENCES campaign_private.capture_raw_intakes(project_id,id),
 FOREIGN KEY(project_id,result_original_id) REFERENCES campaign_private.private_result_originals(project_id,id));
ALTER TABLE campaign_private.private_capture_acceptances ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.private_capture_acceptances FORCE ROW LEVEL SECURITY;
REVOKE ALL ON campaign_private.private_capture_acceptances
 FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
GRANT SELECT,INSERT ON campaign_private.private_capture_acceptances TO anvil_private_grade_owner;
CREATE POLICY private_grade_read ON campaign_private.private_capture_acceptances FOR SELECT TO anvil_private_grade_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE POLICY private_grade_append ON campaign_private.private_capture_acceptances FOR INSERT TO anvil_private_grade_owner
 WITH CHECK(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.private_capture_acceptances
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON campaign_private.private_capture_acceptances
 FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable();
GRANT SELECT ON campaign_private.capture_raw_intakes TO anvil_private_grade_owner;

CREATE FUNCTION marketing_runtime.private_capture_context(p_enrollment uuid,p_intake uuid)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT jsonb_build_object('enrollment',marketing_runtime.private_result_attestation_key(e.id),
 'qualification',q.qualification_canonical::jsonb,'peer_receipt_canonical',peer.os_receipt_canonical,
 'current_status',marketing_runtime.capture_evidence_enrollment_status(e.id),
 'raw_sha256',r.raw_sha256,'raw_bytes',octet_length(r.raw_wire),'raw_intake_id',r.id)
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.capture_channel_qualifications q ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 JOIN campaign_private.capture_attester_peer_bindings peer ON peer.project_id=e.project_id AND peer.enrollment_id=e.id
 JOIN campaign_private.capture_raw_intakes r ON r.project_id=e.project_id AND r.enrollment_id=e.id AND r.id=p_intake
 WHERE e.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND e.id=p_enrollment
 AND e.actor_id::text=current_setting('anvil.user',true) AND r.classification='raw_received_unqualified'
 AND marketing_runtime.private_result_attestation_key(e.id) IS NOT NULL
 AND jsonb_typeof(q.qualification_canonical::jsonb->'private_capture_profile')='object';
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_capture_context(uuid,uuid)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_capture_context(uuid,uuid) TO anvil_app;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_evidence_enrollment_status(uuid) TO anvil_private_grade_owner;

CREATE FUNCTION marketing_runtime.private_capture_profile_current(p_enrollment uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE q jsonb;e campaign_private.capture_enrollments;p jsonb;control text;BEGIN
 SELECT * INTO e FROM campaign_private.capture_enrollments
 WHERE project_id=nullif(current_setting('anvil.project',true),'')::uuid AND id=p_enrollment;
 IF e.id IS NULL OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true) THEN RETURN false;END IF;
 SELECT qualification_canonical::jsonb INTO q FROM campaign_private.capture_channel_qualifications
 WHERE project_id=e.project_id AND id=e.channel_qualification_id;
 p=q->'private_capture_profile';
 IF jsonb_typeof(p) IS DISTINCT FROM 'object'
 OR p->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-capture-qualification.v1'
 OR p->>'actor_scope_profile' IS DISTINCT FROM 'opening-framework-graph-host-helpers-cgroup2-v1'
 OR p->>'api_source_sha256' IS DISTINCT FROM q#>>'{private_grade_transport,source_sha256}'
 OR p->>'deployment_release_sha256' IS NULL OR p->>'deployment_release_sha256'!~'^[a-f0-9]{64}$'
 OR p->>'binding_source_sha256' IS NULL OR p->>'binding_source_sha256'!~'^[a-f0-9]{64}$'
 OR p->>'ordinal_mapping_sha256' IS NULL OR p->>'ordinal_mapping_sha256'!~'^[a-f0-9]{64}$'
 OR p->>'runtime_image_digest' IS NULL OR p->>'runtime_image_digest'!~'^sha256:[a-f0-9]{64}$'
 OR p->>'private_program_sha256' IS NULL OR p->>'private_program_sha256'!~'^[a-f0-9]{64}$'
 OR p->>'tls_certificate_sha256' IS NULL OR p->>'tls_certificate_sha256'!~'^[a-f0-9]{64}$'
 OR p->>'not_after' IS NULL OR jsonb_typeof(p->'controls') IS DISTINCT FROM 'object'
 OR (SELECT count(*) FROM jsonb_object_keys(p->'controls'))<>12 THEN RETURN false;END IF;
 IF clock_timestamp()>=(p->>'not_after')::timestamptz OR e.expires_at>(p->>'not_after')::timestamptz
 OR (p->>'not_after')::timestamptz>'2026-12-11T05:48:04Z'::timestamptz THEN RETURN false;END IF;
 FOREACH control IN ARRAY ARRAY['original_root_children','pidfd_start_identity','root_outside_scope',
 'fixed_engine_profile','captured_actor_before_grading','separate_verifier_process','complete_private_result_custody',
 'final_frozen_empty_scope','actual_owned_containers_stopped','original_api_manifest','no_actor_private_mount',
 'bounded_cancellation_cleanup'] LOOP
  IF p#>>ARRAY['controls',control,'status'] IS DISTINCT FROM 'passed'
  OR p#>>ARRAY['controls',control,'evidence_sha256'] IS NULL
  OR p#>>ARRAY['controls',control,'evidence_sha256']!~'^[a-f0-9]{64}$' THEN RETURN false;END IF;
 END LOOP;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_capture_profile_current(uuid)
 FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;

CREATE OR REPLACE FUNCTION marketing_runtime.private_actor_slot_preflight(p_job uuid,p_lease uuid,p_plan uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE ctx jsonb;project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 e campaign_private.capture_enrollments;slot campaign_private.private_actor_slots;
 q jsonb;frame_max bigint;result_max integer;BEGIN
 IF current_setting('transaction_read_only')<>'on' OR current_setting('transaction_isolation')<>'read committed'
 OR pg_current_xact_id_if_assigned() IS NOT NULL THEN RETURN NULL;END IF;
 ctx=marketing_runtime.committed_attester_enrollment(p_job,p_lease,p_plan);
 IF ctx IS NULL THEN RETURN NULL;END IF;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=(ctx#>>'{enrollment,enrollment_id}')::uuid;
 IF marketing_runtime.private_capture_profile_current(e.id) IS DISTINCT FROM true THEN RETURN NULL;END IF;
 SELECT * INTO slot FROM campaign_private.private_actor_slots WHERE project_id=project AND enrollment_id=e.id;
 SELECT qualification_canonical::jsonb INTO q FROM campaign_private.capture_channel_qualifications
 WHERE project_id=project AND id=e.channel_qualification_id;
 SELECT 4096+2*sum(item.value::integer)+2*(q#>>'{private_grade_transport,reply_metadata_limit}')::integer
 INTO frame_max FROM jsonb_each_text(q#>'{private_grade_transport,file_limits}') AS item;
 result_max=(q#>>'{private_result_transport,wire_limit}')::integer;
 IF slot.id IS NULL OR slot.byte_size<>slot.maximum_bytes+8192
 OR frame_max IS NULL OR frame_max NOT BETWEEN 1 AND 1048576 OR result_max IS NULL OR result_max NOT BETWEEN 1 AND 1048576
 OR NOT EXISTS(SELECT 1 FROM campaign_private.private_grade_artifact_slots s WHERE s.project_id=project
  AND s.enrollment_id=e.id AND s.kind='grade_frame' AND s.maximum_wire_bytes=frame_max AND s.byte_size=frame_max+8192)
 OR NOT EXISTS(SELECT 1 FROM campaign_private.private_grade_artifact_slots s WHERE s.project_id=project
  AND s.enrollment_id=e.id AND s.kind='verifier_result' AND s.maximum_wire_bytes=result_max AND s.byte_size=2*result_max+8192)
 THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('schema_version','anvil.marketing-private-actor-capacity.v1','id',slot.id,
 'enrollment_id',e.id,'scope',e.scope,'maximum_bytes',slot.maximum_bytes,
 'producer_qualification_sha256',ctx#>>'{enrollment,producer_qualification_sha256}',
 'expires_at',e.expires_at,'capture_accepted',false,'run_authority','not_granted');
END $$;

CREATE FUNCTION marketing_runtime.accept_private_capture(p_enrollment uuid,p_intake uuid,p_result uuid,p_wire text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;e campaign_private.capture_enrollments;
 original campaign_private.private_result_originals;i campaign_private.private_result_intents;
 slot campaign_private.private_grade_artifact_slots;frame campaign_private.private_grade_frames;
 ctx jsonb;profile jsonb;body jsonb;identifier uuid=gen_random_uuid();control text;BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN NULL;END IF;
 ctx=marketing_runtime.private_capture_context(p_enrollment,p_intake);
 IF ctx IS NULL OR ctx->>'raw_sha256' IS DISTINCT FROM p_wire
 OR marketing_runtime.private_capture_profile_current(p_enrollment) IS DISTINCT FROM true THEN RETURN NULL;END IF;
 profile=ctx#>'{qualification,private_capture_profile}';
 IF profile->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-capture-qualification.v1'
 OR profile->>'actor_scope_profile' IS DISTINCT FROM 'opening-framework-graph-host-helpers-cgroup2-v1'
 OR profile->>'not_after' IS NULL OR clock_timestamp()>=(profile->>'not_after')::timestamptz
 THEN RETURN NULL;END IF;
 FOREACH control IN ARRAY ARRAY['original_root_children','pidfd_start_identity','root_outside_scope',
 'fixed_engine_profile','captured_actor_before_grading','separate_verifier_process','complete_private_result_custody',
 'final_frozen_empty_scope','actual_owned_containers_stopped','original_api_manifest','no_actor_private_mount',
 'bounded_cancellation_cleanup'] LOOP
  IF profile#>>ARRAY['controls',control,'status'] IS DISTINCT FROM 'passed'
  OR profile#>>ARRAY['controls',control,'evidence_sha256'] IS NULL
  OR profile#>>ARRAY['controls',control,'evidence_sha256']!~'^[a-f0-9]{64}$' THEN RETURN NULL;END IF;
 END LOOP;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_enrollment;
 SELECT * INTO original FROM campaign_private.private_result_originals WHERE project_id=project AND id=p_result;
 SELECT * INTO i FROM campaign_private.private_result_intents WHERE project_id=project AND id=original.intent_id;
 SELECT * INTO slot FROM campaign_private.private_grade_artifact_slots WHERE project_id=project AND id=i.slot_id;
 SELECT * INTO frame FROM campaign_private.private_grade_frames WHERE project_id=project AND id=i.frame_id;
 IF original.id IS NULL OR e.id IS NULL OR slot.enrollment_id IS DISTINCT FROM e.id OR slot.kind<>'verifier_result'
 OR frame.id IS NULL OR frame.manifest_id::text IS DISTINCT FROM ctx#>>'{enrollment,manifest_id}'
 OR frame.raw_sha256 IS DISTINCT FROM (convert_from(original.raw_bundle,'UTF8')::jsonb->>'grade_frame_sha256')
 OR e.expires_at> (profile->>'not_after')::timestamptz THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_capture:'||e.id::text,0));
 -- Recheck after any acceptance lock wait. The final126 validator also owns
 -- native-authority fencing and compares protected physical originals in SQL.
 ctx=marketing_runtime.private_capture_context(p_enrollment,p_intake);
 IF ctx IS NULL OR marketing_runtime.private_capture_profile_current(p_enrollment) IS DISTINCT FROM true
 OR marketing_runtime.private_capture_evidence_valid(p_enrollment,p_intake,p_result) IS DISTINCT FROM true
 THEN RETURN NULL;END IF;
 IF EXISTS(SELECT 1 FROM campaign_private.private_capture_acceptances a WHERE a.project_id=project AND a.enrollment_id=e.id)
 THEN RETURN NULL;END IF;
 body=jsonb_build_object('schema_version','anvil.marketing-private-capture-accepted.v1',
 'id',identifier,'accepted_capture_reference',identifier,'enrollment_id',e.id,'manifest_id',frame.manifest_id,
 'wire_sha256',p_wire,'grade_frame_sha256',frame.raw_sha256,'verifier_result_id',original.id,
 'verifier_result_sha256',original.verifier_sha256,'process_receipt_sha256',original.process_sha256,
 'grade_status',original.grade_status,'capture_accepted',true,'native_qualified',true,
 'run_authority','not_granted','model_performance_validated',false,'human_legal_acceptance','not_established');
 INSERT INTO campaign_private.private_capture_acceptances(id,project_id,enrollment_id,raw_intake_id,result_original_id,receipt,receipt_sha256)
 VALUES(identifier,project,e.id,p_intake,p_result,body,encode(sha256(convert_to(body::text,'UTF8')),'hex'));
 RETURN body;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.accept_private_capture(uuid,uuid,uuid,text)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.accept_private_capture(uuid,uuid,uuid,text) TO anvil_app;
GRANT CREATE ON SCHEMA marketing_runtime TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_capture_context(uuid,uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_capture_profile_current(uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.accept_private_capture(uuid,uuid,uuid,text) OWNER TO anvil_private_grade_owner;
REVOKE CREATE ON SCHEMA marketing_runtime FROM anvil_private_grade_owner;
INSERT INTO anvil.schema_versions(version) VALUES(124);
