-- Freeze opaque private-reference identity before execution, never its contents.
CREATE FUNCTION anvil.campaign_reference_metadata(p_group uuid,p_cases jsonb) RETURNS jsonb
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE p uuid=nullif(current_setting('anvil.project',true),'')::uuid;task jsonb;member jsonb;
 ref campaign_private.references%ROWTYPE;members jsonb='[]'::jsonb;BEGIN
 IF anvil.golden_engineer(p) IS NOT TRUE OR jsonb_typeof(p_cases) IS DISTINCT FROM 'array' OR jsonb_array_length(p_cases) NOT BETWEEN 1 AND 10000 THEN
  RAISE EXCEPTION 'Current project and bounded campaign population required';
 END IF;
 SELECT g.content->'tasks'->0 INTO task FROM anvil.benchmark_task_groups g WHERE g.project_id=p AND g.id=p_group AND jsonb_array_length(g.content->'tasks')=1;
 IF NOT FOUND OR (task->'source'->'template'->>'profile_id') IS DISTINCT FROM 'veyra-hush-one-launch-v1' THEN
  RAISE EXCEPTION 'Exact reusable campaign source required';
 END IF;
 IF (SELECT count(DISTINCT value->>'case_id') FROM jsonb_array_elements(p_cases))<>jsonb_array_length(p_cases) THEN
  RAISE EXCEPTION 'Unique frozen campaign cases required';
 END IF;
 FOR member IN SELECT value FROM jsonb_array_elements(p_cases) LOOP
  IF jsonb_typeof(member->'case_id') IS DISTINCT FROM 'string' OR coalesce(member->>'snapshot_sha256','')!~'^[a-f0-9]{64}$' THEN
   RAISE EXCEPTION 'Exact campaign case and snapshot digest required';
  END IF;
  SELECT r.* INTO ref FROM campaign_private.references r WHERE r.project_id=p AND r.task_id=task->>'task_id'
   AND r.task_version=task->>'task_version' AND r.payload_sha256=task->>'payload_sha256'
   AND r.case_id=member->>'case_id' AND r.case_sha256=member->>'snapshot_sha256' ORDER BY r.created_at DESC,r.id DESC LIMIT 1;
  members=members||jsonb_build_array(jsonb_build_object('case_id',member->>'case_id','snapshot_sha256',member->>'snapshot_sha256',
   'reference_id',ref.id,'reference_sha256',ref.content_sha256,'status',CASE WHEN ref.id IS NULL THEN 'missing_at_preparation' ELSE 'bound' END));
 END LOOP;
 RETURN jsonb_build_object('schema_version','anvil.campaign-reference-manifest.v1','task_id',task->>'task_id',
  'task_version',task->>'task_version','payload_sha256',task->>'payload_sha256','cases',members,'private_contents_included',false);
END $$;
REVOKE ALL ON FUNCTION anvil.campaign_reference_metadata(uuid,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.campaign_reference_metadata(uuid,jsonb) TO anvil_app;

CREATE TABLE marketing_runtime.grading_slots(
 project_id uuid NOT NULL,run_id uuid NOT NULL,case_id text NOT NULL,model_key text NOT NULL,repetition integer NOT NULL,
 job_id uuid NOT NULL UNIQUE,PRIMARY KEY(project_id,run_id,case_id,model_key,repetition),
 FOREIGN KEY(project_id,job_id) REFERENCES marketing_runtime.grading_jobs(project_id,id));
ALTER TABLE marketing_runtime.grading_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing_runtime.grading_slots FORCE ROW LEVEL SECURITY;
CREATE POLICY runtime_read ON marketing_runtime.grading_slots FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT ON marketing_runtime.grading_slots TO anvil_golden_scheduler,anvil_golden_grader;
INSERT INTO marketing_runtime.grading_slots(project_id,run_id,case_id,model_key,repetition,job_id)
 SELECT j.project_id,j.run_id,e.case_id,j.model_key,j.repetition,j.id FROM marketing_runtime.grading_jobs j JOIN marketing_runtime.episodes e ON e.project_id=j.project_id AND e.id=j.episode_id;
CREATE FUNCTION marketing_runtime.claim_grading_slot() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE actual_case text;BEGIN
 SELECT case_id INTO actual_case FROM marketing_runtime.episodes WHERE project_id=NEW.project_id AND id=NEW.episode_id;
 INSERT INTO marketing_runtime.grading_slots(project_id,run_id,case_id,model_key,repetition,job_id)
 VALUES(NEW.project_id,NEW.run_id,actual_case,NEW.model_key,NEW.repetition,NEW.id);
 RETURN NEW;END $$;
CREATE TRIGGER exact_slot AFTER INSERT ON marketing_runtime.grading_jobs FOR EACH ROW EXECUTE FUNCTION marketing_runtime.claim_grading_slot();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON marketing_runtime.grading_slots FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.schema_versions(version) VALUES(100);
