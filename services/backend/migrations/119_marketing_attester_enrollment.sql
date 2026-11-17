-- Source-only public-key enrollment. No key, peer proof, channel qualification,
-- login, role membership, budget approval or actual operation is created.
DO $$ DECLARE r text;consumer text;BEGIN
 FOREACH r IN ARRAY ARRAY['anvil_capture_enrollment_owner','anvil_capture_registrar','anvil_capture_peer_writer'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
   EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',r);
  END IF;
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r AND
   (rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
  THEN RAISE EXCEPTION 'separate restricted capture operator roles required';END IF;
  FOREACH consumer IN ARRAY ARRAY['anvil_app','anvil_worker','anvil_golden_scheduler','anvil_golden_grader'] LOOP
   IF pg_has_role(consumer,r,'MEMBER') THEN RAISE EXCEPTION 'capture operator role must be separate';END IF;
  END LOOP;
 END LOOP;
 IF pg_has_role('anvil_capture_registrar','anvil_capture_enrollment_owner','MEMBER')
 OR pg_has_role('anvil_capture_peer_writer','anvil_capture_enrollment_owner','MEMBER')
 OR pg_has_role('anvil_capture_registrar','anvil_capture_peer_writer','MEMBER')
 OR pg_has_role('anvil_capture_peer_writer','anvil_capture_registrar','MEMBER')
 THEN RAISE EXCEPTION 'capture registrar cannot inherit internal owner';END IF;
END $$;
GRANT USAGE ON SCHEMA anvil,campaign_private,marketing_runtime TO anvil_capture_enrollment_owner;
GRANT USAGE ON SCHEMA marketing_runtime TO anvil_capture_registrar;
GRANT USAGE ON SCHEMA marketing_runtime TO anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION anvil.benchmark_is_admin(uuid,uuid),marketing_runtime.paid_job_current(uuid,uuid,uuid)
 TO anvil_capture_enrollment_owner;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_manifest_preflight(uuid,uuid,uuid)
 TO anvil_capture_enrollment_owner;

-- This is an independently produced operator fact, not a payload accepted from
-- the SDK, API, parent control or registrar. No INSERT grant is issued here.
CREATE TABLE campaign_private.capture_attester_peer_bindings(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 enrollment_id uuid NOT NULL UNIQUE,actor_id uuid NOT NULL REFERENCES anvil.users(id),
 job_id uuid NOT NULL,plan_id uuid NOT NULL,channel_qualification_id uuid NOT NULL,
 operation_nonce text NOT NULL CHECK(operation_nonce~'^[a-f0-9]{64}$'),
 public_key_hex text NOT NULL UNIQUE CHECK(public_key_hex~'^[a-f0-9]{64}$'),
 boot_id uuid NOT NULL,profile_sha256 text NOT NULL CHECK(profile_sha256~'^[a-f0-9]{64}$'),
 request_canonical text NOT NULL CHECK(octet_length(request_canonical) BETWEEN 2 AND 1048576),
 request_sha256 text NOT NULL CHECK(request_sha256=encode(sha256(convert_to(request_canonical,'UTF8')),'hex')),
 operation_canonical text NOT NULL CHECK(octet_length(operation_canonical) BETWEEN 2 AND 4096),
 operation_sha256 text NOT NULL CHECK(operation_sha256=encode(sha256(convert_to(operation_canonical,'UTF8')),'hex')),
 os_receipt_canonical text NOT NULL CHECK(octet_length(os_receipt_canonical) BETWEEN 2 AND 32768),
 os_receipt_sha256 text NOT NULL CHECK(os_receipt_sha256=encode(sha256(convert_to(os_receipt_canonical,'UTF8')),'hex')),
 peer_canonical text NOT NULL CHECK(octet_length(peer_canonical) BETWEEN 2 AND 16384),
 peer_sha256 text NOT NULL CHECK(peer_sha256=encode(sha256(convert_to(peer_canonical,'UTF8')),'hex')),
 original_scope jsonb NOT NULL CHECK(octet_length(original_scope::text)<=8192),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(project_id,id),UNIQUE(project_id,job_id,plan_id),UNIQUE(project_id,operation_nonce),
 FOREIGN KEY(project_id,plan_id) REFERENCES campaign_private.world_sessions(project_id,plan_id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.jobs(project_id,id),
 FOREIGN KEY(project_id,channel_qualification_id) REFERENCES campaign_private.capture_channel_qualifications(project_id,id),
 CHECK(expires_at>created_at AND expires_at<='2026-12-11T05:48:04Z')
);
ALTER TABLE campaign_private.capture_attester_peer_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.capture_attester_peer_bindings FORCE ROW LEVEL SECURITY;
REVOKE ALL ON campaign_private.capture_attester_peer_bindings FROM PUBLIC,anvil_app,anvil_worker,
 anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.capture_attester_peer_bindings
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON campaign_private.capture_attester_peer_bindings
 FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable();
CREATE TABLE campaign_private.capture_attester_peer_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,peer_binding_id uuid NOT NULL UNIQUE,
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,peer_binding_id) REFERENCES campaign_private.capture_attester_peer_bindings(project_id,id));
ALTER TABLE campaign_private.capture_attester_peer_revocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.capture_attester_peer_revocations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON campaign_private.capture_attester_peer_revocations FROM PUBLIC,anvil_app,anvil_worker,
 anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.capture_attester_peer_revocations
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

-- New peer bytes share the original enrollment registry ceiling/lock. Preserve
-- old enrollment/channel charges; reserve peer revocation metadata up front so
-- denial-only revocation never waits for fresh quota or positive-work approval.
CREATE OR REPLACE FUNCTION campaign_private.capture_registry_quota_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE used bigint;amount bigint;quota_kind text;BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 THEN RAISE EXCEPTION 'capture registry quota requires current read committed snapshot';END IF;
 IF NEW.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid
 THEN RAISE EXCEPTION 'original capture registry project context required';END IF;
 quota_kind=CASE WHEN TG_TABLE_NAME='capture_channel_qualifications' THEN TG_TABLE_NAME ELSE 'capture_enrollments' END;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.marketing.private_quota:'||quota_kind||':'||NEW.project_id::text,0));
 IF quota_kind='capture_enrollments' THEN
  SELECT coalesce(sum(size),0) INTO used FROM (
   SELECT octet_length(e.original_canonical)+2048 AS size FROM campaign_private.capture_enrollments e WHERE e.project_id=NEW.project_id
   UNION ALL SELECT octet_length(b.request_canonical)+octet_length(b.peer_canonical)+octet_length(b.original_scope::text)
    +octet_length(b.operation_canonical)+octet_length(b.os_receipt_canonical)+4096
    FROM campaign_private.capture_attester_peer_bindings b WHERE b.project_id=NEW.project_id) charged;
  IF TG_TABLE_NAME='capture_attester_peer_bindings' THEN
   amount=octet_length(NEW.request_canonical)+octet_length(NEW.peer_canonical)+octet_length(NEW.original_scope::text)
    +octet_length(NEW.operation_canonical)+octet_length(NEW.os_receipt_canonical)+4096;
  ELSE amount=octet_length(NEW.original_canonical)+2048;END IF;
 ELSE
  SELECT coalesce(sum(octet_length(q.qualification_canonical)+2048),0) INTO used
   FROM campaign_private.capture_channel_qualifications q WHERE q.project_id=NEW.project_id;
  amount=octet_length(NEW.qualification_canonical)+2048;
 END IF;
 IF used+amount>536870912 THEN RAISE EXCEPTION 'private native capture registry quota exhausted';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER quota_guard BEFORE INSERT ON campaign_private.capture_attester_peer_bindings
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_registry_quota_guard();

-- Fixed definer role has only scoped reads and the one target INSERT. It is not
-- granted to the registrar or any operational login. No general DML is exposed.
DO $$ DECLARE pair text[];s text;t text;BEGIN
 FOREACH pair SLICE 1 IN ARRAY ARRAY[
  ['campaign_private','capture_attester_peer_bindings'],['campaign_private','capture_attester_peer_revocations'],['campaign_private','capture_channel_qualifications'],
  ['campaign_private','capture_channel_revocations'],['campaign_private','capture_enrollments'],
  ['campaign_private','capture_enrollment_revocations'],['campaign_private','world_sessions'],
  ['campaign_private','world_qualifications'],['campaign_private','world_revocations'],
  ['anvil','runtime_role_allowlist'],['anvil','runtime_role_allowlist_revocations'],
  ['anvil','jobs'],['anvil','harbor_agent_plans'],['anvil','harbor_checks'],
  ['marketing_runtime','paid_turn_intents'],['marketing_runtime','paid_agent_bindings']] LOOP
  s=pair[1];t=pair[2];
  EXECUTE format('GRANT SELECT ON %I.%I TO anvil_capture_enrollment_owner',s,t);
  EXECUTE format('CREATE POLICY capture_issuer_read ON %I.%I FOR SELECT TO anvil_capture_enrollment_owner USING(project_id=nullif(current_setting(''anvil.project'',true),'''')::uuid)',s,t);
 END LOOP;
END $$;
GRANT INSERT ON campaign_private.capture_enrollments TO anvil_capture_enrollment_owner;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_manifest_preflight(uuid,uuid,uuid) TO anvil_capture_enrollment_owner;
CREATE POLICY capture_issuer_insert ON campaign_private.capture_enrollments FOR INSERT TO anvil_capture_enrollment_owner
 WITH CHECK(project_id=nullif(current_setting('anvil.project',true),'')::uuid);

-- Only an independently qualified producer can append a peer fact. The callable
-- capability is separate from registrar and graph scheduler; NO login or role
-- membership is installed here. The original qualification pins session_user,
-- verifier profile and all six evidence policies. Public-ready/diagnostic JSON
-- is never accepted as that qualification. Authentic OS/evidence custody remains
-- the qualified producer's responsibility; this function cannot observe an OS.
GRANT INSERT ON campaign_private.capture_attester_peer_bindings TO anvil_capture_enrollment_owner;
CREATE POLICY capture_peer_insert ON campaign_private.capture_attester_peer_bindings FOR INSERT TO anvil_capture_enrollment_owner
 WITH CHECK(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE FUNCTION marketing_runtime.record_attester_peer(p_peer uuid,p_enrollment uuid,p_request text,
 p_operation text,p_scope text,p_receipt text,p_expiry timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 operator_id uuid=nullif(current_setting('anvil.user',true),'')::uuid;
 request jsonb;operation jsonb;scope jsonb;receipt jsonb;ready jsonb;observed jsonb;verifier jsonb;
 q campaign_private.capture_channel_qualifications;a anvil.runtime_role_allowlist;
 w campaign_private.world_sessions;j anvil.jobs;expected_scope jsonb;header text;
 request_sha text;operation_sha text;receipt_sha text;category text;policies jsonb;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR NOT pg_has_role(session_user,'anvil_capture_peer_writer','MEMBER')
 OR pg_has_role(session_user,'anvil_capture_registrar','MEMBER')
 OR pg_has_role(session_user,'anvil_capture_enrollment_owner','MEMBER')
 OR pg_has_role(session_user,'anvil_app','MEMBER') OR pg_has_role(session_user,'anvil_worker','MEMBER')
 OR pg_has_role(session_user,'anvil_golden_scheduler','MEMBER') OR pg_has_role(session_user,'anvil_golden_grader','MEMBER')
 OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=session_user AND rolcanlogin
  AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
 OR NOT anvil.benchmark_is_admin(project,operator_id)
 OR p_peer IS NULL OR p_enrollment IS NULL OR p_expiry IS NULL
 OR octet_length(p_request) NOT BETWEEN 2 AND 1048576
 OR octet_length(p_operation) NOT BETWEEN 2 AND 4096 OR octet_length(p_scope) NOT BETWEEN 2 AND 8192
 OR octet_length(p_receipt) NOT BETWEEN 2 AND 32768
 OR p_request IS NULL OR p_operation IS NULL OR p_scope IS NULL OR p_receipt IS NULL
 THEN RETURN NULL;END IF;
 request=p_request::jsonb;operation=p_operation::jsonb;scope=p_scope::jsonb;receipt=p_receipt::jsonb;
 ready=receipt->'public_ready';observed=receipt->'observation';
 request_sha=encode(sha256(convert_to(p_request,'UTF8')),'hex');
 operation_sha=encode(sha256(convert_to(p_operation,'UTF8')),'hex');
 receipt_sha=encode(sha256(convert_to(p_receipt,'UTF8')),'hex');
 IF receipt->>'schema_version' IS DISTINCT FROM 'anvil.marketing-attester-os-peer-receipt.v1'
 OR receipt->'capture_accepted' IS DISTINCT FROM 'false'::jsonb OR receipt->>'run_authority' IS DISTINCT FROM 'not_granted'
 OR ready->>'schema_version' IS DISTINCT FROM 'anvil.marketing-attester-public-ready.v1'
 OR ready->>'peer_binding_id' IS DISTINCT FROM p_peer::text
 OR ready->>'request_sha256' IS DISTINCT FROM request_sha
 OR ready->>'operation_nonce' IS NULL OR ready->>'operation_nonce'!~'^[a-f0-9]{64}$'
 OR ready->>'public_key_hex' IS NULL OR ready->>'public_key_hex'!~'^[a-f0-9]{64}$'
 OR ready->>'public_key_fingerprint_sha256' IS DISTINCT FROM encode(sha256(decode(ready->>'public_key_hex','hex')),'hex')
 OR observed->>'schema_version' IS DISTINCT FROM 'anvil.marketing-attester-os-observation.v1'
 OR observed->'diagnostic_only' IS DISTINCT FROM 'true'::jsonb
 OR observed->'native_qualified' IS DISTINCT FROM 'false'::jsonb
 OR observed->'admission_eligible' IS DISTINCT FROM 'false'::jsonb
 OR observed->'capture_accepted' IS DISTINCT FROM 'false'::jsonb
 OR observed->>'run_authority' IS DISTINCT FROM 'not_granted'
 OR observed->>'request_sha256' IS DISTINCT FROM request_sha
 OR observed->>'operation_nonce' IS DISTINCT FROM ready->>'operation_nonce'
 OR observed->>'boot_id' IS DISTINCT FROM ready->>'boot_id'
 OR receipt->'framework_identity' IS NOT NULL AND receipt->'framework_identity'<>'null'::jsonb AND (
  receipt#>>'{framework_identity,job_id}' IS DISTINCT FROM request->>'job_id'
  OR receipt#>>'{framework_identity,request_sha256}' IS DISTINCT FROM request_sha
  OR receipt#>>'{framework_identity,operation_nonce}' IS DISTINCT FROM ready->>'operation_nonce')
 OR operation->>'schema_version' IS DISTINCT FROM 'anvil.marketing-native-operation.v1'
 OR operation->>'origin' IS DISTINCT FROM 'independent_operator'
 OR operation->>'purpose' IS DISTINCT FROM 'marketing_campaign_graph_v1'
 OR operation->>'request_sha256' IS DISTINCT FROM request_sha
 OR operation->>'manifest_sha256' IS DISTINCT FROM request->>'asset_manifest_sha256'
 OR operation->>'job_id' IS DISTINCT FROM request->>'job_id'
 OR operation->>'expires_at' IS NULL OR p_expiry>(operation->>'expires_at')::timestamptz
 OR operation->>'stop_at' IS NULL OR (operation->>'stop_at')::timestamptz<>'2026-12-11T05:48:04Z'::timestamptz
 THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.capture_attester_peer:'||p_peer::text,0));
 SELECT * INTO q FROM campaign_private.capture_channel_qualifications
 WHERE project_id=project AND id=(receipt->>'channel_qualification_id')::uuid;
 IF NOT FOUND OR q.auth_kind<>'operator_attested_root_peer_v1' OR q.account_email IS NOT NULL
 OR q.qualification_sha256 IS DISTINCT FROM receipt->>'producer_qualification_sha256'
 OR q.subject IS DISTINCT FROM ready->>'profile_sha256' OR q.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM campaign_private.capture_channel_revocations r WHERE r.project_id=project AND r.qualification_id=q.id)
 THEN RETURN NULL;END IF;
 SELECT * INTO a FROM anvil.runtime_role_allowlist WHERE project_id=project AND id=q.runtime_allowlist_id;
 IF NOT FOUND OR a.role<>'golden-native-coordinator' OR a.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM anvil.runtime_role_allowlist_revocations r WHERE r.project_id=project AND r.allowlist_id=a.id)
 THEN RETURN NULL;END IF;
 verifier=q.qualification_canonical::jsonb->'os_peer_verifier';policies=verifier->'evidence_policies';
 IF verifier->>'schema_version' IS DISTINCT FROM 'anvil.marketing-attester-peer-verifier.v1'
 OR verifier->>'database_login' IS DISTINCT FROM session_user::text
 OR verifier->>'profile_sha256' IS NULL OR verifier->>'profile_sha256'!~'^[a-f0-9]{64}$'
 OR verifier->>'profile_sha256' IS DISTINCT FROM receipt->>'verifier_profile_sha256'
 OR q.qualification_canonical::jsonb->>'attester_boot_id' IS DISTINCT FROM ready->>'boot_id'
 OR q.qualification_canonical::jsonb->>'attester_profile_sha256' IS DISTINCT FROM ready->>'profile_sha256'
 OR jsonb_typeof(policies) IS DISTINCT FROM 'object' OR jsonb_typeof(receipt->'independent_evidence') IS DISTINCT FROM 'object'
 THEN RETURN NULL;END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(policies))<>6
 OR (SELECT count(*) FROM jsonb_object_keys(receipt->'independent_evidence'))<>6 THEN RETURN NULL;END IF;
 FOREACH category IN ARRAY ARRAY['loaded_source_and_image_identity','dumpability_and_proc_access',
  'namespace_and_signal_isolation','exact_allowed_fd_endpoint_custody','qualified_verifier_profile','attester_key_and_public_ready_binding'] LOOP
  IF policies->>category IS NULL OR policies->>category!~'^[a-f0-9]{64}$'
  OR receipt->'independent_evidence'->category->>'policy_sha256' IS DISTINCT FROM policies->>category
  OR receipt->'independent_evidence'->category->>'receipt_sha256' IS NULL
  OR receipt->'independent_evidence'->category->>'receipt_sha256'!~'^[a-f0-9]{64}$'
  THEN RETURN NULL;END IF;
 END LOOP;
 SELECT * INTO j FROM anvil.jobs WHERE project_id=project AND id=(request->>'job_id')::uuid;
 SELECT * INTO w FROM campaign_private.world_sessions WHERE project_id=project AND job_id=j.id AND plan_id=(request->>'plan_id')::uuid;
 IF j.id IS NULL OR w.plan_id IS NULL OR j.lease_token IS NULL
 OR NOT marketing_runtime.paid_job_current(j.id,j.lease_token,w.plan_id)
 OR w.lease_sha256 IS DISTINCT FROM encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex')
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_turn_intents t WHERE t.project_id=project AND t.plan_id=w.plan_id)
 THEN RETURN NULL;END IF;
 expected_scope=jsonb_build_object('project_id',w.project_id,'job_id',w.job_id,'plan_id',w.plan_id,
 'world_binding_id',w.world_binding_id,'world_binding_sha256',w.world_binding_sha256,'episode_id',w.episode_id,
 'generation',w.generation,'lease_sha256',w.lease_sha256,'execution_sha256',w.attachment->>'execution_sha256',
 'source_qualification_sha256',(SELECT v.receipt_sha256 FROM campaign_private.world_qualifications v
  WHERE v.project_id=project AND v.id=w.qualification_id AND v.expires_at>clock_timestamp()
  AND NOT EXISTS(SELECT 1 FROM campaign_private.world_revocations r WHERE r.project_id=project AND r.qualification_id=v.id)));
 IF scope IS DISTINCT FROM expected_scope OR scope->>'source_qualification_sha256' IS NULL
 OR request->>'schema_version' IS DISTINCT FROM 'anvil.marketing-native-request.v1'
 OR request->>'purpose' IS DISTINCT FROM 'marketing_campaign_graph_v1' OR request->>'environment' IS DISTINCT FROM 'qa'
 OR request->>'project_id' IS DISTINCT FROM project::text
 OR request->>'episode_id' IS DISTINCT FROM w.episode_id::text
 OR request->>'generation' IS DISTINCT FROM w.generation::text
 OR request->>'execution_sha256' IS DISTINCT FROM scope->>'execution_sha256'
 OR q.qualification_canonical::jsonb->'status_transport'->>'not_after' IS NULL
 OR NOT EXISTS(SELECT 1 FROM anvil.harbor_agent_plans p JOIN anvil.harbor_checks h ON h.project_id=p.project_id AND h.id=p.check_id
  WHERE p.project_id=project AND p.id=w.plan_id AND p.created_by::text=request->>'actor_id'
  AND h.created_by=p.created_by AND request->>'check_id'=p.check_id::text
  AND request->>'group_id'=p.config->>'workspace_execution_group' AND request->>'max_calls'=p.config->>'max_calls'
  AND request->>'episode_timeout_seconds'=p.config->>'episode_timeout_seconds'
  AND h.started_at IS NOT NULL AND p_expiry<=h.started_at+((p.config->>'episode_timeout_seconds')||' seconds')::interval)
 OR p_expiry>least(q.expires_at,a.expires_at,(q.qualification_canonical::jsonb->'status_transport'->>'not_after')::timestamptz,
  '2026-12-11T05:48:04Z'::timestamptz) OR p_expiry<=clock_timestamp()
 THEN RETURN NULL;END IF;
 header=jsonb_build_object('schema_version','anvil.marketing-attester-peer-binding.v1',
  'boot_id',ready->>'boot_id','profile_sha256',ready->>'profile_sha256','request_sha256',request_sha,
  'operation_nonce',ready->>'operation_nonce','public_key_sha256',ready->>'public_key_fingerprint_sha256',
  'channel_qualification_sha256',q.qualification_sha256,'os_peer_receipt_sha256',receipt_sha,
  'operation_sha256',operation_sha)::text;
 INSERT INTO campaign_private.capture_attester_peer_bindings(id,project_id,enrollment_id,actor_id,job_id,plan_id,
  channel_qualification_id,operation_nonce,public_key_hex,boot_id,profile_sha256,request_canonical,request_sha256,
  operation_canonical,operation_sha256,os_receipt_canonical,os_receipt_sha256,peer_canonical,peer_sha256,original_scope,expires_at)
 VALUES(p_peer,project,p_enrollment,(request->>'actor_id')::uuid,j.id,w.plan_id,q.id,ready->>'operation_nonce',ready->>'public_key_hex',
  (ready->>'boot_id')::uuid,ready->>'profile_sha256',p_request,request_sha,p_operation,operation_sha,p_receipt,receipt_sha,
  header,encode(sha256(convert_to(header,'UTF8')),'hex'),scope,p_expiry);
 RETURN jsonb_build_object('schema_version','anvil.marketing-attester-peer-recorded.v1','peer_binding_id',p_peer,
  'peer_canonical',header,'peer_receipt_sha256',encode(sha256(convert_to(header,'UTF8')),'hex'),
  'os_peer_receipt_sha256',receipt_sha,'operation_sha256',operation_sha,
  'capture_accepted',false,'run_authority','not_granted');
END $$;

CREATE FUNCTION marketing_runtime.enroll_attester_public_key(p_peer uuid,p_public_key text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 operator_id uuid=nullif(current_setting('anvil.user',true),'')::uuid;
 b campaign_private.capture_attester_peer_bindings;q campaign_private.capture_channel_qualifications;
 w campaign_private.world_sessions;j anvil.jobs;a anvil.runtime_role_allowlist;
 qualified jsonb;peer jsonb;request jsonb;scope jsonb;limits jsonb;transport jsonb;slot uuid;
 frame text;control text;BEGIN
 IF p_public_key IS NULL OR p_public_key!~'^[a-f0-9]{64}$'
 OR current_setting('transaction_isolation')<>'read committed'
 OR NOT pg_has_role(session_user,'anvil_capture_registrar','MEMBER')
 OR pg_has_role(session_user,'anvil_capture_peer_writer','MEMBER')
 OR pg_has_role(session_user,'anvil_capture_enrollment_owner','MEMBER')
 OR pg_has_role(session_user,'anvil_app','MEMBER') OR pg_has_role(session_user,'anvil_worker','MEMBER')
 OR pg_has_role(session_user,'anvil_golden_scheduler','MEMBER') OR pg_has_role(session_user,'anvil_golden_grader','MEMBER')
 OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=session_user AND rolcanlogin
  AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
 OR NOT anvil.benchmark_is_admin(project,operator_id) THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.capture_attester_peer:'||p_peer::text,0));
 SELECT * INTO b FROM campaign_private.capture_attester_peer_bindings WHERE project_id=project AND id=p_peer;
 IF NOT FOUND OR b.public_key_hex IS DISTINCT FROM p_public_key OR b.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM campaign_private.capture_attester_peer_revocations r WHERE r.project_id=project AND r.peer_binding_id=b.id)
 OR EXISTS(SELECT 1 FROM campaign_private.capture_enrollments e WHERE e.project_id=project
  AND (e.id=b.enrollment_id OR e.job_id=b.job_id AND e.plan_id=b.plan_id OR e.operation_nonce=b.operation_nonce))
 THEN RETURN NULL;END IF;
 SELECT * INTO q FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=b.channel_qualification_id;
 IF NOT FOUND OR q.subject IS DISTINCT FROM b.profile_sha256 OR q.auth_kind<>'operator_attested_root_peer_v1'
 OR q.account_email IS NOT NULL OR q.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM campaign_private.capture_channel_revocations r WHERE r.project_id=project AND r.qualification_id=q.id)
 THEN RETURN NULL;END IF;
 SELECT * INTO a FROM anvil.runtime_role_allowlist WHERE project_id=project AND id=q.runtime_allowlist_id;
 IF NOT FOUND OR a.role<>'golden-native-coordinator' OR a.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM anvil.runtime_role_allowlist_revocations r WHERE r.project_id=project AND r.allowlist_id=a.id)
 THEN RETURN NULL;END IF;
 qualified=q.qualification_canonical::jsonb;peer=b.peer_canonical::jsonb;request=b.request_canonical::jsonb;
 transport=qualified->'status_transport';limits=qualified->'enrollment_limits';
 -- These are REQUIRED independently qualified facts. Old qualifications without
 -- this new scope cannot silently authorize an attester enrollment.
 IF qualified->>'attester_boot_id' IS DISTINCT FROM b.boot_id::text
 OR qualified->>'attester_profile_sha256' IS DISTINCT FROM b.profile_sha256
 OR qualified->>'registrar_database_login' IS DISTINCT FROM session_user::text
 OR peer->>'schema_version' IS DISTINCT FROM 'anvil.marketing-attester-peer-binding.v1'
 OR peer->>'boot_id' IS DISTINCT FROM b.boot_id::text OR peer->>'profile_sha256' IS DISTINCT FROM b.profile_sha256
 OR peer->>'public_key_sha256' IS DISTINCT FROM encode(sha256(decode(p_public_key,'hex')),'hex')
 OR peer->>'request_sha256' IS DISTINCT FROM b.request_sha256 OR peer->>'operation_nonce' IS DISTINCT FROM b.operation_nonce
 OR peer->>'channel_qualification_sha256' IS DISTINCT FROM q.qualification_sha256
 OR peer->>'os_peer_receipt_sha256' IS DISTINCT FROM b.os_receipt_sha256
 OR peer->>'operation_sha256' IS DISTINCT FROM b.operation_sha256
 OR limits->>'body_schema' IS DISTINCT FROM 'anvil.marketing-native-capture-submission.v2'
 OR jsonb_typeof(limits->'document_limits') IS DISTINCT FROM 'object'
 OR limits->>'wire_limit' IS NULL OR limits->>'wire_limit'!~'^[0-9]{1,7}$'
 OR (limits->>'wire_limit')::integer NOT BETWEEN 1 AND 1048576
 OR limits->'document_limits' IS DISTINCT FROM '{"operation_binding":4096,"kernel_scope":16384,"process_join":8192,"container_shutdown":12288,"capture_seal":8192,"verifier_result":4096}'::jsonb
 OR transport->>'cleanup_reserve_seconds' IS NULL OR transport->>'cleanup_reserve_seconds'!~'^[0-9]{1,3}$'
 OR (transport->>'cleanup_reserve_seconds')::integer NOT BETWEEN 1 AND 600
 OR transport->>'not_after' IS NULL THEN RETURN NULL;END IF;
 IF transport->>'schema_version' IS DISTINCT FROM 'anvil.marketing-status-transport-qualification.v1'
 OR transport->>'origin' IS DISTINCT FROM 'https://anvil-qa.adi-labs.ai'
 OR transport->>'path' IS DISTINCT FROM '/api/v1/integrations/marketing/native-capture/evidence-status'
 OR transport->>'method' IS DISTINCT FROM 'GET' THEN RETURN NULL;END IF;
 FOREACH control IN ARRAY ARRAY['trusted_enrollment_provenance','current_external_TLS_route','serving_API_image',
  'root_attester_isolation','narrow_egress','cleanup_reserve'] LOOP
  IF transport->'controls'->control->>'status' IS DISTINCT FROM 'passed'
  OR transport->'controls'->control->>'evidence_sha256' IS NULL
  OR transport->'controls'->control->>'evidence_sha256'!~'^[a-f0-9]{64}$' THEN RETURN NULL;END IF;
 END LOOP;
 -- The frame contains only fixed ASCII names/UUID/hex; remove JSON whitespace,
 -- not content. Key order does not affect its exact byte length.
 frame=jsonb_build_object('schema_version',limits->>'body_schema','enrollment_id',b.enrollment_id,
  'request_sha256',b.request_sha256,'operation_nonce',b.operation_nonce,'documents',jsonb_build_object(
  'operation_binding','','kernel_scope','','process_join','','container_shutdown','','capture_seal','','verifier_result',''))::text;
 IF octet_length(replace(replace(frame,', ',','),': ',':'))+106496>(limits->>'wire_limit')::integer
 THEN RETURN NULL;END IF;
 SELECT * INTO w FROM campaign_private.world_sessions WHERE project_id=project AND plan_id=b.plan_id AND job_id=b.job_id;
 SELECT * INTO j FROM anvil.jobs WHERE project_id=project AND id=b.job_id;
 IF w.plan_id IS NULL OR j.id IS NULL OR j.lease_token IS NULL
 OR w.lease_sha256 IS DISTINCT FROM encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex')
 OR NOT marketing_runtime.paid_job_current(j.id,j.lease_token,b.plan_id)
 OR EXISTS(SELECT 1 FROM marketing_runtime.paid_turn_intents t WHERE t.project_id=project AND t.plan_id=b.plan_id)
 THEN RETURN NULL;END IF;
 scope=jsonb_build_object('project_id',w.project_id,'job_id',w.job_id,'plan_id',w.plan_id,
 'world_binding_id',w.world_binding_id,'world_binding_sha256',w.world_binding_sha256,
 'episode_id',w.episode_id,'generation',w.generation,'lease_sha256',w.lease_sha256,
 'source_qualification_sha256',(SELECT receipt_sha256 FROM campaign_private.world_qualifications v
  WHERE v.project_id=project AND v.id=w.qualification_id AND v.expires_at>clock_timestamp()
  AND NOT EXISTS(SELECT 1 FROM campaign_private.world_revocations r WHERE r.project_id=project AND r.qualification_id=v.id)),
 'execution_sha256',w.attachment->>'execution_sha256');
 IF scope IS DISTINCT FROM b.original_scope OR scope->>'source_qualification_sha256' IS NULL
 OR request->>'schema_version' IS DISTINCT FROM 'anvil.marketing-native-request.v1'
 OR request->>'purpose' IS DISTINCT FROM 'marketing_campaign_graph_v1'
 OR request->>'environment' IS DISTINCT FROM 'qa' OR request->>'project_id' IS DISTINCT FROM project::text
 OR request->>'actor_id' IS DISTINCT FROM b.actor_id::text OR request->>'job_id' IS DISTINCT FROM b.job_id::text
 OR request->>'plan_id' IS DISTINCT FROM b.plan_id::text OR request->>'episode_id' IS DISTINCT FROM w.episode_id::text
 OR request->>'execution_sha256' IS DISTINCT FROM scope->>'execution_sha256'
 OR request->>'generation' IS DISTINCT FROM w.generation::text
 OR NOT EXISTS(SELECT 1 FROM anvil.harbor_agent_plans p JOIN anvil.harbor_checks h ON h.project_id=p.project_id AND h.id=p.check_id
  WHERE p.project_id=project AND p.id=b.plan_id AND p.created_by=b.actor_id AND h.created_by=b.actor_id
  AND request->>'check_id'=p.check_id::text AND request->>'group_id'=p.config->>'workspace_execution_group'
  AND request->>'max_calls'=p.config->>'max_calls'
  AND request->>'episode_timeout_seconds'=p.config->>'episode_timeout_seconds'
  AND h.started_at IS NOT NULL AND b.expires_at<=h.started_at+((p.config->>'episode_timeout_seconds')||' seconds')::interval)
 OR NOT EXISTS(SELECT 1 FROM marketing_runtime.paid_agent_bindings paid WHERE paid.project_id=project AND paid.plan_id=b.plan_id
  AND request->>'campaign_id'=paid.case_id AND request->'case_assignment'=paid.native_binding->'case_assignment'
  AND paid.created_by=b.actor_id AND paid.execution_sha256=scope->>'execution_sha256')
 OR b.expires_at>least(q.expires_at,a.expires_at,(transport->>'not_after')::timestamptz,'2026-12-11T05:48:04Z'::timestamptz)
 OR clock_timestamp()>=b.expires_at-((transport->>'cleanup_reserve_seconds')||' seconds')::interval
 THEN RETURN NULL;END IF;
 INSERT INTO campaign_private.capture_enrollments(id,project_id,actor_id,job_id,plan_id,channel_qualification_id,
 request_sha256,operation_nonce,attestation_public_key_hex,attester_boot_id,attester_profile_sha256,
 body_schema,wire_limit,original_canonical,original_sha256,scope,document_limits,expires_at)
 VALUES(b.enrollment_id,project,b.actor_id,b.job_id,b.plan_id,q.id,b.request_sha256,b.operation_nonce,
 p_public_key,b.boot_id,b.profile_sha256,limits->>'body_schema',(limits->>'wire_limit')::integer,
 b.request_canonical,b.request_sha256,scope,limits->'document_limits',b.expires_at);
 -- Existing116 AFTER INSERT reserves custody in the SAME transaction.
 SELECT id INTO slot FROM campaign_private.capture_evidence_slots WHERE project_id=project AND enrollment_id=b.enrollment_id;
 IF slot IS NULL THEN RAISE EXCEPTION 'original pre-SDK evidence reservation unavailable';END IF;
 RETURN jsonb_build_object('enrollment_id',b.enrollment_id,'manifest_id',slot,'request_sha256',b.request_sha256,
 'operation_nonce',b.operation_nonce,'public_key_hex',p_public_key,'boot_id',b.boot_id,'profile_sha256',b.profile_sha256,
 'producer_qualification_sha256',q.qualification_sha256,'scope',scope,'expires_at',b.expires_at,
 'body_schema',limits->>'body_schema','document_limits',limits->'document_limits','wire_limit',(limits->>'wire_limit')::integer,
 'status_transport',transport,'capture_accepted',false,'run_authority','not_granted');
END $$;
-- Graph child observes only committed registry state on a DIFFERENT read-only
-- connection/transaction after registrar COMMIT. No public-ready/file/boolean
-- ACK or the registrar's own uncommitted INSERT can satisfy this read barrier.
CREATE FUNCTION marketing_runtime.committed_attester_enrollment(p_job uuid,p_lease uuid,p_plan uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 actor uuid=nullif(current_setting('anvil.user',true),'')::uuid;ctx jsonb;
 b campaign_private.capture_attester_peer_bindings;e campaign_private.capture_enrollments;
 q campaign_private.capture_channel_qualifications;BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR current_setting('transaction_read_only')<>'on'
 OR pg_current_xact_id_if_assigned() IS NOT NULL THEN RETURN NULL;END IF;
 ctx=marketing_runtime.capture_manifest_preflight(p_job,p_lease,p_plan);
 IF ctx IS NULL OR ctx->>'content_state'<>'reserved_no_content'
 OR NOT marketing_runtime.paid_job_current(p_job,p_lease,p_plan) THEN RETURN NULL;END IF;
 SELECT * INTO b FROM campaign_private.capture_attester_peer_bindings
 WHERE project_id=project AND job_id=p_job AND plan_id=p_plan AND actor_id=actor;
 IF NOT FOUND OR b.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM campaign_private.capture_attester_peer_revocations r WHERE r.project_id=project AND r.peer_binding_id=b.id)
 THEN RETURN NULL;END IF;
 SELECT * INTO e FROM campaign_private.capture_enrollments WHERE project_id=project AND id=b.enrollment_id;
 SELECT * INTO q FROM campaign_private.capture_channel_qualifications WHERE project_id=project AND id=b.channel_qualification_id;
 IF e.id IS NULL OR q.id IS NULL OR e.job_id<>p_job OR e.plan_id<>p_plan OR e.actor_id<>actor
 OR e.id::text IS DISTINCT FROM ctx->>'enrollment_id'
 OR e.scope IS DISTINCT FROM ctx->'scope' OR e.scope IS DISTINCT FROM b.original_scope
 OR e.attestation_public_key_hex IS DISTINCT FROM b.public_key_hex
 OR e.attester_boot_id IS DISTINCT FROM b.boot_id OR e.attester_profile_sha256 IS DISTINCT FROM b.profile_sha256
 OR e.request_sha256 IS DISTINCT FROM b.request_sha256 OR e.operation_nonce IS DISTINCT FROM b.operation_nonce
 OR e.original_canonical IS DISTINCT FROM b.request_canonical OR e.original_sha256 IS DISTINCT FROM b.request_sha256
 OR e.expires_at IS DISTINCT FROM b.expires_at OR e.channel_qualification_id IS DISTINCT FROM q.id
 THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('schema_version','anvil.marketing-committed-attester-enrollment.v1',
 'peer_binding_id',b.id,'peer_receipt_sha256',b.peer_sha256,'enrollment',jsonb_build_object(
 'enrollment_id',e.id,'manifest_id',ctx->'manifest_id','request_sha256',e.request_sha256,
 'operation_nonce',e.operation_nonce,'public_key_hex',e.attestation_public_key_hex,'boot_id',e.attester_boot_id,
 'profile_sha256',e.attester_profile_sha256,'producer_qualification_sha256',q.qualification_sha256,
 'scope',e.scope,'expires_at',e.expires_at,'body_schema',e.body_schema,'document_limits',e.document_limits,
 'wire_limit',e.wire_limit,'status_transport',q.qualification_canonical::jsonb->'status_transport',
 'capture_accepted',false,'run_authority','not_granted'),
 'observation','committed_registry_state_only','capture_accepted',false,'run_authority','not_granted');
END $$;
-- Registration and revocation serialize on the same original peer. A revocation
-- before registration prevents it; after registration it atomically revokes113.
GRANT INSERT ON campaign_private.capture_enrollment_revocations TO anvil_capture_enrollment_owner;
CREATE POLICY capture_issuer_revoke ON campaign_private.capture_enrollment_revocations FOR INSERT TO anvil_capture_enrollment_owner
 WITH CHECK(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE FUNCTION marketing_runtime.propagate_attester_peer_revocation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
 OR NOT anvil.benchmark_is_admin(NEW.project_id,nullif(current_setting('anvil.user',true),'')::uuid)
 THEN RAISE EXCEPTION 'original scoped operator revocation required';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.capture_attester_peer:'||NEW.peer_binding_id::text,0));
 INSERT INTO campaign_private.capture_enrollment_revocations(id,project_id,enrollment_id,reason)
 SELECT gen_random_uuid(),b.project_id,e.id,NEW.reason FROM campaign_private.capture_attester_peer_bindings b
 JOIN campaign_private.capture_enrollments e ON e.project_id=b.project_id AND e.id=b.enrollment_id
 WHERE b.project_id=NEW.project_id AND b.id=NEW.peer_binding_id
 AND NOT EXISTS(SELECT 1 FROM campaign_private.capture_enrollment_revocations r WHERE r.enrollment_id=e.id);
 RETURN NEW;END $$;
CREATE TRIGGER revoke_enrollment BEFORE INSERT ON campaign_private.capture_attester_peer_revocations
 FOR EACH ROW EXECUTE FUNCTION marketing_runtime.propagate_attester_peer_revocation();
-- Function owner is isolated from the callable role and has no login/membership.
GRANT SELECT ON campaign_private.capture_evidence_slots TO anvil_capture_enrollment_owner;
CREATE POLICY capture_issuer_slot_read ON campaign_private.capture_evidence_slots FOR SELECT TO anvil_capture_enrollment_owner
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
GRANT CREATE ON SCHEMA marketing_runtime,campaign_private TO anvil_capture_enrollment_owner;
ALTER FUNCTION marketing_runtime.enroll_attester_public_key(uuid,text) OWNER TO anvil_capture_enrollment_owner;
ALTER FUNCTION marketing_runtime.record_attester_peer(uuid,uuid,text,text,text,text,timestamptz) OWNER TO anvil_capture_enrollment_owner;
ALTER FUNCTION marketing_runtime.propagate_attester_peer_revocation() OWNER TO anvil_capture_enrollment_owner;
ALTER FUNCTION marketing_runtime.committed_attester_enrollment(uuid,uuid,uuid) OWNER TO anvil_capture_enrollment_owner;
ALTER FUNCTION campaign_private.capture_registry_quota_guard() OWNER TO anvil_capture_enrollment_owner;
REVOKE CREATE ON SCHEMA marketing_runtime,campaign_private FROM anvil_capture_enrollment_owner;
REVOKE ALL ON FUNCTION campaign_private.capture_registry_quota_guard() FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar;
REVOKE ALL ON FUNCTION marketing_runtime.enroll_attester_public_key(uuid,text) FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader;
REVOKE ALL ON FUNCTION marketing_runtime.enroll_attester_public_key(uuid,text) FROM anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION marketing_runtime.enroll_attester_public_key(uuid,text) TO anvil_capture_registrar;
REVOKE ALL ON FUNCTION marketing_runtime.record_attester_peer(uuid,uuid,text,text,text,text,timestamptz)
 FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar;
GRANT EXECUTE ON FUNCTION marketing_runtime.record_attester_peer(uuid,uuid,text,text,text,text,timestamptz) TO anvil_capture_peer_writer;
REVOKE ALL ON FUNCTION marketing_runtime.propagate_attester_peer_revocation() FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar;
REVOKE ALL ON FUNCTION marketing_runtime.committed_attester_enrollment(uuid,uuid,uuid) FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_grader,anvil_capture_registrar;
REVOKE ALL ON FUNCTION marketing_runtime.committed_attester_enrollment(uuid,uuid,uuid) FROM anvil_capture_peer_writer;
GRANT EXECUTE ON FUNCTION marketing_runtime.committed_attester_enrollment(uuid,uuid,uuid) TO anvil_golden_scheduler;
INSERT INTO anvil.schema_versions(version) VALUES(119);
