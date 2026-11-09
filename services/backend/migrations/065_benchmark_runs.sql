-- Versioned Project imports, executable plans and durable local benchmark jobs.
CREATE TABLE anvil.benchmark_task_groups(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 source_project_id text NOT NULL,source_version text NOT NULL,name text NOT NULL,
 content jsonb NOT NULL,content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,source_project_id,source_version));
CREATE TABLE anvil.benchmark_policy_sets(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,
 content jsonb NOT NULL,content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),
 UNIQUE(project_id,id),UNIQUE(task_group_id,content_sha256));
CREATE TABLE anvil.benchmark_policy_mappings(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,policy_set_id uuid NOT NULL,
 policy_id text NOT NULL,policy_version text NOT NULL,rule_id text NOT NULL,
 configuration_id uuid NOT NULL,evidence_field text NOT NULL,scope jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,policy_set_id) REFERENCES anvil.benchmark_policy_sets(project_id,id),
 FOREIGN KEY(project_id,configuration_id) REFERENCES anvil.evaluator_configurations(project_id,id),
 UNIQUE(project_id,id));
CREATE TABLE anvil.benchmark_method_profiles(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL,method_key text NOT NULL,configuration jsonb NOT NULL,
 content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id));
CREATE TABLE anvil.benchmark_execution_plans(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,name text NOT NULL,
 snapshot jsonb NOT NULL,snapshot_sha256 text NOT NULL CHECK(snapshot_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.benchmark_runs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,plan_id uuid NOT NULL,
 snapshot jsonb NOT NULL,snapshot_sha256 text NOT NULL CHECK(snapshot_sha256~'^[a-f0-9]{64}$'),
 report_policy jsonb NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),state text NOT NULL DEFAULT 'queued'
 CHECK(state IN ('queued','running','completed','failed','blocked')),
 executed_by uuid REFERENCES anvil.users(id),admin_execution boolean NOT NULL DEFAULT false,
 executed_at timestamptz,result jsonb,result_sha256 text,graph_thread_id uuid NOT NULL UNIQUE,
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.benchmark_execution_plans(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.benchmark_run_jobs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','completed','failed')),
 claim_token uuid,created_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id),UNIQUE(run_id));
CREATE TABLE anvil.benchmark_run_cells(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,
 model_key text NOT NULL,task_key text NOT NULL,environment_key text NOT NULL,repetition integer NOT NULL,
 capture jsonb NOT NULL,capture_sha256 text NOT NULL CHECK(capture_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id),UNIQUE(project_id,id),
 UNIQUE(run_id,model_key,task_key,environment_key,repetition));
CREATE TABLE anvil.benchmark_run_scores(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,cell_id uuid NOT NULL,
 assessment jsonb NOT NULL,assessment_sha256 text NOT NULL CHECK(assessment_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,cell_id) REFERENCES anvil.benchmark_run_cells(project_id,id),UNIQUE(cell_id));
CREATE TABLE anvil.benchmark_run_report_decisions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,result_sha256 text NOT NULL,
 decision text NOT NULL CHECK(decision IN ('reviewed','admin_approved')),
 rationale text NOT NULL CHECK(length(rationale) BETWEEN 10 AND 2000),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id),
 UNIQUE(run_id,result_sha256,created_by));
CREATE TABLE anvil.benchmark_remediation_packs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,content jsonb NOT NULL,
 content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_runs(project_id,id),UNIQUE(project_id,id));
CREATE FUNCTION anvil.benchmark_new_author() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid
 OR NOT anvil.golden_engineer(NEW.project_id) THEN RAISE EXCEPTION 'authenticated project engineer required';END IF;
 IF TG_TABLE_NAME='benchmark_runs' THEN
  IF NEW.state<>'queued' OR NEW.executed_by IS NOT NULL OR NEW.admin_execution OR NEW.result IS NOT NULL OR NEW.result_sha256 IS NOT NULL OR NEW.executed_at IS NOT NULL THEN RAISE EXCEPTION 'new Run cannot claim execution or approval'; END IF;
  IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_execution_plans p WHERE p.id=NEW.plan_id AND p.project_id=NEW.project_id AND p.snapshot=NEW.snapshot AND p.snapshot_sha256=NEW.snapshot_sha256) THEN RAISE EXCEPTION 'exact saved plan required';END IF;
  IF jsonb_typeof(NEW.report_policy->'required_reviewers') IS DISTINCT FROM 'number' OR (NEW.report_policy->>'required_reviewers')::int NOT BETWEEN 0 AND 10 OR (NEW.report_policy->>'required_reviewers')::int IS DISTINCT FROM coalesce((SELECT required_reviewers FROM anvil.benchmark_report_policies WHERE project_id=NEW.project_id ORDER BY created_at DESC,id DESC LIMIT 1),1) THEN RAISE EXCEPTION 'current report policy required';END IF;
 END IF;
 RETURN NEW;END $$;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['benchmark_task_groups','benchmark_policy_sets','benchmark_policy_mappings','benchmark_method_profiles','benchmark_execution_plans','benchmark_runs','benchmark_run_report_decisions','benchmark_remediation_packs'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY engineer ON anvil.%I TO anvil_app USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 EXECUTE format('CREATE TRIGGER actual_author BEFORE INSERT ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.benchmark_new_author()',t);
 IF t<>'benchmark_runs' THEN EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);END IF;
 END LOOP;END $$;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['benchmark_run_jobs','benchmark_run_cells','benchmark_run_scores'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY read_engineer ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app',t);
 IF t<>'benchmark_run_jobs' THEN EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);END IF;
 END LOOP;END $$;
CREATE POLICY enqueue ON anvil.benchmark_run_jobs FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id));
GRANT INSERT ON anvil.benchmark_run_jobs TO anvil_app;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['benchmark_task_groups','benchmark_policy_sets','benchmark_policy_mappings','benchmark_method_profiles','benchmark_execution_plans','benchmark_runs','benchmark_run_jobs','benchmark_run_cells','benchmark_run_scores'] LOOP
 IF t='benchmark_run_jobs' THEN
 EXECUTE format('CREATE POLICY worker ON anvil.%I TO anvil_worker USING(current_user=''anvil_worker'') WITH CHECK(current_user=''anvil_worker'')',t);
 ELSE
 EXECUTE format('CREATE POLICY worker ON anvil.%I TO anvil_worker USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 END IF;
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_worker',t);
 END LOOP;END $$;
GRANT UPDATE(state,claim_token,finished_at) ON anvil.benchmark_run_jobs TO anvil_worker;
GRANT UPDATE(state,executed_by,admin_execution,executed_at,result,result_sha256) ON anvil.benchmark_runs TO anvil_worker;
GRANT INSERT ON anvil.benchmark_run_cells,anvil.benchmark_run_scores TO anvil_worker;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['evaluator_configurations','evaluator_validation_receipts','evaluator_revocations'] LOOP
 EXECUTE format('ALTER POLICY scope ON anvil.%I TO anvil_app',t);
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_worker',t);
 EXECUTE format('CREATE POLICY worker_read ON anvil.%I FOR SELECT TO anvil_worker USING(anvil.in_scope(project_id))',t);
 END LOOP;END $$;
CREATE FUNCTION anvil.guard_benchmark_run_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF current_user<>'anvil_worker' OR OLD.state IN ('completed','failed','blocked') THEN RAISE EXCEPTION 'terminal benchmark Run is immutable';END IF;
 IF (OLD.state='queued' AND NEW.state NOT IN ('running','blocked','failed')) OR
 (OLD.state='running' AND NEW.state NOT IN ('completed','failed','blocked')) THEN RAISE EXCEPTION 'invalid benchmark transition';END IF;
 IF NEW.state='running' THEN
  IF NEW.executed_by IS DISTINCT FROM OLD.created_by OR NEW.admin_execution IS DISTINCT FROM EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE m.project_id=NEW.project_id AND m.user_id=OLD.created_by AND m.active AND m.role='admin') THEN RAISE EXCEPTION 'actual execution identity required'; END IF;
 END IF;
 RETURN NEW;END $$;
CREATE TRIGGER run_state BEFORE UPDATE OR DELETE ON anvil.benchmark_runs FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_run_update();
CREATE FUNCTION anvil.guard_benchmark_report_decision() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE r anvil.benchmark_runs; BEGIN
 SELECT * INTO r FROM anvil.benchmark_runs WHERE id=NEW.run_id AND project_id=NEW.project_id;
 IF NOT FOUND OR r.state<>'completed' OR r.result_sha256 IS DISTINCT FROM NEW.result_sha256 THEN RAISE EXCEPTION 'exact completed result required';END IF;
 IF NEW.decision='admin_approved' AND NOT EXISTS(SELECT 1 FROM anvil.memberships WHERE project_id=NEW.project_id AND user_id=NEW.created_by AND active AND role='admin') THEN RAISE EXCEPTION 'actual Admin required';END IF;
 IF NEW.decision='reviewed' AND NEW.created_by=r.executed_by THEN RAISE EXCEPTION 'distinct actual report reviewer required';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER exact_report BEFORE INSERT ON anvil.benchmark_run_report_decisions FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_report_decision();
INSERT INTO anvil.schema_versions(version) VALUES('065') ON CONFLICT DO NOTHING;
