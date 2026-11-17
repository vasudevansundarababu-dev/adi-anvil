CREATE SCHEMA campaign_private;
CREATE TABLE campaign_private.references(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),task_id text NOT NULL,task_version text NOT NULL,
 payload_sha256 text NOT NULL,case_id text NOT NULL,case_sha256 text NOT NULL,
 content jsonb NOT NULL CHECK(octet_length(content::text)<=1048576),content_sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id));
ALTER TABLE campaign_private.references ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.references FORCE ROW LEVEL SECURITY;
CREATE POLICY private_read ON campaign_private.references FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT USAGE ON SCHEMA campaign_private TO anvil_golden_grader;
GRANT SELECT ON campaign_private.references TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.references FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE TABLE marketing_runtime.grading_jobs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,kind text NOT NULL CHECK(kind IN('benchmark_run','workspace_group')),
 task_group_id uuid NOT NULL,task_id text NOT NULL,model_key text NOT NULL,repetition integer NOT NULL CHECK(repetition>=0),
 episode_id uuid NOT NULL,generation integer NOT NULL,plan_id uuid,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN('queued','completed')),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),
 FOREIGN KEY(project_id,episode_id) REFERENCES marketing_runtime.episodes(project_id,id),
 FOREIGN KEY(episode_id,generation) REFERENCES marketing_runtime.seals(episode_id,generation),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id),
 UNIQUE(project_id,id),UNIQUE(run_id,episode_id,generation));
ALTER TABLE marketing_runtime.grading_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing_runtime.grading_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY scheduler_queue ON marketing_runtime.grading_jobs TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
CREATE POLICY private_grade ON marketing_runtime.grading_jobs TO anvil_golden_grader USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
GRANT SELECT,INSERT ON marketing_runtime.grading_jobs TO anvil_golden_scheduler;
GRANT SELECT,UPDATE(state) ON marketing_runtime.grading_jobs TO anvil_golden_grader;
CREATE POLICY campaign_run_read ON anvil.benchmark_runs FOR SELECT TO anvil_golden_grader USING(
 banking.runtime_scope(project_id) AND EXISTS(SELECT 1 FROM marketing_runtime.grading_jobs j WHERE j.project_id=benchmark_runs.project_id AND j.run_id=benchmark_runs.id AND j.kind='benchmark_run'));
CREATE FUNCTION marketing_runtime.grading_job_transition() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR OLD.state<>'queued' OR NEW.state<>'completed' OR (to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state') THEN
  RAISE EXCEPTION 'Campaign grading job terminal identity is immutable';
 END IF; RETURN NEW;END $$;
CREATE TRIGGER terminal_custody BEFORE UPDATE OR DELETE ON marketing_runtime.grading_jobs FOR EACH ROW EXECUTE FUNCTION marketing_runtime.grading_job_transition();

CREATE TABLE campaign_private.results(
 project_id uuid NOT NULL,job_id uuid PRIMARY KEY,result jsonb NOT NULL CHECK(octet_length(result::text)<=4194304),
 result_sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,job_id) REFERENCES marketing_runtime.grading_jobs(project_id,id));
ALTER TABLE campaign_private.results ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.results FORCE ROW LEVEL SECURITY;
CREATE POLICY private_grade ON campaign_private.results TO anvil_golden_grader USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
GRANT SELECT,INSERT ON campaign_private.results TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.results FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE POLICY private_episode_metadata ON marketing_runtime.episodes FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT(id,project_id,case_id,dataset_id,dataset_version,dataset_sha256,snapshot_sha256,generation) ON marketing_runtime.episodes TO anvil_golden_grader;
INSERT INTO anvil.schema_versions(version) VALUES(99);
