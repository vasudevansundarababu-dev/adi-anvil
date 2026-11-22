-- Technical method publication only. No seeded principals, human approvals,
-- safety/evaluator publication, private answers, run activation or spending.
CREATE TABLE anvil.task_method_publications(
 id uuid PRIMARY KEY, project_id uuid NOT NULL,
 qualification_id uuid NOT NULL UNIQUE,
 login_role name NOT NULL, sponsoring_admin uuid NOT NULL REFERENCES anvil.users(id),
 observation_sha256 text NOT NULL CHECK(observation_sha256~'^[a-f0-9]{64}$'),
 review_sha256 text NOT NULL CHECK(review_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,qualification_id)
  REFERENCES anvil.task_capability_qualifications(project_id,id));
ALTER TABLE anvil.task_method_publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.task_method_publications FORCE ROW LEVEL SECURITY;
REVOKE ALL ON anvil.task_method_publications FROM PUBLIC,anvil_app,anvil_worker,
 anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_qualifier;
GRANT SELECT ON anvil.task_method_publications TO anvil_kyc_qualifier;
CREATE POLICY enrolled_method_read ON anvil.task_method_publications
 FOR SELECT TO anvil_kyc_qualifier USING(anvil.kyc_policy_operator_scope(project_id));
CREATE POLICY enrolled_method_fence ON anvil.task_method_publications AS RESTRICTIVE
 FOR ALL TO anvil_kyc_qualifier
 USING(anvil.kyc_policy_operator_scope(project_id))
 WITH CHECK(anvil.kyc_policy_operator_scope(project_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.task_method_publications
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

-- Return a bounded public projection, never grant SELECT on raw group content.
-- In particular, neither legacy task.source nor private references are returned.
CREATE FUNCTION anvil.task_method_public_group(p uuid,g uuid) RETURNS jsonb
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE r anvil.benchmark_task_groups; tasks jsonb; result jsonb;
BEGIN
 IF NOT pg_has_role(session_user,'anvil_kyc_qualifier','MEMBER')
  OR NOT anvil.kyc_policy_operator_scope(p) THEN
  RAISE EXCEPTION 'Enrolled task method operator required' USING ERRCODE='42501';
 END IF;
 SELECT * INTO r FROM anvil.benchmark_task_groups WHERE project_id=p AND id=g;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF jsonb_typeof(r.content->'tasks') IS DISTINCT FROM 'array'
  OR jsonb_array_length(r.content->'tasks') NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION 'Bounded captured task group required';
 END IF;
 SELECT jsonb_agg(jsonb_build_object(
  'task_id',CASE WHEN jsonb_typeof(t->'task_id')='string' THEN t->'task_id' END,
  'task_version',CASE WHEN jsonb_typeof(t->'task_version')='string' THEN t->'task_version' END,
  'payload_sha256',CASE WHEN jsonb_typeof(t->'payload_sha256')='string' THEN t->'payload_sha256' END,
  'workflow_declared',jsonb_typeof(t->'workflow')='object',
  'workflow_steps',coalesce((SELECT jsonb_agg(jsonb_build_object(
   'index',step_ordinal-1,
   'action',CASE WHEN jsonb_typeof(step->'action')='string' THEN step->'action' END,
   'tool',CASE WHEN jsonb_typeof(step->'tool')='string' THEN step->'tool' END,
   'failureBehaviour',CASE WHEN jsonb_typeof(step->'failureBehaviour')='string'
    THEN step->'failureBehaviour' END) ORDER BY step_ordinal)
   FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t#>'{actor,sections,S5,steps}')='array'
    THEN t#>'{actor,sections,S5,steps}' ELSE '[]'::jsonb END)
    WITH ORDINALITY s(step,step_ordinal)),'[]'::jsonb)) ORDER BY ordinal)
 INTO tasks FROM jsonb_array_elements(r.content->'tasks') WITH ORDINALITY x(t,ordinal);
 result=jsonb_build_object('id',r.id,'project_id',r.project_id,
  'source_sha256',r.content_sha256,'tasks',tasks,
  'database_identity',jsonb_build_object('database',current_database(),
   'database_oid',(SELECT oid::text FROM pg_database WHERE datname=current_database()),
   'system_identifier',(SELECT system_identifier::text FROM pg_control_system())));
 IF octet_length(result::text)>1048576 THEN
  RAISE EXCEPTION 'Public method observation exceeds bound';
 END IF;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION anvil.task_method_public_group(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.task_method_public_group(uuid,uuid) TO anvil_kyc_qualifier;

-- The disjoint publisher must first verify original observations and their
-- independent review in the exact installed image. The API cannot call this
-- function; enrollment does not turn its sponsoring Admin into a qualifier.
CREATE FUNCTION anvil.publish_task_method(p uuid,g uuid,q uuid,e text,
 evidence_hash text,expiry timestamptz) RETURNS uuid
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE body jsonb; source text; control text; sponsor uuid;
 controls_text text; canonical_text text;
BEGIN
 IF NOT pg_has_role(session_user,'anvil_kyc_qualifier','MEMBER')
  OR NOT anvil.kyc_policy_operator_scope(p) THEN
  RAISE EXCEPTION 'Enrolled task method publisher required' USING ERRCODE='42501';
 END IF;
 -- Serialize enrollment, sponsoring membership and user revocation with this
 -- publication, rather than trusting an authorization checked before a wait.
 SELECT user_id INTO sponsor FROM anvil.kyc_policy_operator_principals
  WHERE login_role=session_user AND project_id=p FOR SHARE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'Current method operator enrollment required' USING ERRCODE='42501';
 END IF;
 PERFORM 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
  WHERE m.project_id=p AND m.user_id=sponsor AND m.active AND u.active
   AND m.role='admin' FOR SHARE OF m,u;
 IF NOT FOUND OR NOT anvil.kyc_policy_operator_scope(p) THEN
  RAISE EXCEPTION 'Current sponsoring Admin required' USING ERRCODE='42501';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.task.method:'||p::text||':'||q::text,0));
 IF octet_length(e) NOT BETWEEN 2 AND 65536 OR evidence_hash IS NULL
  OR evidence_hash<>encode(sha256(convert_to(e,'UTF8')),'hex') THEN
  RAISE EXCEPTION 'Exact bounded canonical evidence bytes required';
 END IF;
 body=e::jsonb;
 -- This closed receipt has only ASCII field names, string/boolean leaves and
 -- one fixed two-level controls object. Serialize that exact subset; do not
 -- pretend jsonb::text is a general JCS implementation (numbers are forbidden).
 IF (SELECT array_agg(key ORDER BY key COLLATE "C") FROM jsonb_object_keys(body) names(key))
  IS DISTINCT FROM (SELECT array_agg(key ORDER BY key COLLATE "C") FROM unnest(ARRAY[
   'schema_version','origin','project_id','task_group_id','source_sha256','target',
   'candidate_id','publisher_login','spending_authority','human_review_approval',
   'model_performance','issued_at','expires_at','controls','candidate_sha256',
   'runtime_source_sha256','broker_source_sha256','runtime_image_sha256',
   'release_sha256','observation_sha256','review_sha256','evidence_scope']) names(key)) THEN
  RAISE EXCEPTION 'Closed method publication receipt required';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_each(body) fields(key,value)
  WHERE key NOT IN('controls','spending_authority','human_review_approval','model_performance')
   AND jsonb_typeof(value) IS DISTINCT FROM 'string') THEN
  RAISE EXCEPTION 'Method identity fields must be strings';
 END IF;
 SELECT content_sha256 INTO source FROM anvil.benchmark_task_groups
  WHERE project_id=p AND id=g FOR SHARE;
 IF NOT FOUND OR body->>'schema_version' IS DISTINCT FROM 'anvil.task-capability-control.v1'
  OR body->>'origin' IS DISTINCT FROM 'independent_qa'
  OR body->>'source_sha256' IS DISTINCT FROM source
  OR body->>'target' IS DISTINCT FROM 'method:task-rubric-v1'
  OR body->>'candidate_id' IS DISTINCT FROM 'task-rubric-v1'
  OR body->>'evidence_scope' IS DISTINCT FROM 'technical_method_controls_only'
  OR body->>'publisher_login' IS DISTINCT FROM session_user::text
  OR body->>'task_group_id' IS DISTINCT FROM g::text
  OR body->>'project_id' IS DISTINCT FROM p::text
  OR body->'spending_authority' IS DISTINCT FROM 'false'::jsonb
  OR body->'human_review_approval' IS DISTINCT FROM 'false'::jsonb
  OR body->'model_performance' IS DISTINCT FROM 'false'::jsonb
  OR expiry IS NULL OR expiry<=clock_timestamp()
  OR expiry>clock_timestamp()+interval '24 hours'
  OR (body->>'expires_at')::timestamptz IS DISTINCT FROM expiry
  OR body->>'issued_at' IS NULL
  OR (body->>'issued_at')::timestamptz>clock_timestamp()
  OR expiry>(body->>'issued_at')::timestamptz+interval '24 hours' THEN
  RAISE EXCEPTION 'Exact nonspending task method subject required';
 END IF;
 FOREACH control IN ARRAY ARRAY['candidate_sha256','runtime_source_sha256',
  'broker_source_sha256','runtime_image_sha256','release_sha256',
  'observation_sha256','review_sha256'] LOOP
  IF body->>control IS NULL OR body->>control !~ '^[a-f0-9]{64}$' THEN
   RAISE EXCEPTION 'Pinned method publication identities required';
  END IF;
 END LOOP;
 IF jsonb_typeof(body->'controls') IS DISTINCT FROM 'object'
  OR (SELECT count(*) FROM jsonb_object_keys(body->'controls'))<>4 THEN
  RAISE EXCEPTION 'Observed method controls required';
 END IF;
 FOREACH control IN ARRAY ARRAY['positive','negative','missing','project_isolation'] LOOP
  IF body->'controls'->control->>'status' IS DISTINCT FROM 'passed'
   OR jsonb_typeof(body->'controls'->control) IS DISTINCT FROM 'object'
   OR (SELECT count(*) FROM jsonb_object_keys(body->'controls'->control))<>2
   OR jsonb_typeof(body->'controls'->control->'evidence_sha256') IS DISTINCT FROM 'string'
   OR body->'controls'->control->>'evidence_sha256' IS NULL
   OR body->'controls'->control->>'evidence_sha256' !~ '^[a-f0-9]{64}$' THEN
   RAISE EXCEPTION 'Complete independently reviewed method controls required';
  END IF;
 END LOOP;
 SELECT '{'||string_agg(to_jsonb(name)::text||':'||'{'||
  (SELECT string_agg(to_jsonb(key)::text||':'||value::text,',' ORDER BY key COLLATE "C")
   FROM jsonb_each(item) fields(key,value))||'}',',' ORDER BY name COLLATE "C")||'}'
 INTO controls_text FROM jsonb_each(body->'controls') controls(name,item);
 SELECT '{'||string_agg(to_jsonb(key)::text||':'||
  CASE WHEN key='controls' THEN controls_text ELSE value::text END,',' ORDER BY key COLLATE "C")||'}'
 INTO canonical_text FROM jsonb_each(body) fields(key,value);
 IF canonical_text IS DISTINCT FROM e THEN
  RAISE EXCEPTION 'Exact canonical string/boolean method evidence required';
 END IF;
 INSERT INTO anvil.task_capability_qualifications(id,project_id,task_group_id,
  target,kind,candidate_id,candidate_sha256,source_sha256,release_sha256,evidence,
  evidence_sha256,expires_at)
 VALUES(q,p,g,'method:task-rubric-v1','method','task-rubric-v1',body->>'candidate_sha256',
  source,body->>'release_sha256',body,evidence_hash,expiry);
 INSERT INTO anvil.task_method_publications(id,project_id,qualification_id,login_role,
  sponsoring_admin,observation_sha256,review_sha256)
 VALUES(q,p,q,session_user,sponsor,body->>'observation_sha256',body->>'review_sha256');
 RETURN q;
END $$;
REVOKE ALL ON FUNCTION anvil.publish_task_method(uuid,uuid,uuid,text,text,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.publish_task_method(uuid,uuid,uuid,text,text,timestamptz)
 TO anvil_kyc_qualifier;

ALTER TABLE anvil.task_capability_revocations
 ADD COLUMN operator_login name,
 ADD COLUMN operator_admin uuid REFERENCES anvil.users(id),
 ADD CONSTRAINT operator_attribution_pair CHECK(
  (operator_login IS NULL)=(operator_admin IS NULL));
CREATE FUNCTION anvil.revoke_task_method(p uuid,q uuid,r uuid,why text) RETURNS uuid
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE sponsor uuid;
BEGIN
 IF NOT pg_has_role(session_user,'anvil_kyc_qualifier','MEMBER')
  OR NOT anvil.kyc_policy_operator_scope(p) THEN
  RAISE EXCEPTION 'Enrolled task method revoker required' USING ERRCODE='42501';
 END IF;
 SELECT user_id INTO sponsor FROM anvil.kyc_policy_operator_principals
  WHERE login_role=session_user AND project_id=p FOR SHARE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'Current method operator enrollment required' USING ERRCODE='42501';
 END IF;
 PERFORM 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
  WHERE m.project_id=p AND m.user_id=sponsor AND m.active AND u.active
   AND m.role='admin' FOR SHARE OF m,u;
 IF NOT FOUND OR NOT anvil.kyc_policy_operator_scope(p) THEN
  RAISE EXCEPTION 'Current sponsoring Admin required' USING ERRCODE='42501';
 END IF;
 IF why IS NULL OR length(btrim(why)) NOT BETWEEN 10 AND 2000 THEN
  RAISE EXCEPTION 'Explicit bounded technical revocation reason required';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil.task.method:'||p::text||':'||q::text,0));
 PERFORM 1 FROM anvil.task_capability_qualifications c
  JOIN anvil.task_method_publications a ON a.project_id=c.project_id AND a.qualification_id=c.id
  WHERE c.project_id=p AND c.id=q AND c.kind='method'
   AND c.candidate_id='task-rubric-v1' AND c.target='method:task-rubric-v1'
  FOR UPDATE OF c;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'Owned task method publication required' USING ERRCODE='42501';
 END IF;
 INSERT INTO anvil.task_capability_revocations(id,project_id,qualification_id,reason,
  operator_login,operator_admin) VALUES(r,p,q,why,session_user,sponsor);
 RETURN r;
END $$;
REVOKE ALL ON FUNCTION anvil.revoke_task_method(uuid,uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.revoke_task_method(uuid,uuid,uuid,text) TO anvil_kyc_qualifier;
-- Fence only the enrolled project's qualification inputs. Template writers
-- already lock its project; evaluator receipt/revocation triggers lock their
-- configuration. The qualifier receives no UPDATE privilege on either table.
CREATE FUNCTION anvil.task_method_binding_fence(p uuid) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF NOT pg_has_role(session_user,'anvil_kyc_qualifier','MEMBER')
  OR NOT anvil.kyc_policy_operator_scope(p) THEN
  RAISE EXCEPTION 'Enrolled task method operator required' USING ERRCODE='42501';
 END IF;
 PERFORM id FROM anvil.projects WHERE id=p FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Existing enrolled project required'; END IF;
 PERFORM id FROM anvil.evaluator_configurations WHERE project_id=p ORDER BY id FOR SHARE;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION anvil.task_method_binding_fence(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.task_method_binding_fence(uuid) TO anvil_kyc_qualifier;
INSERT INTO anvil.schema_versions(version) VALUES(136);
