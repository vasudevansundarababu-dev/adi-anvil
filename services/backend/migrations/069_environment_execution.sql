-- Durable environment lifecycle. No cloud activation is created by this migration.
GRANT EXECUTE ON FUNCTION anvil.golden_engineer(uuid) TO anvil_worker;
CREATE TABLE anvil.environment_runtime_profiles(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),name text NOT NULL,
 configuration jsonb NOT NULL,content_sha256 text NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id));
ALTER TABLE anvil.environment_runtime_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.environment_runtime_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY read_engineer ON anvil.environment_runtime_profiles FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY write_admin ON anvil.environment_runtime_profiles FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND anvil.benchmark_is_admin(project_id,nullif(current_setting('anvil.user',true),'')::uuid));
CREATE POLICY worker ON anvil.environment_runtime_profiles TO anvil_worker USING(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.environment_runtime_profiles TO anvil_app;
GRANT SELECT ON anvil.environment_runtime_profiles TO anvil_worker;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.environment_runtime_profiles FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER actual_author BEFORE INSERT ON anvil.environment_runtime_profiles FOR EACH ROW EXECUTE FUNCTION anvil.environment_author();
CREATE TABLE anvil.environment_build_jobs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,environment_id uuid NOT NULL,
 profile jsonb NOT NULL,profile_sha256 text NOT NULL,state text NOT NULL DEFAULT 'queued'
 CHECK(state IN('queued','running','completed','failed','cancelled','reconciliation_required','waiting_authority')),
 phase text NOT NULL DEFAULT 'preflight',revision integer NOT NULL DEFAULT 0,
 cancel_requested boolean NOT NULL DEFAULT false,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,environment_id) REFERENCES anvil.environment_versions(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.environment_build_steps(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,job_id uuid NOT NULL,phase text NOT NULL,
 content jsonb NOT NULL,content_sha256 text NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(job_id,phase),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.environment_build_jobs(project_id,id));
CREATE TABLE anvil.environment_attempts(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,binding_id uuid,environment_id uuid NOT NULL,
 model_key text NOT NULL,repetition integer NOT NULL,parent_attempt_id uuid,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN('queued','running','captured','assessed','failed','cancelled','uncertain')),
 instance_id uuid,evidence_receipt_id uuid,evaluation_id uuid,error_code text,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id),
 FOREIGN KEY(project_id,binding_id) REFERENCES anvil.environment_task_bindings(project_id,id),
 FOREIGN KEY(project_id,environment_id) REFERENCES anvil.environment_versions(project_id,id),
 FOREIGN KEY(project_id,instance_id) REFERENCES anvil.environment_instances(project_id,id),
 FOREIGN KEY(project_id,evidence_receipt_id) REFERENCES anvil.environment_receipts(project_id,id),
 FOREIGN KEY(project_id,evaluation_id) REFERENCES anvil.environment_evaluations(project_id,id),
 UNIQUE(project_id,id),UNIQUE(run_id,environment_id,model_key,repetition),
 FOREIGN KEY(project_id,parent_attempt_id) REFERENCES anvil.environment_attempts(project_id,id));
CREATE TABLE anvil.environment_run_controls(
 run_id uuid PRIMARY KEY,project_id uuid NOT NULL,cancel_requested boolean NOT NULL DEFAULT false,
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id));
CREATE TABLE anvil.environment_run_lineage(
 run_id uuid PRIMARY KEY,project_id uuid NOT NULL,parent_run_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id),
 FOREIGN KEY(project_id,parent_run_id) REFERENCES anvil.benchmark_runs(project_id,id));
ALTER TABLE anvil.environment_run_lineage ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.environment_run_lineage FORCE ROW LEVEL SECURITY;
CREATE POLICY engineer ON anvil.environment_run_lineage TO anvil_app USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id));
CREATE POLICY worker ON anvil.environment_run_lineage TO anvil_worker USING(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.environment_run_lineage TO anvil_app;
GRANT SELECT ON anvil.environment_run_lineage TO anvil_worker;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.environment_run_lineage FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER actual_author BEFORE INSERT ON anvil.environment_run_lineage FOR EACH ROW EXECUTE FUNCTION anvil.environment_author();
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['environment_build_jobs','environment_build_steps','environment_attempts','environment_run_controls'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY engineer ON anvil.%I TO anvil_app USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id))',t);
 EXECUTE format('CREATE POLICY worker ON anvil.%I TO anvil_worker USING(anvil.in_scope(project_id) AND anvil.golden_engineer(project_id)) WITH CHECK(anvil.in_scope(project_id) AND anvil.golden_engineer(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app,anvil_worker',t);
 IF t='environment_build_steps' THEN EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 ELSE EXECUTE format('GRANT UPDATE ON anvil.%I TO anvil_app,anvil_worker',t);END IF;
 IF t<>'environment_run_controls' THEN EXECUTE format('CREATE TRIGGER actual_author BEFORE INSERT ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.environment_author()',t);END IF;
 END LOOP;END $$;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['environment_versions','environment_packs','environment_instances','environment_records','environment_files','environment_events','environment_receipts','environment_task_bindings','environment_evaluations'] LOOP
 EXECUTE format('CREATE POLICY scoped_worker ON anvil.%I TO anvil_worker USING(anvil.in_scope(project_id) AND anvil.golden_engineer(project_id)) WITH CHECK(anvil.in_scope(project_id) AND anvil.golden_engineer(project_id))',t);
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_worker',t);
 IF t IN ('environment_instances','environment_records','environment_files','environment_events','environment_receipts','environment_evaluations') THEN EXECUTE format('GRANT INSERT ON anvil.%I TO anvil_worker',t);END IF;
 IF t IN ('environment_instances','environment_records','environment_files') THEN EXECUTE format('GRANT UPDATE ON anvil.%I TO anvil_worker',t);END IF;
 IF t IN ('environment_records','environment_files') THEN EXECUTE format('GRANT DELETE ON anvil.%I TO anvil_worker',t);END IF;
 END LOOP;END $$;
CREATE FUNCTION anvil.environment_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF (to_jsonb(NEW)-ARRAY['state','phase','revision','cancel_requested','instance_id','evidence_receipt_id','evaluation_id','error_code']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','phase','revision','cancel_requested','instance_id','evidence_receipt_id','evaluation_id','error_code']) THEN RAISE EXCEPTION 'frozen execution identity';END IF;
 IF TG_TABLE_NAME='environment_build_jobs' THEN
  IF OLD.state IN('completed','cancelled') OR NEW.revision<>OLD.revision+1 THEN RAISE EXCEPTION 'invalid build transition';END IF;
 END IF;
 IF TG_TABLE_NAME='environment_attempts' AND OLD.state IN('assessed','failed','cancelled','uncertain') THEN RAISE EXCEPTION 'terminal attempt immutable';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER build_guard BEFORE UPDATE ON anvil.environment_build_jobs FOR EACH ROW EXECUTE FUNCTION anvil.environment_job_guard();
CREATE TRIGGER attempt_guard BEFORE UPDATE ON anvil.environment_attempts FOR EACH ROW EXECUTE FUNCTION anvil.environment_job_guard();
