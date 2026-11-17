-- SOURCE PROPOSAL: authenticated private raw intake, NOT qualified capture or
-- successful finish. No channel/enrollment/qualification rows are seeded.
CREATE TABLE campaign_private.capture_channel_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 auth_kind text NOT NULL CHECK(auth_kind='operator_attested_root_peer_v1'),
 subject text NOT NULL,account_email text,
 runtime_allowlist_id uuid NOT NULL,
 qualification_canonical text NOT NULL CHECK(octet_length(qualification_canonical) BETWEEN 1 AND 1048576),
 qualification_sha256 text NOT NULL CHECK(qualification_sha256=encode(sha256(convert_to(qualification_canonical,'UTF8')),'hex')),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,runtime_allowlist_id) REFERENCES anvil.runtime_role_allowlist(project_id,id),
 UNIQUE(project_id,id),CHECK(expires_at>created_at AND expires_at<='2026-12-11T05:48:04Z'),
 CHECK(subject~'^[a-f0-9]{64}$' AND account_email IS NULL));
CREATE TABLE campaign_private.capture_channel_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL UNIQUE,
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,qualification_id) REFERENCES campaign_private.capture_channel_qualifications(project_id,id));
CREATE TABLE campaign_private.capture_enrollments(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,actor_id uuid NOT NULL REFERENCES anvil.users(id),
 job_id uuid NOT NULL REFERENCES anvil.jobs(id),plan_id uuid NOT NULL,
 channel_qualification_id uuid NOT NULL,request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),
 operation_nonce text NOT NULL CHECK(operation_nonce~'^[a-f0-9]{64}$'),
 attestation_public_key_hex text NOT NULL UNIQUE CHECK(attestation_public_key_hex~'^[a-f0-9]{64}$'),
 attester_boot_id uuid NOT NULL,attester_profile_sha256 text NOT NULL CHECK(attester_profile_sha256~'^[a-f0-9]{64}$'),
 body_schema text NOT NULL CHECK(body_schema IN('anvil.marketing-native-capture-submission.v1','anvil.marketing-native-capture-submission.v2')),
 wire_limit integer NOT NULL CHECK(wire_limit BETWEEN 1 AND 1048576),
 original_canonical text NOT NULL CHECK(octet_length(original_canonical) BETWEEN 1 AND 16777216),
 original_sha256 text NOT NULL CHECK(original_sha256=encode(sha256(convert_to(original_canonical,'UTF8')),'hex')),
 scope jsonb NOT NULL CHECK(jsonb_typeof(scope)='object' AND octet_length(scope::text)<=8192),
 document_limits jsonb NOT NULL CHECK(jsonb_typeof(document_limits)='object' AND octet_length(document_limits::text)<=4096),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES campaign_private.world_sessions(project_id,plan_id),
 FOREIGN KEY(project_id,channel_qualification_id) REFERENCES campaign_private.capture_channel_qualifications(project_id,id),
 UNIQUE(project_id,id),UNIQUE(project_id,job_id,plan_id),UNIQUE(project_id,operation_nonce),
 CHECK(expires_at>created_at AND expires_at<='2026-12-11T05:48:04Z'));
CREATE TABLE campaign_private.capture_enrollment_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,enrollment_id uuid NOT NULL UNIQUE,
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,enrollment_id) REFERENCES campaign_private.capture_enrollments(project_id,id));
CREATE TABLE campaign_private.capture_intents(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,enrollment_id uuid NOT NULL UNIQUE,
 auth_kind text NOT NULL,subject text NOT NULL,account_email text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,enrollment_id) REFERENCES campaign_private.capture_enrollments(project_id,id),UNIQUE(project_id,id));
CREATE TABLE campaign_private.capture_raw_intakes(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,intent_id uuid NOT NULL UNIQUE,enrollment_id uuid NOT NULL UNIQUE,
 raw_wire bytea NOT NULL CHECK(octet_length(raw_wire)<=1048576),
 raw_sha256 text NOT NULL CHECK(raw_sha256=encode(sha256(raw_wire),'hex')),
 attestation_header text NOT NULL CHECK(octet_length(attestation_header) BETWEEN 1 AND 4096
  AND attestation_header~'^v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$'),
 attestation_sha256 text NOT NULL CHECK(attestation_sha256=encode(sha256(convert_to(attestation_header,'UTF8')),'hex')),
 verification_key_snapshot jsonb NOT NULL CHECK(jsonb_typeof(verification_key_snapshot)='object'
  AND octet_length(verification_key_snapshot::text)<=16384),
 decoded_documents jsonb NOT NULL CHECK(jsonb_typeof(decoded_documents)='object' AND octet_length(decoded_documents::text)<=1048576),
 classification text NOT NULL CHECK(classification IN('raw_received_unqualified','invalid_submission','transport_unknown')),
 byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 2117632),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,intent_id) REFERENCES campaign_private.capture_intents(project_id,id),
 FOREIGN KEY(project_id,enrollment_id) REFERENCES campaign_private.capture_enrollments(project_id,id));
DO $$DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['capture_channel_qualifications','capture_channel_revocations','capture_enrollments',
 'capture_enrollment_revocations','capture_intents','capture_raw_intakes'] LOOP
  EXECUTE format('ALTER TABLE campaign_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE campaign_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON campaign_private.%I FROM PUBLIC,anvil_app,anvil_golden_scheduler,anvil_golden_grader',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;

CREATE FUNCTION campaign_private.capture_registry_quota_guard() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE used bigint;size bigint;BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_quota:'||TG_TABLE_NAME||':'||NEW.project_id::text,0));
 IF TG_TABLE_NAME='capture_enrollments' THEN
  SELECT coalesce(sum(octet_length(original_canonical)+2048),0) INTO used FROM campaign_private.capture_enrollments WHERE project_id=NEW.project_id;
  size=octet_length(NEW.original_canonical)+2048;
 ELSE
  SELECT coalesce(sum(octet_length(qualification_canonical)+2048),0) INTO used FROM campaign_private.capture_channel_qualifications WHERE project_id=NEW.project_id;
  size=octet_length(NEW.qualification_canonical)+2048;
 END IF;
 IF used+size>536870912 THEN RAISE EXCEPTION 'private native capture registry quota exhausted';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER quota_guard BEFORE INSERT ON campaign_private.capture_enrollments
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_registry_quota_guard();
CREATE TRIGGER quota_guard BEFORE INSERT ON campaign_private.capture_channel_qualifications
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_registry_quota_guard();

CREATE FUNCTION campaign_private.capture_enrollment_guard() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM campaign_private.capture_channel_qualifications q
 JOIN anvil.runtime_role_allowlist a ON a.project_id=q.project_id AND a.id=q.runtime_allowlist_id
 JOIN anvil.harbor_agent_plans p ON p.project_id=NEW.project_id AND p.id=NEW.plan_id
 JOIN anvil.harbor_checks h ON h.project_id=p.project_id AND h.id=p.check_id
 WHERE q.project_id=NEW.project_id AND q.id=NEW.channel_qualification_id AND q.subject=NEW.attester_profile_sha256
 AND a.role='golden-native-coordinator' AND p.created_by=NEW.actor_id AND h.created_by=NEW.actor_id AND h.started_at IS NOT NULL
 AND p.config->>'marketing_paid'='true' AND coalesce(p.config->>'golden_kyc_paid','false')<>'true'
 AND jsonb_typeof(p.config->'episode_timeout_seconds')='number'
 AND (p.config->>'episode_timeout_seconds')::integer BETWEEN 1 AND 600
 AND EXISTS(SELECT 1 FROM anvil.jobs j WHERE j.project_id=NEW.project_id AND j.id=NEW.job_id
 AND j.target_id=p.check_id AND j.kind='benchmark_marketing_paid')
 AND NEW.expires_at<=least(q.expires_at,a.expires_at,h.started_at+((p.config->>'episode_timeout_seconds')||' seconds')::interval,
 '2026-12-11T05:48:04Z'::timestamptz)) THEN RAISE EXCEPTION 'original native capture scope or server deadline changed';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER original_scope BEFORE INSERT ON campaign_private.capture_enrollments
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_enrollment_guard();

-- Only operator custody can create independent channel qualifications and
-- original-operation enrollments. OIDC or peer authentication alone is not
-- authorization and these records do not qualify whole-actor/capture proof.
CREATE FUNCTION marketing_runtime.capture_enrollment_scope(p_id uuid,p_kind text,p_subject text,p_email text)
 RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('project_id',e.project_id,'actor_id',e.actor_id)
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.capture_channel_qualifications q ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 JOIN anvil.runtime_role_allowlist a ON a.project_id=q.project_id AND a.id=q.runtime_allowlist_id
 WHERE e.id=p_id AND q.auth_kind=p_kind AND q.subject=p_subject AND q.account_email IS NOT DISTINCT FROM p_email
 AND q.subject=e.attester_profile_sha256
 AND a.role='golden-native-coordinator' AND a.expires_at>clock_timestamp()
 AND q.expires_at>clock_timestamp() AND e.expires_at>clock_timestamp() AND clock_timestamp()<'2026-12-11T05:48:04Z'
 AND NOT EXISTS(SELECT 1 FROM anvil.runtime_role_allowlist_revocations x WHERE x.allowlist_id=a.id)
 AND NOT EXISTS(SELECT 1 FROM campaign_private.capture_channel_revocations x WHERE x.qualification_id=q.id)
 AND NOT EXISTS(SELECT 1 FROM campaign_private.capture_enrollment_revocations x WHERE x.enrollment_id=e.id);
$$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_enrollment_scope(uuid,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_enrollment_scope(uuid,text,text,text) TO anvil_app;

-- Public verification material only; possession of an enrollment UUID/public
-- key is not authentication. No private key, raw context or operator issuer is
-- available through this lookup. Actual enrollment/isolation is not seeded.
CREATE FUNCTION marketing_runtime.capture_attestation_key(p_id uuid)
 RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('enrollment_id',e.id,'request_sha256',e.request_sha256,'operation_nonce',e.operation_nonce,
 'boot_id',e.attester_boot_id,'profile_sha256',e.attester_profile_sha256,'producer_qualification_sha256',q.qualification_sha256,
 'public_key_hex',e.attestation_public_key_hex,'expires_at',e.expires_at,'document_limits',e.document_limits,
 'body_schema',e.body_schema,'wire_limit',e.wire_limit)
 FROM campaign_private.capture_enrollments e JOIN campaign_private.capture_channel_qualifications q
 ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 WHERE e.id=p_id AND q.auth_kind='operator_attested_root_peer_v1' AND q.subject=e.attester_profile_sha256
 AND e.attestation_public_key_hex IS NOT NULL AND e.attester_boot_id IS NOT NULL
 AND marketing_runtime.capture_enrollment_scope(e.id,q.auth_kind,q.subject,NULL) IS NOT NULL;
$$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_attestation_key(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_attestation_key(uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.capture_plan_preflight(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('enrollment_id',e.id,'request_sha256',e.request_sha256,'operation_nonce',e.operation_nonce,
 'document_limits',e.document_limits,'body_schema',e.body_schema,'wire_limit',e.wire_limit,
 'scope',e.scope,'project_id',e.project_id,'job_id',e.job_id,'plan_id',e.plan_id)
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.capture_channel_qualifications q ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 JOIN campaign_private.world_sessions s ON s.project_id=e.project_id AND s.plan_id=e.plan_id
 JOIN anvil.jobs j ON j.project_id=e.project_id AND j.id=e.job_id
 JOIN anvil.harbor_agent_plans p ON p.project_id=e.project_id AND p.id=e.plan_id
 JOIN anvil.harbor_checks h ON h.project_id=p.project_id AND h.id=p.check_id
 WHERE e.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND e.actor_id=nullif(current_setting('anvil.user',true),'')::uuid
 AND e.job_id=p_job AND e.plan_id=p_plan AND j.lease_token=p_lease
 AND s.job_id=p_job AND s.lease_sha256=encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
 AND e.scope->>'project_id'=e.project_id::text AND e.scope->>'job_id'=e.job_id::text AND e.scope->>'plan_id'=e.plan_id::text
 AND e.scope->>'world_binding_id'=s.world_binding_id::text AND e.scope->>'world_binding_sha256'=s.world_binding_sha256
 AND e.scope->>'episode_id'=s.episode_id::text AND e.scope->>'generation'=s.generation::text
 AND e.scope->>'execution_sha256'=s.attachment->>'execution_sha256' AND e.scope->>'lease_sha256'=s.lease_sha256
 AND EXISTS(SELECT 1 FROM campaign_private.world_qualifications wq WHERE wq.project_id=e.project_id AND wq.id=s.qualification_id
 AND wq.receipt_sha256=e.scope->>'source_qualification_sha256')
 AND h.started_at IS NOT NULL AND h.state='running' AND NOT h.cancel_requested
 AND clock_timestamp()<h.started_at+((p.config->>'episode_timeout_seconds')||' seconds')::interval
 AND e.expires_at<=h.started_at+((p.config->>'episode_timeout_seconds')||' seconds')::interval
 AND marketing_runtime.capture_enrollment_scope(e.id,q.auth_kind,q.subject,q.account_email) IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM campaign_private.capture_intents i WHERE i.enrollment_id=e.id);
$$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_plan_preflight(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_plan_preflight(uuid,uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.begin_capture_intake(p_id uuid,p_kind text,p_subject text,p_email text,p_intent uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE e campaign_private.capture_enrollments;s campaign_private.world_sessions;scope_value jsonb;project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RETURN NULL;END IF;
 scope_value=marketing_runtime.capture_enrollment_scope(p_id,p_kind,p_subject,p_email);
 IF scope_value IS NULL OR scope_value->>'project_id' IS DISTINCT FROM project::text
 OR scope_value->>'actor_id' IS DISTINCT FROM current_setting('anvil.user',true) THEN RETURN NULL;END IF;
 PERFORM 1 FROM anvil.projects WHERE id=project FOR KEY SHARE;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=p_id;
 IF NOT FOUND THEN RETURN NULL;END IF;
 PERFORM 1 FROM anvil.workspace_execution_groups g JOIN anvil.harbor_agent_plans p
 ON p.project_id=g.project_id AND (p.config->>'workspace_execution_group')::uuid=g.id
 WHERE p.project_id=project AND p.id=e.plan_id FOR UPDATE OF g;
 IF NOT FOUND THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('marketing-world-stop:'||project::text||':'||e.plan_id::text,0));
 SELECT * INTO s FROM campaign_private.world_sessions WHERE project_id=project AND plan_id=e.plan_id FOR UPDATE;
 IF NOT FOUND OR s.job_id<>e.job_id OR e.scope->>'project_id' IS DISTINCT FROM project::text
 OR e.scope->>'job_id' IS DISTINCT FROM e.job_id::text OR e.scope->>'plan_id' IS DISTINCT FROM e.plan_id::text
 OR e.scope->>'world_binding_id' IS DISTINCT FROM s.world_binding_id::text
 OR e.scope->>'world_binding_sha256' IS DISTINCT FROM s.world_binding_sha256
 OR e.scope->>'episode_id' IS DISTINCT FROM s.episode_id::text OR e.scope->>'generation' IS DISTINCT FROM s.generation::text
 OR e.scope->>'execution_sha256' IS DISTINCT FROM s.attachment->>'execution_sha256'
 OR e.scope->>'lease_sha256' IS DISTINCT FROM s.lease_sha256
 OR NOT EXISTS(SELECT 1 FROM campaign_private.world_qualifications q WHERE q.project_id=project AND q.id=s.qualification_id
 AND q.receipt_sha256=e.scope->>'source_qualification_sha256') THEN RETURN NULL;END IF;
 -- Durable exclusive capture intent precedes reading/parsing the HTTP body.
 -- Conflicting/partial/lost outcomes do not authorize another intake.
 IF marketing_runtime.capture_enrollment_scope(p_id,p_kind,p_subject,p_email) IS NULL THEN RETURN NULL;END IF;
 INSERT INTO campaign_private.capture_intents(id,project_id,enrollment_id,auth_kind,subject,account_email)
 VALUES(p_intent,project,p_id,p_kind,p_subject,p_email);
 RETURN jsonb_build_object('intent_id',p_intent,'enrollment_id',e.id,'project_id',e.project_id,'actor_id',e.actor_id,
 'job_id',e.job_id,'plan_id',e.plan_id,'request_sha256',e.request_sha256,'operation_nonce',e.operation_nonce,
 'original_canonical',e.original_canonical,'original_sha256',e.original_sha256,'scope',e.scope,
 'document_limits',e.document_limits,'expires_at',e.expires_at,'body_schema',e.body_schema,'wire_limit',e.wire_limit);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.begin_capture_intake(uuid,text,text,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.begin_capture_intake(uuid,text,text,text,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.store_capture_raw_intake(p_intent uuid,p_receipt uuid,p_wire bytea,p_hash text,p_documents text,p_class text,p_attestation text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE i campaign_private.capture_intents;e campaign_private.capture_enrollments;
 q campaign_private.capture_channel_qualifications;d jsonb;k jsonb;size integer;used bigint;
 project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' OR p_wire IS NULL OR octet_length(p_wire)>1048576
 OR p_hash IS DISTINCT FROM encode(sha256(p_wire),'hex') OR p_documents IS NULL OR octet_length(p_documents)>1048576
 OR p_attestation IS NULL OR octet_length(p_attestation) NOT BETWEEN 1 AND 4096
 OR p_attestation!~'^v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$'
 OR p_class IS NULL OR p_class NOT IN('raw_received_unqualified','invalid_submission','transport_unknown') THEN RETURN false;END IF;
 SELECT * INTO i FROM campaign_private.capture_intents WHERE project_id=project AND id=p_intent FOR UPDATE;
 IF NOT FOUND THEN RETURN false;END IF;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=i.enrollment_id;
 IF NOT FOUND OR e.actor_id::text IS DISTINCT FROM current_setting('anvil.user',true) THEN RETURN false;END IF;
 SELECT * INTO q FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=e.channel_qualification_id;
 IF NOT FOUND THEN RETURN false;END IF;
 -- Immutable server-owned original references and public material, never a
 -- client supplied key/scope snapshot. Retain even on partial transport after
 -- expiry, for independent signature verification; not acceptance authority.
 k=jsonb_build_object('enrollment_id',e.id,'enrollment_original_sha256',e.original_sha256,
 'channel_qualification_id',q.id,'producer_qualification_sha256',q.qualification_sha256,
 'public_key_hex',e.attestation_public_key_hex,'boot_id',e.attester_boot_id,
 'profile_sha256',e.attester_profile_sha256,'request_sha256',e.request_sha256,
 'operation_nonce',e.operation_nonce,'scope',e.scope,'expires_at',e.expires_at,
 'body_schema',e.body_schema,'wire_limit',e.wire_limit,'document_limits',e.document_limits);
 -- Diagnostic completion of an already committed original intent only. It may
 -- retain transport-failure bytes after expiry; it can never grant acceptance,
 -- release funds, create work, repair a receipt or authorize replay.
 d=p_documents::jsonb;IF jsonb_typeof(d) IS DISTINCT FROM 'object' THEN RETURN false;END IF;
 size=greatest(1,octet_length(p_wire)+octet_length(d::text)+octet_length(p_attestation)+octet_length(k::text));
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_quota:capture_raw_intakes:'||project::text,0));
 SELECT coalesce(sum(byte_size),0) INTO used FROM campaign_private.capture_raw_intakes WHERE project_id=project;
 IF used+size>536870912 THEN RAISE EXCEPTION 'private native capture intake quota exhausted';END IF;
 INSERT INTO campaign_private.capture_raw_intakes(id,project_id,intent_id,enrollment_id,raw_wire,raw_sha256,
 attestation_header,attestation_sha256,verification_key_snapshot,decoded_documents,classification,byte_size)
 VALUES(p_receipt,project,p_intent,i.enrollment_id,p_wire,p_hash,p_attestation,
 encode(sha256(convert_to(p_attestation,'UTF8')),'hex'),k,d,p_class,size);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.store_capture_raw_intake(uuid,uuid,bytea,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.store_capture_raw_intake(uuid,uuid,bytea,text,text,text,text) TO anvil_app;

-- No accepted-capture table/function or success-finish grant is supplied by raw
-- transport custody. Whole-actor shutdown and capture-seal validators are a
-- separate jointly reviewed implementation and actual qualification boundary.
