-- Original API grade frame + full result/process custody, never acceptance.
CREATE TABLE campaign_private.private_grade_artifact_slots(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,enrollment_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN('grade_frame','verifier_result')),
 maximum_wire_bytes integer NOT NULL CHECK(maximum_wire_bytes BETWEEN 1 AND 1048576),
 byte_size integer NOT NULL CHECK(byte_size=maximum_wire_bytes*CASE WHEN kind='verifier_result' THEN 2 ELSE 1 END+8192),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),UNIQUE(enrollment_id,kind),
 FOREIGN KEY(project_id,enrollment_id) REFERENCES campaign_private.capture_enrollments(project_id,id));
CREATE TABLE campaign_private.private_grade_frames(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,slot_id uuid NOT NULL UNIQUE,manifest_id uuid NOT NULL,
 actor_original_id uuid NOT NULL,raw_frame bytea NOT NULL CHECK(octet_length(raw_frame) BETWEEN 1 AND 1048576),
 raw_sha256 text NOT NULL CHECK(raw_sha256=encode(sha256(raw_frame),'hex')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,slot_id) REFERENCES campaign_private.private_grade_artifact_slots(project_id,id),
 FOREIGN KEY(project_id,manifest_id) REFERENCES campaign_private.capture_evidence_slots(project_id,id),
 FOREIGN KEY(project_id,actor_original_id) REFERENCES campaign_private.private_actor_originals(project_id,id));
CREATE TABLE campaign_private.private_result_intents(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,slot_id uuid NOT NULL UNIQUE,frame_id uuid NOT NULL,
 wire_bytes integer NOT NULL CHECK(wire_bytes BETWEEN 1 AND 1048576),wire_sha256 text NOT NULL CHECK(wire_sha256~'^[a-f0-9]{64}$'),
 attestation_sha256 text NOT NULL CHECK(attestation_sha256~'^[a-f0-9]{64}$'),
 verifier_sha256 text NOT NULL CHECK(verifier_sha256~'^[a-f0-9]{64}$'),
 process_sha256 text NOT NULL CHECK(process_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,slot_id) REFERENCES campaign_private.private_grade_artifact_slots(project_id,id),
 FOREIGN KEY(project_id,frame_id) REFERENCES campaign_private.private_grade_frames(project_id,id));
CREATE TABLE campaign_private.private_result_originals(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,intent_id uuid NOT NULL UNIQUE,
 raw_bundle bytea NOT NULL CHECK(octet_length(raw_bundle) BETWEEN 1 AND 1048576),
 raw_sha256 text NOT NULL CHECK(raw_sha256=encode(sha256(raw_bundle),'hex')),
 verifier_raw bytea NOT NULL CHECK(octet_length(verifier_raw) BETWEEN 1 AND 1048576),
 verifier_sha256 text NOT NULL CHECK(verifier_sha256=encode(sha256(verifier_raw),'hex')),
 process_raw bytea NOT NULL CHECK(octet_length(process_raw) BETWEEN 1 AND 1048576),
 process_sha256 text NOT NULL CHECK(process_sha256=encode(sha256(process_raw),'hex')),
 attestation_header text NOT NULL CHECK(octet_length(attestation_header) BETWEEN 1 AND 4096),
 grade_status text NOT NULL CHECK(grade_status IN('passed','failed','unscored')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,intent_id) REFERENCES campaign_private.private_result_intents(project_id,id),
 CHECK(octet_length(verifier_raw)+octet_length(process_raw)<=octet_length(raw_bundle)));
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['private_grade_artifact_slots','private_grade_frames','private_result_intents','private_result_originals'] LOOP
  EXECUTE format('ALTER TABLE campaign_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE campaign_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON campaign_private.%I FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer',t);
  EXECUTE format('GRANT SELECT,INSERT ON campaign_private.%I TO anvil_private_grade_owner',t);
  EXECUTE format('CREATE POLICY private_grade_read ON campaign_private.%I FOR SELECT TO anvil_private_grade_owner USING(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',t);
  EXECUTE format('CREATE POLICY private_grade_append ON campaign_private.%I FOR INSERT TO anvil_private_grade_owner WITH CHECK(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON campaign_private.%I FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION campaign_private.capture_evidence_quota() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE used bigint;BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR NEW.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid
 THEN RAISE EXCEPTION 'original current capture quota context required';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.capture_combined_quota:'||NEW.project_id::text,0));
 SELECT coalesce(sum(byte_size),0) INTO used FROM(
  SELECT byte_size FROM campaign_private.capture_raw_intakes WHERE project_id=NEW.project_id
  UNION ALL SELECT byte_size FROM campaign_private.capture_actor_prompts WHERE project_id=NEW.project_id
  UNION ALL SELECT byte_size FROM campaign_private.capture_evidence_snapshots WHERE project_id=NEW.project_id
  UNION ALL SELECT byte_size FROM campaign_private.capture_evidence_manifests WHERE project_id=NEW.project_id
  UNION ALL SELECT byte_size FROM campaign_private.private_actor_slots WHERE project_id=NEW.project_id
  UNION ALL SELECT byte_size FROM campaign_private.private_grade_artifact_slots WHERE project_id=NEW.project_id
 ) charged;
 IF used+NEW.byte_size>536870912 THEN RAISE EXCEPTION 'original private capture quota exhausted';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER original_quota BEFORE INSERT ON campaign_private.private_grade_artifact_slots
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_evidence_quota();
CREATE FUNCTION campaign_private.reserve_private_grade_artifacts() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE q jsonb;limits jsonb;metadata text;frame bigint;result_wire text;value text;total bigint=0;BEGIN
 SELECT qualification_canonical::jsonb INTO q FROM campaign_private.capture_channel_qualifications
 WHERE project_id=NEW.project_id AND id=NEW.channel_qualification_id;
 IF q->'private_grade_transport' IS NULL THEN RETURN NEW;END IF;
 limits=q#>'{private_grade_transport,file_limits}';metadata=q#>>'{private_grade_transport,reply_metadata_limit}';
 result_wire=q#>>'{private_result_transport,wire_limit}';
 IF jsonb_typeof(limits) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(limits))<>4
 OR NOT limits ?& ARRAY['verifier-input.json','actor-output.json','private-evidence.json','evaluation-profile.json']
 OR metadata IS NULL OR metadata!~'^[0-9]{1,5}$' OR metadata::integer NOT BETWEEN 1 AND 32768
 OR q#>>'{private_result_transport,schema_version}' IS DISTINCT FROM 'anvil.marketing-private-result-transport-qualification.v1'
 OR result_wire IS NULL OR result_wire!~'^[0-9]{1,7}$' OR result_wire::integer NOT BETWEEN 1 AND 1048576
 THEN RAISE EXCEPTION 'original grade/result pre-provider capacity profile required';END IF;
 FOR value IN SELECT item.value FROM jsonb_each_text(limits) AS item LOOP
  IF value!~'^[0-9]{1,7}$' OR value::integer NOT BETWEEN 1 AND 1048576
  THEN RAISE EXCEPTION 'original complete private file limits required';END IF;
  total=total+value::integer;
 END LOOP;
 frame=4096+2*total+2*metadata::integer;
 IF frame>1048576 THEN RAISE EXCEPTION 'original complete grade frame cannot fit';END IF;
 INSERT INTO campaign_private.private_grade_artifact_slots(id,project_id,enrollment_id,kind,maximum_wire_bytes,byte_size)
 VALUES(gen_random_uuid(),NEW.project_id,NEW.id,'grade_frame',frame::integer,frame::integer+8192),
 (gen_random_uuid(),NEW.project_id,NEW.id,'verifier_result',result_wire::integer,2*result_wire::integer+8192);
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION campaign_private.reserve_private_grade_artifacts() FROM PUBLIC;
CREATE TRIGGER private_grade_reservations AFTER INSERT ON campaign_private.capture_enrollments
 FOR EACH ROW EXECUTE FUNCTION campaign_private.reserve_private_grade_artifacts();

CREATE FUNCTION marketing_runtime.record_private_grade_frame(p_enrollment uuid,p_manifest uuid,p_actor uuid,p_raw bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;slot campaign_private.private_grade_artifact_slots;
 identifier uuid=gen_random_uuid();BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR marketing_runtime.private_grade_read_authorized(p_enrollment,p_manifest) IS DISTINCT FROM true THEN RETURN NULL;END IF;
 SELECT * INTO slot FROM campaign_private.private_grade_artifact_slots WHERE project_id=project AND enrollment_id=p_enrollment AND kind='grade_frame';
 IF slot.id IS NULL OR p_raw IS NULL OR octet_length(p_raw) NOT BETWEEN 1 AND slot.maximum_wire_bytes
 OR NOT EXISTS(SELECT 1 FROM campaign_private.private_actor_originals a
  JOIN campaign_private.private_actor_intents i ON i.project_id=a.project_id AND i.id=a.intent_id
  JOIN campaign_private.private_actor_slots s ON s.project_id=i.project_id AND s.id=i.slot_id
  WHERE a.project_id=project AND a.id=p_actor AND s.enrollment_id=p_enrollment AND i.manifest_id=p_manifest)
 THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_grade_frame:'||slot.id::text,0));
 IF EXISTS(SELECT 1 FROM campaign_private.private_grade_frames v WHERE v.project_id=project AND v.slot_id=slot.id) THEN RETURN NULL;END IF;
 INSERT INTO campaign_private.private_grade_frames(id,project_id,slot_id,manifest_id,actor_original_id,raw_frame,raw_sha256)
 VALUES(identifier,project,slot.id,p_manifest,p_actor,p_raw,encode(sha256(p_raw),'hex'));
 RETURN jsonb_build_object('id',identifier,'enrollment_id',p_enrollment,'manifest_id',p_manifest,
 'raw_sha256',encode(sha256(p_raw),'hex'),'raw_bytes',octet_length(p_raw),'capture_accepted',false,'run_authority','not_granted');
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.record_private_grade_frame(uuid,uuid,uuid,bytea) FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.record_private_grade_frame(uuid,uuid,uuid,bytea) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_grade_frame(p_enrollment uuid,p_manifest uuid)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT jsonb_build_object('id',v.id,'enrollment_id',e.id,'manifest_id',v.manifest_id,
 'raw_utf8',convert_from(v.raw_frame,'UTF8'),'raw_sha256',v.raw_sha256,'raw_bytes',octet_length(v.raw_frame))
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.private_grade_artifact_slots s ON s.project_id=e.project_id AND s.enrollment_id=e.id AND s.kind='grade_frame'
 JOIN campaign_private.private_grade_frames v ON v.project_id=e.project_id AND v.slot_id=s.id
 WHERE e.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND e.id=p_enrollment
 AND e.actor_id::text=current_setting('anvil.user',true) AND v.manifest_id=p_manifest
 AND marketing_runtime.private_actor_attestation_key(e.id) IS NOT NULL;
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_grade_frame(uuid,uuid) FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_grade_frame(uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_result_attestation_key(p_enrollment uuid)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT marketing_runtime.private_actor_attestation_key(e.id)||jsonb_build_object(
 'private_result_transport',q.qualification_canonical::jsonb->'private_result_transport')
 FROM campaign_private.capture_enrollments e JOIN campaign_private.capture_channel_qualifications q
 ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 WHERE e.id=p_enrollment AND marketing_runtime.private_actor_attestation_key(e.id) IS NOT NULL
 AND jsonb_typeof(q.qualification_canonical::jsonb->'private_result_transport')='object';
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_result_attestation_key(uuid) FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_result_attestation_key(uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.begin_private_result(p_enrollment uuid,p_manifest uuid,p_bytes integer,
 p_sha text,p_attestation text,p_frame text,p_verifier text,p_process text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;e campaign_private.capture_enrollments;
 slot campaign_private.private_grade_artifact_slots;frame campaign_private.private_grade_frames;
 metadata jsonb;identifier uuid=gen_random_uuid();BEGIN
 metadata=marketing_runtime.private_result_attestation_key(p_enrollment);
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_enrollment;
 IF e.id IS NULL OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true)
 OR metadata IS NULL OR metadata->>'manifest_id' IS DISTINCT FROM p_manifest::text
 OR current_setting('transaction_isolation')<>'read committed'
 OR p_bytes IS NULL OR p_bytes NOT BETWEEN 1 AND 1048576
 OR p_sha IS NULL OR p_sha!~'^[a-f0-9]{64}$' OR p_attestation IS NULL OR p_attestation!~'^[a-f0-9]{64}$'
 OR p_frame IS NULL OR p_frame!~'^[a-f0-9]{64}$' OR p_verifier IS NULL OR p_verifier!~'^[a-f0-9]{64}$'
 OR p_process IS NULL OR p_process!~'^[a-f0-9]{64}$' THEN RETURN NULL;END IF;
 SELECT * INTO slot FROM campaign_private.private_grade_artifact_slots
 WHERE project_id=project AND enrollment_id=e.id AND kind='verifier_result';
 SELECT v.* INTO frame FROM campaign_private.private_grade_frames v
 JOIN campaign_private.private_grade_artifact_slots s ON s.project_id=v.project_id AND s.id=v.slot_id
 WHERE v.project_id=project AND s.enrollment_id=e.id AND s.kind='grade_frame'
 AND v.manifest_id=p_manifest AND v.raw_sha256=p_frame;
 IF slot.id IS NULL OR frame.id IS NULL OR p_bytes>slot.maximum_wire_bytes THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_result:'||slot.id::text,0));
 IF EXISTS(SELECT 1 FROM campaign_private.private_result_intents i WHERE i.project_id=project AND i.slot_id=slot.id)
 THEN RETURN NULL;END IF;
 INSERT INTO campaign_private.private_result_intents(id,project_id,slot_id,frame_id,wire_bytes,wire_sha256,
 attestation_sha256,verifier_sha256,process_sha256)
 VALUES(identifier,project,slot.id,frame.id,p_bytes,p_sha,p_attestation,p_verifier,p_process);
 RETURN jsonb_build_object('intent_id',identifier,'enrollment_id',e.id,'manifest_id',p_manifest,
 'request_sha256',e.request_sha256,'operation_nonce',e.operation_nonce,'expires_at',e.expires_at,
 'scope',e.scope,'wire_bytes',p_bytes,'wire_sha256',p_sha,'grade_frame_sha256',frame.raw_sha256,
 'capture_accepted',false,'native_qualified',false,'run_authority','not_granted');
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.begin_private_result(uuid,uuid,integer,text,text,text,text,text)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.begin_private_result(uuid,uuid,integer,text,text,text,text,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.retain_private_result(p_intent uuid,p_raw bytea,p_verifier bytea,
 p_process bytea,p_header text,p_status text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;i campaign_private.private_result_intents;
 slot campaign_private.private_grade_artifact_slots;e campaign_private.capture_enrollments;
 frame campaign_private.private_grade_frames;identifier uuid=gen_random_uuid();BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN NULL;END IF;
 SELECT * INTO i FROM campaign_private.private_result_intents WHERE project_id=project AND id=p_intent;
 IF i.id IS NULL THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_result:'||i.slot_id::text,0));
 SELECT * INTO slot FROM campaign_private.private_grade_artifact_slots WHERE project_id=project AND id=i.slot_id;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=slot.enrollment_id;
 SELECT * INTO frame FROM campaign_private.private_grade_frames WHERE project_id=project AND id=i.frame_id;
 IF e.id IS NULL OR frame.id IS NULL OR slot.kind IS DISTINCT FROM 'verifier_result'
 OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true)
 OR marketing_runtime.private_result_attestation_key(e.id) IS NULL
 OR p_raw IS NULL OR p_verifier IS NULL OR p_process IS NULL OR p_header IS NULL
 OR octet_length(p_raw) IS DISTINCT FROM i.wire_bytes OR octet_length(p_raw)>slot.maximum_wire_bytes
 OR encode(sha256(p_raw),'hex') IS DISTINCT FROM i.wire_sha256
 OR encode(sha256(p_verifier),'hex') IS DISTINCT FROM i.verifier_sha256
 OR encode(sha256(p_process),'hex') IS DISTINCT FROM i.process_sha256
 OR octet_length(p_header) NOT BETWEEN 1 AND 4096
 OR encode(sha256(convert_to(p_header,'UTF8')),'hex') IS DISTINCT FROM i.attestation_sha256
 OR p_status IS NULL OR p_status NOT IN('passed','failed','unscored')
 OR EXISTS(SELECT 1 FROM campaign_private.private_result_originals r WHERE r.project_id=project AND r.intent_id=i.id)
 THEN RETURN NULL;END IF;
 INSERT INTO campaign_private.private_result_originals(id,project_id,intent_id,raw_bundle,raw_sha256,
 verifier_raw,verifier_sha256,process_raw,process_sha256,attestation_header,grade_status)
 VALUES(identifier,project,i.id,p_raw,i.wire_sha256,p_verifier,i.verifier_sha256,p_process,i.process_sha256,p_header,p_status);
 RETURN jsonb_build_object('schema_version','anvil.marketing-private-result-custody.v1','id',identifier,
 'enrollment_id',e.id,'manifest_id',frame.manifest_id,'grade_frame_sha256',frame.raw_sha256,
 'raw_sha256',i.wire_sha256,'raw_bytes',i.wire_bytes,'verifier_result_sha256',i.verifier_sha256,
 'process_receipt_sha256',i.process_sha256,'grade_status',p_status,
 'capture_accepted',false,'native_qualified',false,'run_authority','not_granted');
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.retain_private_result(uuid,bytea,bytea,bytea,text,text)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.retain_private_result(uuid,bytea,bytea,bytea,text,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_result_original(p_enrollment uuid,p_manifest uuid)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT jsonb_build_object('schema_version','anvil.marketing-private-result-original.v1','id',r.id,
 'enrollment_id',e.id,'manifest_id',f.manifest_id,'grade_frame_sha256',f.raw_sha256,
 'raw_utf8',convert_from(r.raw_bundle,'UTF8'),'raw_sha256',r.raw_sha256,'raw_bytes',i.wire_bytes,
 'verifier_utf8',convert_from(r.verifier_raw,'UTF8'),'verifier_result_sha256',r.verifier_sha256,
 'process_utf8',convert_from(r.process_raw,'UTF8'),'process_receipt_sha256',r.process_sha256,
 'attestation_header',r.attestation_header,'grade_status',r.grade_status,
 'capture_accepted',false,'native_qualified',false,'run_authority','not_granted')
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.private_grade_artifact_slots s ON s.project_id=e.project_id AND s.enrollment_id=e.id AND s.kind='verifier_result'
 JOIN campaign_private.private_result_intents i ON i.project_id=e.project_id AND i.slot_id=s.id
 JOIN campaign_private.private_grade_frames f ON f.project_id=e.project_id AND f.id=i.frame_id
 JOIN campaign_private.private_result_originals r ON r.project_id=e.project_id AND r.intent_id=i.id
 WHERE e.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND e.id=p_enrollment
 AND e.actor_id::text=current_setting('anvil.user',true) AND f.manifest_id=p_manifest
 AND marketing_runtime.private_result_attestation_key(e.id) IS NOT NULL;
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_result_original(uuid,uuid)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_result_original(uuid,uuid) TO anvil_app;

-- Preserve the original public capacity shape. Private successor observation
-- now also requires BOTH pre-provider artifact slots from that same enrollment.
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
GRANT CREATE ON SCHEMA marketing_runtime,campaign_private TO anvil_private_grade_owner;
ALTER FUNCTION campaign_private.reserve_private_grade_artifacts() OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.record_private_grade_frame(uuid,uuid,uuid,bytea) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_grade_frame(uuid,uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_result_attestation_key(uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.begin_private_result(uuid,uuid,integer,text,text,text,text,text) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.retain_private_result(uuid,bytea,bytea,bytea,text,text) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_result_original(uuid,uuid) OWNER TO anvil_private_grade_owner;
REVOKE CREATE ON SCHEMA marketing_runtime,campaign_private FROM anvil_private_grade_owner;
INSERT INTO anvil.schema_versions(version) VALUES(123);
