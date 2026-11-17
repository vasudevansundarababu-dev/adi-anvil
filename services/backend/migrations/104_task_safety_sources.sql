-- Operator-only source qualification. App drafts cannot approve their framework.
CREATE TABLE anvil.task_safety_source_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,
 source_sha256 text NOT NULL CHECK(source_sha256~'^[a-f0-9]{64}$'),
 configuration_sha256 text NOT NULL CHECK(configuration_sha256~'^[a-f0-9]{64}$'),
 runtime_sha256 text NOT NULL CHECK(runtime_sha256~'^[a-f0-9]{64}$'),
 broker_sha256 text NOT NULL CHECK(broker_sha256~'^[a-f0-9]{64}$'),
 runtime_image_sha256 text NOT NULL,release_sha256 text NOT NULL CHECK(release_sha256~'^[a-f0-9]{64}$'),
 receipt jsonb NOT NULL CHECK(octet_length(receipt::text)<=65536),
 receipt_sha256 text NOT NULL CHECK(receipt_sha256~'^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.task_safety_source_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,
 reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.task_safety_source_qualifications(project_id,id),UNIQUE(qualification_id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['task_safety_source_qualifications','task_safety_source_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY engineer_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_golden_scheduler,anvil_golden_grader',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
-- Keep the existing once-only budget, current credential/Admin and lease checks.
-- The private legacy helper cannot be invoked by an app to bypass source checks.
ALTER FUNCTION anvil.claim_governed_ai_sdk(uuid,uuid,uuid,uuid,text,jsonb) RENAME TO claim_governed_ai_sdk_089;
REVOKE ALL ON FUNCTION anvil.claim_governed_ai_sdk_089(uuid,uuid,uuid,uuid,text,jsonb) FROM PUBLIC,anvil_app;
CREATE FUNCTION anvil.claim_governed_ai_sdk(p_job uuid,p_lease uuid,p_call uuid,p_dispatch uuid,p_hash text,p_model jsonb)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE a anvil.governed_ai_calls;q anvil.task_safety_source_qualifications;f jsonb;
BEGIN
 SELECT * INTO a FROM anvil.governed_ai_calls WHERE id=p_call FOR UPDATE;
 f=a.request->'safety_framework';
 IF f IS NOT NULL THEN
  IF a.purpose<>'safety_generation' OR a.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid THEN RETURN false;END IF;
  SELECT * INTO q FROM anvil.task_safety_source_qualifications WHERE id=(f->'qualification'->>'id')::uuid FOR UPDATE;
  IF q.id IS NULL OR q.project_id IS DISTINCT FROM a.project_id OR q.task_group_id::text IS DISTINCT FROM a.request->>'task_group_id'
  OR q.source_sha256 IS DISTINCT FROM a.request->>'source_sha256'
  OR q.configuration_sha256 IS DISTINCT FROM f->'source_ref'->>'configuration_sha256'
  OR q.runtime_sha256 IS DISTINCT FROM a.request->>'runtime_source_sha256'
  OR q.broker_sha256 IS DISTINCT FROM a.request->>'broker_source_sha256'
  OR q.release_sha256 IS DISTINCT FROM a.request->>'release_sha256'
  OR q.receipt_sha256 IS DISTINCT FROM f->'qualification'->>'receipt_sha256'
  OR q.expires_at<=clock_timestamp() OR EXISTS(SELECT 1 FROM anvil.task_safety_source_revocations r WHERE r.qualification_id=q.id)
  THEN RETURN false;END IF;
 END IF;
 RETURN anvil.claim_governed_ai_sdk_089(p_job,p_lease,p_call,p_dispatch,p_hash,p_model);
END $$;
REVOKE ALL ON FUNCTION anvil.claim_governed_ai_sdk(uuid,uuid,uuid,uuid,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_governed_ai_sdk(uuid,uuid,uuid,uuid,text,jsonb) TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(104);
