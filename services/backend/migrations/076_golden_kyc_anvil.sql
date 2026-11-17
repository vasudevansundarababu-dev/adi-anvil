-- Golden KYC uses Anvil's existing catalog/environment/evaluator/run registries.
CREATE TABLE banking.anvil_imports(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,pack_id uuid NOT NULL,
 task_group_id uuid NOT NULL,environment_id uuid NOT NULL,
 manifest jsonb NOT NULL,manifest_sha256 text NOT NULL CHECK(manifest_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,pack_id,manifest_sha256),
 FOREIGN KEY(project_id,pack_id) REFERENCES banking.packs(project_id,id),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),
 FOREIGN KEY(project_id,environment_id) REFERENCES anvil.environment_versions(project_id,id));
CREATE TABLE banking.anvil_runs(
 project_id uuid NOT NULL,run_id uuid PRIMARY KEY,import_id uuid NOT NULL,
 software_run_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id),
 FOREIGN KEY(project_id,import_id) REFERENCES banking.anvil_imports(project_id,id),
 FOREIGN KEY(project_id,software_run_id) REFERENCES banking.runs(project_id,id));
CREATE TABLE banking.execution_jobs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL UNIQUE,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','captured','completed','failed')),
 claim_token uuid,error_code text,created_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['anvil_imports','anvil_runs','execution_jobs'] LOOP
  EXECUTE format('ALTER TABLE banking.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE banking.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY engineer_read ON banking.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY engineer_insert ON banking.%I FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY scheduler_scope ON banking.%I TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE POLICY grader_read ON banking.%I FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('GRANT SELECT,INSERT ON banking.%I TO anvil_app',t);
  EXECUTE format('GRANT SELECT ON banking.%I TO anvil_golden_scheduler,anvil_golden_grader',t);
  IF t<>'execution_jobs' THEN
   EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  END IF;
 END LOOP;
END $$;
GRANT UPDATE(state,claim_token,error_code,finished_at) ON banking.execution_jobs TO anvil_golden_scheduler;
GRANT INSERT ON banking.anvil_runs TO anvil_golden_scheduler;
GRANT SELECT ON anvil.benchmark_task_groups,anvil.benchmark_execution_plans,anvil.benchmark_runs,anvil.environment_versions,anvil.environment_task_bindings,anvil.evaluator_configurations,anvil.evaluator_validation_receipts,anvil.evaluator_revocations TO anvil_golden_scheduler,anvil_golden_grader;
GRANT SELECT ON anvil.benchmark_run_cells,anvil.benchmark_run_scores TO anvil_golden_scheduler,anvil_golden_grader;
GRANT UPDATE(state,executed_by,admin_execution,executed_at,result,result_sha256) ON anvil.benchmark_runs TO anvil_golden_scheduler;
GRANT INSERT ON anvil.benchmark_run_cells TO anvil_golden_scheduler;
GRANT INSERT ON anvil.benchmark_run_scores TO anvil_golden_grader;
GRANT UPDATE(state,error_code,finished_at) ON banking.execution_jobs TO anvil_golden_grader;
CREATE POLICY grader_job_update ON banking.execution_jobs FOR UPDATE TO anvil_golden_grader USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['benchmark_task_groups','benchmark_execution_plans','environment_versions','environment_task_bindings','evaluator_configurations','evaluator_validation_receipts','evaluator_revocations'] LOOP
  EXECUTE format('CREATE POLICY golden_runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
 END LOOP;
END $$;
CREATE POLICY golden_run_read ON anvil.benchmark_runs FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id) AND EXISTS(SELECT 1 FROM banking.anvil_runs l WHERE l.run_id=id));
CREATE POLICY golden_queued_read ON anvil.benchmark_runs FOR SELECT TO anvil_golden_scheduler USING(banking.runtime_scope(project_id) AND snapshot->>'schema_version'='anvil.golden-kyc-execution-plan.v1');
CREATE POLICY golden_run_update ON anvil.benchmark_runs FOR UPDATE TO anvil_golden_scheduler USING(banking.runtime_scope(project_id) AND EXISTS(SELECT 1 FROM banking.anvil_runs l WHERE l.run_id=id)) WITH CHECK(banking.runtime_scope(project_id) AND EXISTS(SELECT 1 FROM banking.anvil_runs l WHERE l.run_id=id));
CREATE POLICY golden_capture ON anvil.benchmark_run_cells TO anvil_golden_scheduler USING(banking.runtime_scope(project_id) AND EXISTS(SELECT 1 FROM banking.anvil_runs l WHERE l.run_id=benchmark_run_cells.run_id)) WITH CHECK(banking.runtime_scope(project_id) AND EXISTS(SELECT 1 FROM banking.anvil_runs l WHERE l.run_id=benchmark_run_cells.run_id));
CREATE POLICY golden_grader_cells ON anvil.benchmark_run_cells FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
CREATE POLICY golden_scores ON anvil.benchmark_run_scores TO anvil_golden_grader USING(banking.runtime_scope(project_id) AND EXISTS(SELECT 1 FROM anvil.benchmark_run_cells b JOIN banking.anvil_runs l ON l.run_id=b.run_id WHERE b.id=cell_id)) WITH CHECK(banking.runtime_scope(project_id) AND EXISTS(SELECT 1 FROM anvil.benchmark_run_cells b JOIN banking.anvil_runs l ON l.run_id=b.run_id WHERE b.id=cell_id));
CREATE POLICY golden_scheduler_scores ON anvil.benchmark_run_scores FOR SELECT TO anvil_golden_scheduler USING(banking.runtime_scope(project_id));
-- Preserve existing transitions and identity semantics; only exact linked Golden
-- runs admit the disjoint scheduler capability. No grant to ordinary API/worker.
CREATE OR REPLACE FUNCTION anvil.guard_benchmark_run_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE golden boolean; BEGIN
 IF current_user='anvil_worker' THEN golden=false;
 ELSE golden=pg_has_role(current_user,'anvil_golden_scheduler','MEMBER') AND EXISTS(SELECT 1 FROM banking.anvil_runs l WHERE l.run_id=OLD.id AND banking.runtime_scope(l.project_id));END IF;
 IF (current_user<>'anvil_worker' AND NOT golden) OR OLD.state IN ('completed','failed','blocked') THEN RAISE EXCEPTION 'terminal benchmark Run is immutable';END IF;
 IF (OLD.state='queued' AND NEW.state NOT IN ('running','blocked','failed')) OR (OLD.state='running' AND NEW.state NOT IN ('completed','failed','blocked')) THEN RAISE EXCEPTION 'invalid benchmark transition';END IF;
 IF (to_jsonb(OLD)-ARRAY['state','executed_by','admin_execution','executed_at','result','result_sha256']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['state','executed_by','admin_execution','executed_at','result','result_sha256']) THEN RAISE EXCEPTION 'frozen Run changed';END IF;
 IF NEW.state='running' THEN
  IF NEW.executed_by IS DISTINCT FROM OLD.created_by OR NEW.admin_execution IS DISTINCT FROM EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE m.project_id=NEW.project_id AND m.user_id=OLD.created_by AND m.active AND m.role='admin') THEN RAISE EXCEPTION 'actual execution identity required';END IF;
 END IF;
 RETURN NEW;END $$;
INSERT INTO anvil.schema_versions(version) VALUES(76);
