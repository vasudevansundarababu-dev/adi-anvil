-- Source-only own-actor custody. No routes enabled, artifacts seeded, keys or
-- native/process qualification granted. Reserve original capacity before SDK.
CREATE TABLE campaign_private.private_actor_slots(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,enrollment_id uuid NOT NULL UNIQUE,
 maximum_bytes integer NOT NULL CHECK(maximum_bytes BETWEEN 1 AND 1048576),
 byte_size integer NOT NULL CHECK(byte_size=maximum_bytes+8192),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,enrollment_id) REFERENCES campaign_private.capture_enrollments(project_id,id));
CREATE TABLE campaign_private.private_actor_intents(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,slot_id uuid NOT NULL UNIQUE,manifest_id uuid NOT NULL,
 wire_bytes integer NOT NULL CHECK(wire_bytes BETWEEN 1 AND 1048576),wire_sha256 text NOT NULL CHECK(wire_sha256~'^[a-f0-9]{64}$'),
 attestation_sha256 text NOT NULL CHECK(attestation_sha256~'^[a-f0-9]{64}$'),
 actor_stop_sha256 text NOT NULL CHECK(actor_stop_sha256~'^[a-f0-9]{64}$'),
 collection_receipt_sha256 text NOT NULL CHECK(collection_receipt_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,slot_id) REFERENCES campaign_private.private_actor_slots(project_id,id),
 FOREIGN KEY(project_id,manifest_id) REFERENCES campaign_private.capture_evidence_slots(project_id,id));
CREATE TABLE campaign_private.private_actor_originals(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,intent_id uuid NOT NULL UNIQUE,
 raw_body bytea NOT NULL CHECK(octet_length(raw_body) BETWEEN 1 AND 1048576),
 raw_sha256 text NOT NULL CHECK(raw_sha256=encode(sha256(raw_body),'hex')),
 attestation_header text NOT NULL CHECK(octet_length(attestation_header) BETWEEN 1 AND 4096),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,intent_id) REFERENCES campaign_private.private_actor_intents(project_id,id));
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['private_actor_slots','private_actor_intents','private_actor_originals'] LOOP
  EXECUTE format('ALTER TABLE campaign_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE campaign_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON campaign_private.%I FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON campaign_private.%I FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
-- All existing and new writers share the SAME original512MiB quota and lock.
-- Slot charges reserve raw body+header/metadata before SDK; later actual rows
-- consume that reservation and are not charged twice or given another allowance.
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
 ) charged;
 IF used+NEW.byte_size>536870912 THEN RAISE EXCEPTION 'original private capture quota exhausted';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER original_quota BEFORE INSERT ON campaign_private.private_actor_slots
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_evidence_quota();
CREATE FUNCTION campaign_private.reserve_private_actor_slot() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE q jsonb;maximum text;BEGIN
 SELECT qualification_canonical::jsonb INTO q FROM campaign_private.capture_channel_qualifications
 WHERE project_id=NEW.project_id AND id=NEW.channel_qualification_id;
 IF q->'private_grade_transport' IS NULL AND q->'private_actor_transport' IS NULL THEN RETURN NEW;END IF;
 maximum=q#>>'{private_actor_transport,wire_limit}';
 IF q#>>'{private_actor_transport,schema_version}' IS DISTINCT FROM 'anvil.marketing-private-actor-transport-qualification.v1'
 OR q#>>'{private_grade_transport,schema_version}' IS DISTINCT FROM 'anvil.marketing-private-grade-transport-qualification.v1'
 OR maximum IS NULL OR maximum!~'^[0-9]{1,7}$' OR maximum::integer NOT BETWEEN 1 AND 1048576
 OR q#>>'{private_grade_transport,file_limits,actor-output.json}' IS NULL
 OR q#>>'{private_grade_transport,file_limits,actor-output.json}'!~'^[0-9]{1,7}$'
 OR maximum::integer>(q#>>'{private_grade_transport,file_limits,actor-output.json}')::integer
 THEN RAISE EXCEPTION 'exact private actor pre-SDK reservation profile required';END IF;
 INSERT INTO campaign_private.private_actor_slots(id,project_id,enrollment_id,maximum_bytes,byte_size)
 VALUES(gen_random_uuid(),NEW.project_id,NEW.id,maximum::integer,maximum::integer+8192);
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION campaign_private.reserve_private_actor_slot() FROM PUBLIC;
CREATE TRIGGER private_actor_reservation AFTER INSERT ON campaign_private.capture_enrollments
 FOR EACH ROW EXECUTE FUNCTION campaign_private.reserve_private_actor_slot();

CREATE FUNCTION marketing_runtime.private_actor_attestation_key(p_enrollment uuid)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT marketing_runtime.private_grade_attestation_key(e.id)||jsonb_build_object(
 'private_actor_transport',q.qualification_canonical::jsonb->'private_actor_transport',
 'actor_slot_id',slot.id,'actor_maximum_bytes',slot.maximum_bytes)
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.capture_channel_qualifications q ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 JOIN campaign_private.private_actor_slots slot ON slot.project_id=e.project_id AND slot.enrollment_id=e.id
 WHERE e.id=p_enrollment AND marketing_runtime.private_grade_attestation_key(e.id) IS NOT NULL
 AND jsonb_typeof(q.qualification_canonical::jsonb->'private_actor_transport')='object';
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_actor_attestation_key(uuid) FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_actor_attestation_key(uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.begin_private_actor(p_enrollment uuid,p_manifest uuid,p_bytes integer,
 p_sha text,p_attestation text,p_stop text,p_collection text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;e campaign_private.capture_enrollments;
 slot campaign_private.private_actor_slots;metadata jsonb;identifier uuid=gen_random_uuid();BEGIN
 metadata=marketing_runtime.private_actor_attestation_key(p_enrollment);
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_enrollment;
 IF e.id IS NULL OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true)
 OR metadata IS NULL OR metadata->>'manifest_id' IS DISTINCT FROM p_manifest::text
 OR current_setting('transaction_isolation')<>'read committed'
 OR p_bytes IS NULL OR p_bytes NOT BETWEEN 1 AND 1048576 OR p_sha IS NULL OR p_sha!~'^[a-f0-9]{64}$'
 OR p_attestation IS NULL OR p_attestation!~'^[a-f0-9]{64}$'
 OR p_stop IS NULL OR p_stop!~'^[a-f0-9]{64}$' OR p_collection IS NULL OR p_collection!~'^[a-f0-9]{64}$'
 THEN RETURN NULL;END IF;
 SELECT * INTO slot FROM campaign_private.private_actor_slots WHERE project_id=project AND enrollment_id=e.id;
 IF slot.id IS NULL THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_actor:'||slot.id::text,0));
 IF slot.id IS NULL OR p_bytes>slot.maximum_bytes
 OR EXISTS(SELECT 1 FROM campaign_private.private_actor_intents i WHERE i.project_id=project AND i.slot_id=slot.id)
 THEN RETURN NULL;END IF;
 INSERT INTO campaign_private.private_actor_intents(id,project_id,slot_id,manifest_id,wire_bytes,wire_sha256,
 attestation_sha256,actor_stop_sha256,collection_receipt_sha256)
 VALUES(identifier,project,slot.id,p_manifest,p_bytes,p_sha,p_attestation,p_stop,p_collection);
 RETURN jsonb_build_object('intent_id',identifier,'enrollment_id',e.id,'manifest_id',p_manifest,
 'request_sha256',e.request_sha256,'operation_nonce',e.operation_nonce,'expires_at',e.expires_at,
 'scope',e.scope,'wire_bytes',p_bytes,'wire_sha256',p_sha,'capture_accepted',false);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.begin_private_actor(uuid,uuid,integer,text,text,text,text)
 FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.begin_private_actor(uuid,uuid,integer,text,text,text,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.retain_private_actor(p_intent uuid,p_raw bytea,p_header text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;i campaign_private.private_actor_intents;
 slot campaign_private.private_actor_slots;e campaign_private.capture_enrollments;identifier uuid=gen_random_uuid();BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN NULL;END IF;
 SELECT * INTO i FROM campaign_private.private_actor_intents WHERE project_id=project AND id=p_intent;
 IF i.id IS NULL THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_actor:'||i.slot_id::text,0));
 SELECT * INTO slot FROM campaign_private.private_actor_slots WHERE project_id=project AND id=i.slot_id;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=slot.enrollment_id;
 IF e.id IS NULL OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true)
 OR marketing_runtime.private_actor_attestation_key(e.id) IS NULL OR p_raw IS NULL OR p_header IS NULL
 OR octet_length(p_raw) IS DISTINCT FROM i.wire_bytes OR octet_length(p_raw)>slot.maximum_bytes
 OR encode(sha256(p_raw),'hex') IS DISTINCT FROM i.wire_sha256
 OR octet_length(p_header) NOT BETWEEN 1 AND 4096
 OR encode(sha256(convert_to(p_header,'UTF8')),'hex') IS DISTINCT FROM i.attestation_sha256
 OR EXISTS(SELECT 1 FROM campaign_private.private_actor_originals r WHERE r.project_id=project AND r.intent_id=i.id)
 THEN RETURN NULL;END IF;
 INSERT INTO campaign_private.private_actor_originals(id,project_id,intent_id,raw_body,raw_sha256,attestation_header)
 VALUES(identifier,project,i.id,p_raw,i.wire_sha256,p_header);
 RETURN jsonb_build_object('schema_version','anvil.marketing-private-actor-custody.v1','id',identifier,
 'enrollment_id',e.id,'manifest_id',i.manifest_id,'raw_sha256',i.wire_sha256,'raw_bytes',i.wire_bytes,
 'capture_accepted',false,'native_qualified',false,'run_authority','not_granted');
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.retain_private_actor(uuid,bytea,text) FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.retain_private_actor(uuid,bytea,text) TO anvil_app;

CREATE FUNCTION marketing_runtime.private_actor_original(p_enrollment uuid,p_manifest uuid)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT jsonb_build_object('schema_version','anvil.marketing-private-actor-original.v1','id',r.id,
 'enrollment_id',e.id,'manifest_id',i.manifest_id,'actor_stop_sha256',i.actor_stop_sha256,
 'collection_receipt_sha256',i.collection_receipt_sha256,'raw_utf8',convert_from(r.raw_body,'UTF8'),
 'raw_sha256',r.raw_sha256,'raw_bytes',i.wire_bytes,'attestation_header',r.attestation_header)
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.private_actor_slots slot ON slot.project_id=e.project_id AND slot.enrollment_id=e.id
 JOIN campaign_private.private_actor_intents i ON i.project_id=e.project_id AND i.slot_id=slot.id
 JOIN campaign_private.private_actor_originals r ON r.project_id=e.project_id AND r.intent_id=i.id
 WHERE e.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND e.id=p_enrollment AND i.manifest_id=p_manifest
 AND e.actor_id::text=current_setting('anvil.user',true) AND marketing_runtime.private_actor_attestation_key(e.id) IS NOT NULL;
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_actor_original(uuid,uuid) FROM PUBLIC,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_actor_original(uuid,uuid) TO anvil_app;
CREATE FUNCTION marketing_runtime.private_actor_slot_preflight(p_job uuid,p_lease uuid,p_plan uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE ctx jsonb;project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 e campaign_private.capture_enrollments;slot campaign_private.private_actor_slots;BEGIN
 IF current_setting('transaction_read_only')<>'on' OR current_setting('transaction_isolation')<>'read committed'
 OR pg_current_xact_id_if_assigned() IS NOT NULL THEN RETURN NULL;END IF;
 ctx=marketing_runtime.committed_attester_enrollment(p_job,p_lease,p_plan);
 IF ctx IS NULL THEN RETURN NULL;END IF;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=(ctx#>>'{enrollment,enrollment_id}')::uuid;
 SELECT * INTO slot FROM campaign_private.private_actor_slots WHERE project_id=project AND enrollment_id=e.id;
 IF slot.id IS NULL OR slot.byte_size<>slot.maximum_bytes+8192 THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('schema_version','anvil.marketing-private-actor-capacity.v1','id',slot.id,
 'enrollment_id',e.id,'scope',e.scope,'maximum_bytes',slot.maximum_bytes,
 'producer_qualification_sha256',ctx#>>'{enrollment,producer_qualification_sha256}',
 'expires_at',e.expires_at,'capture_accepted',false,'run_authority','not_granted');
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_actor_slot_preflight(uuid,uuid,uuid)
 FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION marketing_runtime.private_actor_slot_preflight(uuid,uuid,uuid) TO anvil_golden_scheduler;
-- Same isolated NOLOGIN owner as121. Explicit scoped reads/appends replace any
-- assumption that a deployment migration account can bypass FORCE RLS.
GRANT SELECT(project_id,byte_size) ON campaign_private.capture_raw_intakes TO anvil_private_grade_owner;
CREATE POLICY private_grade_quota_read ON campaign_private.capture_raw_intakes FOR SELECT TO anvil_private_grade_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['private_actor_slots','private_actor_intents','private_actor_originals'] LOOP
  EXECUTE format('GRANT SELECT,INSERT ON campaign_private.%I TO anvil_private_grade_owner',t);
  IF t='private_actor_slots' THEN
   EXECUTE format('CREATE POLICY private_grade_read ON campaign_private.%I FOR SELECT TO anvil_private_grade_owner USING(nullif(current_setting(''anvil.project'',true),'''') IS NULL OR project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',t);
  ELSE
   EXECUTE format('CREATE POLICY private_grade_read ON campaign_private.%I FOR SELECT TO anvil_private_grade_owner USING(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',t);
  END IF;
  EXECUTE format('CREATE POLICY private_grade_append ON campaign_private.%I FOR INSERT TO anvil_private_grade_owner WITH CHECK(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',t);
 END LOOP;
END $$;
GRANT EXECUTE ON FUNCTION marketing_runtime.committed_attester_enrollment(uuid,uuid,uuid) TO anvil_private_grade_owner;
GRANT CREATE ON SCHEMA campaign_private,marketing_runtime TO anvil_private_grade_owner;
ALTER FUNCTION campaign_private.capture_evidence_quota() OWNER TO anvil_private_grade_owner;
ALTER FUNCTION campaign_private.reserve_private_actor_slot() OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_actor_attestation_key(uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.begin_private_actor(uuid,uuid,integer,text,text,text,text) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.retain_private_actor(uuid,bytea,text) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_actor_original(uuid,uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_actor_slot_preflight(uuid,uuid,uuid) OWNER TO anvil_private_grade_owner;
REVOKE CREATE ON SCHEMA campaign_private,marketing_runtime FROM anvil_private_grade_owner;
INSERT INTO anvil.schema_versions(version) VALUES(122);
