CREATE TABLE anvil.project_data_inputs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,source_sha256 text NOT NULL,
 family text NOT NULL CHECK(family IN('kyc','marketing')),filename text NOT NULL,
 schema_version text NOT NULL,schema_sha256 text NOT NULL,raw_sha256 text NOT NULL,
 content jsonb NOT NULL CHECK(octet_length(content::text)<=16777216),content_sha256 text NOT NULL,
 byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 10485760),created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(project_id,id),UNIQUE(task_group_id,content_sha256,schema_sha256),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id));
CREATE TABLE anvil.project_data_input_jobs(
 input_id uuid PRIMARY KEY,project_id uuid NOT NULL,state text NOT NULL DEFAULT 'queued' CHECK(state IN('queued','completed')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),FOREIGN KEY(project_id,input_id) REFERENCES anvil.project_data_inputs(project_id,id));
CREATE TABLE anvil.project_data_provisions(
 input_id uuid PRIMARY KEY,project_id uuid NOT NULL,pack_id uuid,
 manifest jsonb NOT NULL CHECK(octet_length(manifest::text)<=4194304),manifest_sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,input_id) REFERENCES anvil.project_data_inputs(project_id,id),
 FOREIGN KEY(project_id,pack_id) REFERENCES banking.packs(project_id,id));
CREATE TABLE anvil.project_data_selections(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,input_id uuid,
 source_sha256 text NOT NULL,selection jsonb NOT NULL CHECK(octet_length(selection::text)<=4194304),selection_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),
 FOREIGN KEY(project_id,input_id) REFERENCES anvil.project_data_inputs(project_id,id),UNIQUE(project_id,id));
DO $$ DECLARE t text;BEGIN FOREACH t IN ARRAY ARRAY['project_data_inputs','project_data_input_jobs','project_data_provisions','project_data_selections'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY engineer_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
 EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_golden_scheduler,anvil_golden_grader',t);
 IF t<>'project_data_input_jobs' THEN
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END IF;
END LOOP;END $$;
CREATE POLICY engineer_insert ON anvil.project_data_inputs FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY engineer_insert ON anvil.project_data_selections FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY engineer_queue ON anvil.project_data_input_jobs FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND state='queued');
CREATE POLICY scheduler_provision ON anvil.project_data_provisions FOR INSERT TO anvil_golden_scheduler WITH CHECK(banking.runtime_scope(project_id));
CREATE POLICY scheduler_job ON anvil.project_data_input_jobs FOR UPDATE TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
GRANT INSERT ON anvil.project_data_inputs,anvil.project_data_selections,anvil.project_data_input_jobs TO anvil_app;
GRANT INSERT ON anvil.project_data_provisions TO anvil_golden_scheduler;
GRANT UPDATE(state) ON anvil.project_data_input_jobs TO anvil_golden_scheduler;
CREATE FUNCTION anvil.project_input_job_transition() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF OLD.state<>'queued' OR NEW.state<>'completed'
 OR (to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state') THEN
  RAISE EXCEPTION 'Input population job is once-only and identity is immutable';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION anvil.project_input_job_transition() FROM PUBLIC;
CREATE TRIGGER project_input_job_transition BEFORE UPDATE ON anvil.project_data_input_jobs
 FOR EACH ROW EXECUTE FUNCTION anvil.project_input_job_transition();
INSERT INTO anvil.schema_versions(version) VALUES(102);
