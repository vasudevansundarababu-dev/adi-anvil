-- Fixed ASCII OS-proof projection, not a general task/document canonicalizer.
-- Original physical documents contain ASCII kernel names/UUIDs/hashes/paths and
-- bounded plain monotonic numbers. Other representations fail closed.
CREATE FUNCTION campaign_private.physical_json_bytes(p jsonb,depth integer DEFAULT 0) RETURNS bytea
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
DECLARE result text;BEGIN
 IF p IS NULL OR depth NOT BETWEEN 0 AND 24 OR octet_length(p::text)>1048576
 OR octet_length(p::text)<>char_length(p::text) THEN RETURN NULL;END IF;
 CASE jsonb_typeof(p)
 WHEN 'object' THEN
  IF EXISTS(SELECT 1 FROM jsonb_each(p) item WHERE campaign_private.physical_json_bytes(item.value,depth+1) IS NULL)
  THEN RETURN NULL;END IF;
  SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||convert_from(campaign_private.physical_json_bytes(value,depth+1),'UTF8'),',' ORDER BY key COLLATE "C"),'')||'}'
  INTO result FROM jsonb_each(p);
 WHEN 'array' THEN
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(p) item WHERE campaign_private.physical_json_bytes(item.value,depth+1) IS NULL)
  THEN RETURN NULL;END IF;
  SELECT '['||coalesce(string_agg(convert_from(campaign_private.physical_json_bytes(value,depth+1),'UTF8'),',' ORDER BY ordinal),'')||']'
  INTO result FROM jsonb_array_elements(p) WITH ORDINALITY AS item(value,ordinal);
 WHEN 'number' THEN
  IF p::text!~'^(0|[1-9][0-9]*)(\.[0-9]+)?$' THEN RETURN NULL;END IF;
  result=p::text;
 ELSE result=p::text;
 END CASE;
 RETURN convert_to(result,'UTF8');
END $$;
REVOKE ALL ON FUNCTION campaign_private.physical_json_bytes(jsonb,integer) FROM PUBLIC;

CREATE FUNCTION campaign_private.physical_observation_time(value jsonb,deadline numeric) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
 SELECT CASE WHEN jsonb_typeof(value) IS DISTINCT FROM 'number' OR deadline IS NULL OR deadline<=0 THEN false
 ELSE (value::text)::numeric>0 AND (value::text)::numeric<deadline END;
$$;
REVOKE ALL ON FUNCTION campaign_private.physical_observation_time(jsonb,numeric) FROM PUBLIC;
CREATE FUNCTION marketing_runtime.private_capture_authority_lock(project uuid) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT pg_advisory_xact_lock_shared(hashtextextended('marketing-capture-authority:'||project::text,0));
$$;
REVOKE ALL ON FUNCTION marketing_runtime.private_capture_authority_lock(uuid) FROM PUBLIC;

CREATE FUNCTION campaign_private.capture_authority_fence() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('marketing-capture-authority:'||NEW.project_id::text,0));
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION campaign_private.capture_authority_fence() FROM PUBLIC;
CREATE TRIGGER private_capture_revoke_fence BEFORE INSERT ON campaign_private.capture_channel_revocations
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_authority_fence();
CREATE TRIGGER private_capture_revoke_fence BEFORE INSERT ON campaign_private.capture_enrollment_revocations
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_authority_fence();
CREATE TRIGGER private_capture_revoke_fence BEFORE INSERT ON campaign_private.capture_attester_peer_revocations
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_authority_fence();
CREATE TRIGGER private_capture_revoke_fence BEFORE INSERT ON anvil.runtime_role_allowlist_revocations
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_authority_fence();
CREATE TRIGGER private_capture_revoke_fence BEFORE INSERT ON campaign_private.world_revocations
 FOR EACH ROW EXECUTE FUNCTION campaign_private.capture_authority_fence();

CREATE FUNCTION marketing_runtime.private_capture_evidence_valid(p_enrollment uuid,p_intake uuid,p_result uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
DECLARE project uuid=nullif(current_setting('anvil.project',true),'')::uuid;
 r campaign_private.capture_raw_intakes;result campaign_private.private_result_originals;
 i campaign_private.private_result_intents;frame campaign_private.private_grade_frames;
 actor campaign_private.private_actor_originals;actor_intent campaign_private.private_actor_intents;
 ctx jsonb;e jsonb;p jsonb;peer jsonb;pre jsonb;docs jsonb;op jsonb;kernel jsonb;joined jsonb;containers jsonb;
 verifier jsonb;seal jsonb;process jsonb;grade jsonb;stop jsonb;proof jsonb;binding jsonb;root jsonb;children jsonb;
 input_seal jsonb;current_registry jsonb;node jsonb;expected jsonb;item jsonb;role text;kind text;section text;
 value jsonb;original jsonb;first_snapshot jsonb;second_snapshot jsonb;deadline numeric;
 award jsonb;weights jsonb='{"A1":4,"A2":4,"A3":2,"B1":5,"B2":5,"B3":5,"B4":5,"C1":6,"C2":5,"C3":4,"D1":6,"D2":4,"E1":5,"E2":5,"E3":5,"F1":5,"F2":4,"F3":3,"F4":3,"G1":4,"G2":4,"G3":4,"G4":3}'::jsonb;
 totals jsonb='{"A":0,"B":0,"C":0,"D":0,"E":0,"F":0,"G":0}'::jsonb;
 points numeric=0;total numeric=0;missing integer=0;status text;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' OR current_setting('transaction_read_only')<>'off'
 THEN RETURN false;END IF;
 -- Revocation INSERTs take the matching exclusive transaction lock. Retain
 -- this shared fence through the actual acceptance COMMIT, not just a SELECT.
 PERFORM marketing_runtime.private_capture_authority_lock(project);
 ctx=marketing_runtime.private_capture_context(p_enrollment,p_intake);
 IF ctx IS NULL OR marketing_runtime.private_capture_profile_current(p_enrollment) IS DISTINCT FROM true THEN RETURN false;END IF;
 e=ctx->'enrollment';p=ctx#>'{qualification,private_capture_profile}';
 SELECT * INTO r FROM campaign_private.capture_raw_intakes WHERE project_id=project AND id=p_intake AND enrollment_id=p_enrollment;
 SELECT * INTO result FROM campaign_private.private_result_originals WHERE project_id=project AND id=p_result;
 SELECT * INTO i FROM campaign_private.private_result_intents WHERE project_id=project AND id=result.intent_id;
 SELECT * INTO frame FROM campaign_private.private_grade_frames WHERE project_id=project AND id=i.frame_id;
 SELECT * INTO actor FROM campaign_private.private_actor_originals WHERE project_id=project AND id=frame.actor_original_id;
 SELECT * INTO actor_intent FROM campaign_private.private_actor_intents WHERE project_id=project AND id=actor.intent_id;
 IF r.id IS NULL OR result.id IS NULL OR frame.id IS NULL OR actor.id IS NULL
 OR frame.manifest_id::text IS DISTINCT FROM e->>'manifest_id' OR actor_intent.manifest_id<>frame.manifest_id
 OR frame.native_registry_sha256 IS NULL OR frame.deployment_release_sha256 IS DISTINCT FROM p->>'deployment_release_sha256'
 THEN RETURN false;END IF;
 current_registry=marketing_runtime.private_native_ordinal_acceptance_context(p_enrollment,frame.manifest_id,p->>'deployment_release_sha256');
 IF current_registry IS NULL OR encode(sha256(convert_to(current_registry::text,'UTF8')),'hex') IS DISTINCT FROM frame.native_registry_sha256
 THEN RETURN false;END IF;
 -- Locks may wait. All current external authority and elapsed expiry is
 -- checked AGAIN after those waits, immediately before the acceptance INSERT.
 ctx=marketing_runtime.private_capture_context(p_enrollment,p_intake);
 IF ctx IS NULL OR marketing_runtime.private_capture_profile_current(p_enrollment) IS DISTINCT FROM true THEN RETURN false;END IF;
 e=ctx->'enrollment';
 docs=r.decoded_documents;
 IF docs IS DISTINCT FROM (convert_from(r.raw_wire,'UTF8')::jsonb->'documents') OR jsonb_typeof(docs) IS DISTINCT FROM 'object'
 OR (SELECT count(*) FROM jsonb_object_keys(docs))<>6
 OR NOT docs ?& ARRAY['operation_binding','kernel_scope','process_join','container_shutdown','verifier_result','capture_seal']
 THEN RETURN false;END IF;
 FOR kind IN SELECT jsonb_object_keys(docs) LOOP
  value=(docs->>kind)::jsonb;
  IF campaign_private.physical_json_bytes(value) IS DISTINCT FROM convert_to(docs->>kind,'UTF8') THEN RETURN false;END IF;
 END LOOP;
 op=(docs->>'operation_binding')::jsonb;kernel=(docs->>'kernel_scope')::jsonb;
 joined=(docs->>'process_join')::jsonb;containers=(docs->>'container_shutdown')::jsonb;
 verifier=(docs->>'verifier_result')::jsonb;seal=(docs->>'capture_seal')::jsonb;
 process=convert_from(result.process_raw,'UTF8')::jsonb;grade=convert_from(frame.raw_frame,'UTF8')::jsonb;
 peer=(ctx->>'peer_receipt_canonical')::jsonb;pre=peer->'preG_actor_observation';
 root=op->'actor_scope_binding';children=op->'child_binding';input_seal=seal->'input_seal';
 IF op->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-operation-binding.v1'
 OR kernel->>'schema_version' IS DISTINCT FROM 'anvil.marketing-empty-kernel-scope-observation.v1'
 OR joined->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-original-process-exits.v1'
 OR containers->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-owned-containers-stopped.v1'
 OR verifier->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-verifier-custody-reference.v1'
 OR seal->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-whole-capture-seal.v1'
 OR grade->'mapping_qualified' IS DISTINCT FROM 'true'::jsonb THEN RETURN false;END IF;
 FOREACH value IN ARRAY ARRAY[op,verifier,seal] LOOP
  IF value->'identity' IS DISTINCT FROM e->'identity' OR value->'scope' IS DISTINCT FROM e->'scope'
  OR value->'capture_accepted' IS DISTINCT FROM 'false'::jsonb OR value->'native_qualified' IS DISTINCT FROM 'false'::jsonb
  OR value->>'run_authority' IS DISTINCT FROM 'not_granted' THEN RETURN false;END IF;
 END LOOP;
 FOREACH value IN ARRAY ARRAY[op,seal] LOOP
  IF value->>'enrollment_id' IS DISTINCT FROM p_enrollment::text OR value->>'manifest_id' IS DISTINCT FROM frame.manifest_id::text
  OR value->>'api_descriptor_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(e->'descriptor')),'hex')
  THEN RETURN false;END IF;
 END LOOP;
 IF op->>'original_peer_receipt_sha256' IS DISTINCT FROM encode(sha256(convert_to(ctx->>'peer_receipt_canonical','UTF8')),'hex')
 OR op->>'public_ready_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(peer->'public_ready')),'hex')
 OR op->>'boot_id' IS DISTINCT FROM e->>'boot_id' OR root->>'boot_id' IS DISTINCT FROM e->>'boot_id'
 OR root->>'request_sha256' IS DISTINCT FROM e->>'request_sha256' OR root->>'operation_nonce' IS DISTINCT FROM e->>'operation_nonce'
 OR root->>'plan_sha256' IS DISTINCT FROM e#>>'{identity,plan_sha256}'
 OR root->'original_deadline_monotonic' IS DISTINCT FROM pre->'original_deadline_monotonic'
 OR op->'original_deadline_monotonic' IS DISTINCT FROM pre->'original_deadline_monotonic'
 OR pre->>'actor_scope_binding_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(root)),'hex')
 OR children->>'binding_sha256' IS DISTINCT FROM pre->>'actor_scope_binding_sha256'
 OR kernel->>'independent_binding_sha256' IS DISTINCT FROM pre->>'actor_scope_binding_sha256'
 OR kernel->>'boot_id' IS DISTINCT FROM e->>'boot_id'
 OR children->>'schema_version' IS DISTINCT FROM 'anvil.marketing-original-actor-scope-children.v2'
 OR (SELECT count(*) FROM jsonb_object_keys(children->'children'))<>3
 OR NOT (children->'children') ?& ARRAY['framework','graph','host_helpers'] THEN RETURN false;END IF;
 IF jsonb_typeof(pre->'original_deadline_monotonic') IS DISTINCT FROM 'number'
 OR jsonb_typeof(kernel->'observed_monotonic') IS DISTINCT FROM 'number'
 OR jsonb_typeof(joined->'original_deadline_monotonic') IS DISTINCT FROM 'number'
 OR joined->'original_deadline_monotonic' IS DISTINCT FROM pre->'original_deadline_monotonic' THEN RETURN false;END IF;
 deadline=(pre->>'original_deadline_monotonic')::numeric;
 IF campaign_private.physical_observation_time(kernel->'observed_monotonic',deadline) IS DISTINCT FROM true
 THEN RETURN false;END IF;
 FOREACH section IN ARRAY ARRAY['snapshot_first','snapshot_second'] LOOP
  value=kernel->section;
  IF jsonb_typeof(value) IS DISTINCT FROM 'array' OR jsonb_array_length(value)<>4
  OR (SELECT count(DISTINCT n->>'relative') FROM jsonb_array_elements(value) n)<>4 THEN RETURN false;END IF;
  FOR node IN SELECT n FROM jsonb_array_elements(value) n LOOP
   role=node->>'relative';
   IF role='.' THEN expected=pre->'original_actor_scope';
   ELSIF role IN('./framework','./graph','./host_helpers') THEN expected=children#>ARRAY['children',substr(role,3)];
   ELSE RETURN false;END IF;
   IF node->'device' IS DISTINCT FROM expected->'device' OR node->'inode' IS DISTINCT FROM expected->'inode'
   OR node->'mount_id' IS DISTINCT FROM expected->'mount_id'
   OR coalesce(node#>>'{raw_kernel_files,cgroup.procs}','missing')!~'^\s*$'
   OR coalesce(node#>>'{raw_kernel_files,cgroup.threads}','missing')!~'^\s*$'
   OR (regexp_split_to_array(trim(node#>>'{raw_kernel_files,cgroup.events}'),E'\\s+') IS DISTINCT FROM ARRAY['populated','0','frozen','1']
    AND regexp_split_to_array(trim(node#>>'{raw_kernel_files,cgroup.events}'),E'\\s+') IS DISTINCT FROM ARRAY['frozen','1','populated','0']) THEN RETURN false;END IF;
  END LOOP;
  SELECT jsonb_agg(n-'raw_fdinfo' ORDER BY n->>'relative') INTO expected FROM jsonb_array_elements(value) n;
  IF section='snapshot_first' THEN first_snapshot=expected;ELSE second_snapshot=expected;END IF;
 END LOOP;
 IF first_snapshot IS DISTINCT FROM second_snapshot
 OR joined->>'kernel_scope_sha256' IS DISTINCT FROM encode(sha256(convert_to(docs->>'kernel_scope','UTF8')),'hex')
 OR joined->>'before_G_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(pre)),'hex')
 OR joined->>'request_sha256' IS DISTINCT FROM e->>'request_sha256' OR joined->>'operation_nonce' IS DISTINCT FROM e->>'operation_nonce'
 OR joined->>'boot_id' IS DISTINCT FROM e->>'boot_id' THEN RETURN false;END IF;
 FOREACH role IN ARRAY ARRAY['framework','graph'] LOOP
  value=joined#>ARRAY['actors',role];expected=pre#>ARRAY['children',role];
  IF value->'pid' IS DISTINCT FROM expected->'pid' OR value->'start_ticks' IS DISTINCT FROM expected->'start_ticks'
  OR value->'pidfd_exit_observed' IS DISTINCT FROM 'true'::jsonb
  OR children#>ARRAY['children',role,'device'] IS DISTINCT FROM expected->'cgroup_device'
  OR children#>ARRAY['children',role,'inode'] IS DISTINCT FROM expected->'cgroup_inode'
  OR children#>ARRAY['children',role,'mount_id'] IS DISTINCT FROM expected->'cgroup_mount_id' THEN RETURN false;END IF;
  value=joined->CASE WHEN role='framework' THEN 'framework_exit' ELSE 'graph_join' END;
  IF value->'pid' IS DISTINCT FROM expected->'pid' OR value->'start_ticks' IS DISTINCT FROM expected->'start_ticks'
  OR value->>'request_sha256' IS DISTINCT FROM e->>'request_sha256' OR value->>'plan_sha256' IS DISTINCT FROM e#>>'{identity,plan_sha256}'
  OR value->(CASE WHEN role='framework' THEN 'returncode' ELSE 'wait_status' END) IS DISTINCT FROM '0'::jsonb
  THEN RETURN false;END IF;
  IF role='framework' AND campaign_private.physical_observation_time(value->'observed_monotonic',deadline) IS DISTINCT FROM true
  THEN RETURN false;END IF;
 END LOOP;
 FOR kind IN SELECT key FROM jsonb_object_keys(docs) AS key WHERE key<>'capture_seal' LOOP
  IF seal#>>ARRAY['documents_sha256',kind] IS DISTINCT FROM encode(sha256(convert_to(docs->>kind,'UTF8')),'hex') THEN RETURN false;END IF;
 END LOOP;
 IF (SELECT count(*) FROM jsonb_object_keys(seal->'documents_sha256'))<>5
 OR seal->>'own_api_status_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(ctx->'current_status')),'hex')
 OR seal->>'own_api_tls_certificate_sha256' IS DISTINCT FROM p->>'tls_certificate_sha256'
 OR seal->>'actor_output_sha256' IS DISTINCT FROM actor.raw_sha256
 OR seal->>'actor_stop_sha256' IS DISTINCT FROM actor_intent.actor_stop_sha256
 OR seal->>'collection_receipt_sha256' IS DISTINCT FROM actor_intent.collection_receipt_sha256
 OR input_seal->>'api_frame_sha256' IS DISTINCT FROM frame.raw_sha256
 OR input_seal->'file_sha256' IS DISTINCT FROM grade->'file_sha256'
 OR input_seal->>'sdk_binding_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(grade->'sdk_binding')),'hex')
 OR input_seal->'identity' IS DISTINCT FROM e->'identity' OR input_seal->'scope' IS DISTINCT FROM e->'scope'
 OR input_seal#>>'{directory,mode}' IS DISTINCT FROM '0555' OR input_seal#>'{directory,uid}' IS DISTINCT FROM '0'::jsonb
 THEN RETURN false;END IF;
 IF process->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-verifier-process-observed.v1'
 OR process->'identity' IS DISTINCT FROM e->'identity' OR process->'scope' IS DISTINCT FROM e->'scope'
 OR process->>'role' IS DISTINCT FROM 'tests' OR process->>'image_id' IS DISTINCT FROM p->>'runtime_image_digest'
 OR process->'argv' IS DISTINCT FROM '["python3","-I","-B","-m","anvil_harbor.marketing_private_verifier"]'::jsonb
 OR process->'exit_code' IS DISTINCT FROM '0'::jsonb OR process#>'{engine_wait,StatusCode}' IS DISTINCT FROM '0'::jsonb
 OR coalesce(process#>'{engine_wait,Error}','null'::jsonb) NOT IN('null'::jsonb,'{}'::jsonb)
 OR process->>'program_sha256' IS DISTINCT FROM p->>'private_program_sha256'
 OR process->>'input_sha256' IS DISTINCT FROM grade#>>'{sdk_binding,input_sha256}'
 OR process->'input_files' IS DISTINCT FROM grade#>'{sdk_binding,input_files}'
 OR process->>'sdk_binding_sha256' IS DISTINCT FROM input_seal->>'sdk_binding_sha256'
 OR process->>'input_seal_receipt_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(input_seal)),'hex')
 OR process#>>'{output,sha256}' IS DISTINCT FROM result.verifier_sha256
 OR process#>'{output,bytes}' IS DISTINCT FROM to_jsonb(octet_length(result.verifier_raw))
 OR process#>>'{output,source}' IS DISTINCT FROM '/logs/verifier/result.json'
 OR process#>'{output,uid}' IS DISTINCT FROM '10001'::jsonb OR process#>'{output,gid}' IS DISTINCT FROM '10001'::jsonb
 OR process#>>'{output,mode}' IS DISTINCT FROM '0600' OR process#>'{output,links}' IS DISTINCT FROM '1'::jsonb THEN RETURN false;END IF;
 IF process->'whole_operation_stopped' IS DISTINCT FROM 'false'::jsonb
 OR process->'capture_accepted' IS DISTINCT FROM 'false'::jsonb OR process->'native_qualified' IS DISTINCT FROM 'false'::jsonb
 OR jsonb_typeof(process->'started_at') IS DISTINCT FROM 'string' OR jsonb_typeof(process->'finished_at') IS DISTINCT FROM 'string'
 OR (process->>'started_at')::timestamptz<'1970-01-01Z'::timestamptz
 OR (process->>'finished_at')::timestamptz<(process->>'started_at')::timestamptz
 OR (process->>'finished_at')::timestamptz>=(e->>'expires_at')::timestamptz
 OR (SELECT count(*) FROM jsonb_array_elements(process->'mounts') m WHERE m->>'Destination'='/sealed-verifier')<>1
 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(process->'mounts') m WHERE m->>'Destination'='/sealed-verifier'
  AND m->>'Type'='bind' AND m->'RW'='false'::jsonb AND m->>'Propagation'='rprivate'
  AND m->>'Source' LIKE '/%/sealed-verifier') THEN RETURN false;END IF;
 award=convert_from(result.verifier_raw,'UTF8')::jsonb;
 IF award->>'schema_version' IS DISTINCT FROM 'anvil.marketing-private-result.v1'
 OR award->'identity' IS DISTINCT FROM e->'identity' OR award->'scope' IS DISTINCT FROM e->'scope'
 OR award->>'source_sha256' IS DISTINCT FROM grade#>>'{sdk_binding,source_sha256}'
 OR award->>'input_sha256' IS DISTINCT FROM grade#>>'{sdk_binding,input_sha256}'
 OR award->'input_files' IS DISTINCT FROM grade#>'{sdk_binding,input_files}'
 OR award->>'scoring_contract' IS DISTINCT FROM 'marketing-task2-native-23-ordinal-v1'
 OR award->'scoring_source_pins' IS DISTINCT FROM grade#>'{sdk_binding,scoring_source_pins}'
 OR grade#>'{sdk_binding,criterion_weights}' IS DISTINCT FROM weights
 OR award->>'result' IS DISTINCT FROM result.grade_status OR award->>'scale' IS DISTINCT FROM 'zero_to_four'
 OR jsonb_typeof(award->'levels') IS DISTINCT FROM 'object'
 OR (SELECT count(*) FROM jsonb_object_keys(award->'levels'))<>23
 OR jsonb_typeof(award->'critical_failures') IS DISTINCT FROM 'array'
 OR jsonb_typeof(award->'unknown_critical_rules') IS DISTINCT FROM 'array'
 OR award->'model_performance_validated' IS DISTINCT FROM 'false'::jsonb
 OR award->'native_qualification_granted' IS DISTINCT FROM 'false'::jsonb
 OR award->>'human_legal_acceptance' IS DISTINCT FROM 'not_established' THEN RETURN false;END IF;
 FOR kind,value IN SELECT pair.key,pair.entry FROM jsonb_each(weights) AS pair(key,entry) LOOP
  IF NOT (award->'levels') ? kind THEN RETURN false;END IF;
  item=award#>ARRAY['levels',kind];
  IF item='null'::jsonb THEN missing=missing+1;
  ELSE
   IF jsonb_typeof(item) IS DISTINCT FROM 'number' OR item::text!~'^[0-4]$' THEN RETURN false;END IF;
   points=(value::text)::numeric*(item::text)::numeric/4;
   totals=jsonb_set(totals,ARRAY[left(kind,1)],to_jsonb((totals->>left(kind,1))::numeric+points));
  END IF;
 END LOOP;
 FOR kind,value IN SELECT pair.key,pair.entry FROM jsonb_each(totals) AS pair(key,entry) LOOP
  item=award#>ARRAY['groups',kind];
  IF jsonb_typeof(item->'numerator') IS DISTINCT FROM 'number' OR jsonb_typeof(item->'denominator') IS DISTINCT FROM 'number'
  OR (item->>'denominator')::numeric NOT BETWEEN 1 AND 4
  OR (item->>'numerator')::numeric/(item->>'denominator')::numeric IS DISTINCT FROM (value::text)::numeric
  THEN RETURN false;END IF;
  total=total+(value::text)::numeric;
 END LOOP;
 IF (award#>>'{total,denominator}')::numeric NOT BETWEEN 1 AND 4
 OR (award#>>'{total,numerator}')::numeric/(award#>>'{total,denominator}')::numeric IS DISTINCT FROM total
 THEN RETURN false;END IF;
 status=CASE WHEN jsonb_array_length(award->'critical_failures')>0 OR award->'output_gate'='false'::jsonb THEN 'failed'
 WHEN missing>0 OR jsonb_array_length(award->'unknown_critical_rules')>0 OR award->'output_gate'='null'::jsonb THEN 'unscored'
 WHEN award->'output_gate'='true'::jsonb AND total>=80 AND (totals->>'B')::numeric>=12 THEN 'passed' ELSE 'failed' END;
 IF status IS DISTINCT FROM result.grade_status THEN RETURN false;END IF;
 stop=process->'actor_stop';proof=process->'actor_capture_proof';
 IF encode(sha256(campaign_private.physical_json_bytes(stop)),'hex') IS DISTINCT FROM actor_intent.actor_stop_sha256
 OR encode(sha256(campaign_private.physical_json_bytes(proof)),'hex') IS DISTINCT FROM process->>'actor_capture_sha256'
 OR stop->>'native_stop_receipt_sha256' IS DISTINCT FROM process->>'actor_capture_sha256'
 OR stop->>'actor_output_sha256' IS DISTINCT FROM actor.raw_sha256 OR stop->>'collection_receipt_sha256' IS DISTINCT FROM actor_intent.collection_receipt_sha256
 OR proof->>'actor_output_sha256' IS DISTINCT FROM actor.raw_sha256
 OR proof->'api_scope' IS DISTINCT FROM e->'scope'
 OR proof->>'quiescence_sha256' IS DISTINCT FROM e#>>'{descriptor,quiescence_receipt_sha256}'
 OR proof->>'operation_scope_binding_sha256' IS DISTINCT FROM pre->>'actor_scope_binding_sha256'
 OR proof->>'child_binding_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(children)),'hex')
 THEN RETURN false;END IF;
 IF verifier#>>'{custody,id}' IS DISTINCT FROM result.id::text
 OR verifier#>>'{custody,raw_sha256}' IS DISTINCT FROM result.raw_sha256
 OR verifier#>>'{custody,process_receipt_sha256}' IS DISTINCT FROM result.process_sha256
 OR verifier#>>'{custody,verifier_result_sha256}' IS DISTINCT FROM result.verifier_sha256
 OR verifier#>>'{custody,grade_frame_sha256}' IS DISTINCT FROM frame.raw_sha256
 OR verifier#>>'{custody,grade_status}' IS DISTINCT FROM result.grade_status
 OR verifier->>'input_seal_receipt_sha256' IS DISTINCT FROM process->>'input_seal_receipt_sha256'
 OR verifier->>'private_program_sha256' IS DISTINCT FROM process->>'program_sha256'
 OR verifier->>'sdk_binding_sha256' IS DISTINCT FROM process->>'sdk_binding_sha256'
 OR (SELECT count(*) FROM jsonb_object_keys(containers->'roles'))<>2 THEN RETURN false;END IF;
 FOREACH role IN ARRAY ARRAY['environment','tests'] LOOP
  value=containers#>ARRAY['roles',role];binding=value->'binding';original=value->'stop_observation';
  IF binding->>'schema_version' IS DISTINCT FROM 'anvil.marketing-owned-container.v1'
  OR binding->>'role' IS DISTINCT FROM role OR binding->>'image_id' IS DISTINCT FROM p->>'runtime_image_digest'
  OR binding->>'request_sha256' IS DISTINCT FROM e->>'request_sha256' OR binding->>'operation_nonce' IS DISTINCT FROM e->>'operation_nonce'
  OR binding->>'framework_trial_id' IS DISTINCT FROM e#>>'{identity,framework_trial_id}'
  OR binding->>'plan_sha256' IS DISTINCT FROM e#>>'{identity,plan_sha256}'
  OR value->>'identity_fields_sha256' IS DISTINCT FROM binding->>'inspect_config_sha256'
  OR value->'restart_count' IS DISTINCT FROM '0'::jsonb OR value#>'{current_state,Running}' IS DISTINCT FROM 'false'::jsonb
  OR value#>'{current_state,Pid}' IS DISTINCT FROM '0'::jsonb OR value#>>'{current_state,Status}' IS DISTINCT FROM 'exited'
  OR value#>'{current_state,Paused}' IS DISTINCT FROM 'false'::jsonb OR value#>'{current_state,Restarting}' IS DISTINCT FROM 'false'::jsonb
  OR value#>'{current_state,Dead}' IS DISTINCT FROM 'false'::jsonb
  OR original->>'binding_sha256' IS DISTINCT FROM encode(sha256(campaign_private.physical_json_bytes(binding)),'hex')
  OR original->'container_stopped_observed' IS DISTINCT FROM 'true'::jsonb OR original->>'role' IS DISTINCT FROM role
  OR original->>'container_id' IS DISTINCT FROM binding->>'container_id'
  OR campaign_private.physical_observation_time(original->'observed_monotonic',deadline) IS DISTINCT FROM true
  THEN RETURN false;END IF;
  IF role='tests' AND (value#>'{current_state,ExitCode}' IS DISTINCT FROM '0'::jsonb
   OR binding->>'container_id' IS DISTINCT FROM process->>'container_id'
   OR encode(sha256(campaign_private.physical_json_bytes(binding)),'hex') IS DISTINCT FROM process->>'container_binding_sha256') THEN RETURN false;END IF;
 END LOOP;
 RETURN marketing_runtime.private_capture_profile_current(p_enrollment)
  AND marketing_runtime.private_capture_context(p_enrollment,p_intake) IS NOT NULL;
EXCEPTION WHEN OTHERS THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.private_capture_evidence_valid(uuid,uuid,uuid)
 FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_golden_grader,anvil_capture_registrar,anvil_capture_peer_writer;
CREATE FUNCTION campaign_private.check_capture_commit_authority() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$ BEGIN
 IF marketing_runtime.private_capture_profile_current(NEW.enrollment_id) IS DISTINCT FROM true
 OR marketing_runtime.private_capture_evidence_valid(NEW.enrollment_id,NEW.raw_intake_id,NEW.result_original_id) IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'original capture authority expired or changed before COMMIT';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION campaign_private.check_capture_commit_authority() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER current_authority_at_commit AFTER INSERT ON campaign_private.private_capture_acceptances
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION campaign_private.check_capture_commit_authority();
GRANT CREATE ON SCHEMA campaign_private,marketing_runtime TO anvil_private_grade_owner;
ALTER FUNCTION campaign_private.physical_json_bytes(jsonb,integer) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION campaign_private.physical_observation_time(jsonb,numeric) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_capture_authority_lock(uuid) OWNER TO anvil_private_grade_owner;
ALTER FUNCTION campaign_private.capture_authority_fence() OWNER TO anvil_private_grade_owner;
ALTER FUNCTION campaign_private.check_capture_commit_authority() OWNER TO anvil_private_grade_owner;
ALTER FUNCTION marketing_runtime.private_capture_evidence_valid(uuid,uuid,uuid) OWNER TO anvil_private_grade_owner;
REVOKE CREATE ON SCHEMA campaign_private,marketing_runtime FROM anvil_private_grade_owner;
INSERT INTO anvil.schema_versions(version) VALUES(126);
