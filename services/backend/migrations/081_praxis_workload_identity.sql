-- Keyless service principals reuse project grants, live sponsor checks and
-- append-only revocations. No token/key is issued or stored by this mapping.
CREATE TABLE anvil.dataset_export_workload_principals(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,client_id uuid NOT NULL UNIQUE,
 issuer text NOT NULL CHECK(issuer='https://accounts.google.com'),
 subject text NOT NULL CHECK(subject~'^[0-9]{6,30}$'),
 account_email text NOT NULL CHECK(account_email~'^[a-z0-9][a-z0-9._-]*@[a-z0-9][a-z0-9.-]*[.]iam[.]gserviceaccount[.]com$'),
 audience text NOT NULL CHECK(audience='https://anvil-qa.adi-labs.ai'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,client_id) REFERENCES anvil.dataset_export_clients(project_id,id));
ALTER TABLE anvil.dataset_export_workload_principals ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.dataset_export_workload_principals FORCE ROW LEVEL SECURITY;
CREATE POLICY workload_project_lookup ON anvil.dataset_export_workload_principals
 FOR SELECT TO anvil_app
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE POLICY workload_admin_insert ON anvil.dataset_export_workload_principals
 FOR INSERT TO anvil_app WITH CHECK(
 anvil.benchmark_is_admin(project_id,nullif(current_setting('anvil.user',true),'')::uuid)
 AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
GRANT SELECT,INSERT ON anvil.dataset_export_workload_principals TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.dataset_export_workload_principals
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

-- Separate case execution from authored task identity. Old cells retain an empty
-- case axis and exactly their former uniqueness; no historical capture changes.
ALTER TABLE anvil.benchmark_run_cells ADD COLUMN case_key text NOT NULL DEFAULT ''
 CHECK(length(case_key)<=80);
DO $$ DECLARE item record; BEGIN
 FOR item IN SELECT conname FROM pg_constraint
 WHERE conrelid='anvil.benchmark_run_cells'::regclass AND contype='u'
 AND cardinality(conkey)=5 LOOP
  EXECUTE format('ALTER TABLE anvil.benchmark_run_cells DROP CONSTRAINT %I',item.conname);
 END LOOP;
END $$;
CREATE UNIQUE INDEX benchmark_run_case_identity ON anvil.benchmark_run_cells
 (run_id,model_key,task_key,environment_key,repetition,case_key);

-- Dedicated LangGraph PostgresSaver layout (checkpoint-postgres migrations0..9).
-- No runtime DDL or ordinary worker/API access. State contains phase identities
-- and hashes only; private grading data and provider/trial credentials stay out.
CREATE SCHEMA anvil_golden_checkpoints;
CREATE TABLE anvil_golden_checkpoints.checkpoints(
 thread_id text NOT NULL,checkpoint_ns text NOT NULL DEFAULT '',
 checkpoint_id text NOT NULL,parent_checkpoint_id text,type text,
 checkpoint jsonb NOT NULL,metadata jsonb NOT NULL DEFAULT '{}',
 PRIMARY KEY(thread_id,checkpoint_ns,checkpoint_id));
CREATE TABLE anvil_golden_checkpoints.checkpoint_blobs(
 thread_id text NOT NULL,checkpoint_ns text NOT NULL DEFAULT '',
 channel text NOT NULL,version text NOT NULL,type text,blob bytea,
 PRIMARY KEY(thread_id,checkpoint_ns,channel,version));
CREATE TABLE anvil_golden_checkpoints.checkpoint_writes(
 thread_id text NOT NULL,checkpoint_ns text NOT NULL DEFAULT '',
 checkpoint_id text NOT NULL,task_id text NOT NULL,idx integer NOT NULL,
 channel text NOT NULL,type text,blob bytea NOT NULL,task_path text NOT NULL DEFAULT '',
 PRIMARY KEY(thread_id,checkpoint_ns,checkpoint_id,task_id,idx));
GRANT USAGE ON SCHEMA anvil_golden_checkpoints TO anvil_golden_scheduler;
DO $$ DECLARE table_name text; BEGIN
 FOREACH table_name IN ARRAY ARRAY['checkpoints','checkpoint_blobs','checkpoint_writes'] LOOP
  EXECUTE format('ALTER TABLE anvil_golden_checkpoints.%I ENABLE ROW LEVEL SECURITY',table_name);
  EXECUTE format('ALTER TABLE anvil_golden_checkpoints.%I FORCE ROW LEVEL SECURITY',table_name);
  EXECUTE format('CREATE POLICY scoped ON anvil_golden_checkpoints.%I TO anvil_golden_scheduler USING(split_part(thread_id,'':'',1)=nullif(current_setting(''anvil.project'',true),'''')) WITH CHECK(split_part(thread_id,'':'',1)=nullif(current_setting(''anvil.project'',true),''''))',table_name);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE ON anvil_golden_checkpoints.%I TO anvil_golden_scheduler',table_name);
 END LOOP;
END $$;
