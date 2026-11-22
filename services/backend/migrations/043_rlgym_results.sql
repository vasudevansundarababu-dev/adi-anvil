-- RL Gym v2 work package 2.8: report revisions and PDF renders, RL engineer diagnoses, packages. Schema `results`.
CREATE SCHEMA IF NOT EXISTS results;

-- A report revision is the exact view the report and its PDF were built from (view_sha256 over that view).
CREATE TABLE results.reports(
 run_id text NOT NULL REFERENCES runs.runs, workspace_id uuid NOT NULL, revision int NOT NULL CHECK (revision > 0),
 pass_id uuid NOT NULL REFERENCES scoring.scoring_passes, view jsonb NOT NULL, view_sha256 char(64) NOT NULL,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (run_id, revision), UNIQUE (run_id, view_sha256));
CREATE TRIGGER reports_final BEFORE UPDATE OR DELETE ON results.reports
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE results.report_renders(
 run_id text NOT NULL, revision int NOT NULL, workspace_id uuid NOT NULL,
 pdf_ref text NOT NULL, pdf_sha256 char(64) NOT NULL, pages int NOT NULL CHECK (pages > 0), bytes int NOT NULL,
 renderer text NOT NULL, created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (run_id, revision), FOREIGN KEY (run_id, revision) REFERENCES results.reports);
CREATE TRIGGER report_renders_final BEFORE UPDATE OR DELETE ON results.report_renders
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

-- The RL engineer's diagnosis of one episode. It never changes a score, a task or an evaluator.
CREATE TABLE results.diagnoses(
 episode_id text PRIMARY KEY REFERENCES runs.episodes, workspace_id uuid NOT NULL,
 task_finding text NOT NULL CHECK (task_finding IN ('unresolved','task_correct','task_defect')),
 attributed_to text NOT NULL CHECK (attributed_to IN ('unresolved','agent','task','rubric','grader','environment')),
 evaluator_finding text NOT NULL CHECK (evaluator_finding IN ('unresolved','evaluator_correct','grader_defect','criterion_defect')),
 strength text NOT NULL CHECK (strength IN ('unresolved','strong','moderate','weak')),
 evidence_items text[] NOT NULL, why text NOT NULL DEFAULT '', inbox_item_id text,
 saved_by text NOT NULL, saved_at timestamptz NOT NULL DEFAULT now());

-- A package: the immutable delivery bundle of selected runs (manifests, scores, report revisions, data card).
CREATE TABLE results.packages(
 id text PRIMARY KEY, workspace_id uuid NOT NULL, run_ids text[] NOT NULL CHECK (cardinality(run_ids) > 0),
 contents jsonb NOT NULL, package_ref text NOT NULL, package_sha256 char(64) NOT NULL,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TRIGGER packages_final BEFORE UPDATE OR DELETE ON results.packages
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['results.reports','results.report_renders','results.diagnoses','results.packages'] LOOP
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP; END $$;

GRANT USAGE ON SCHEMA results TO anvil_app;
GRANT SELECT, INSERT ON results.reports, results.report_renders, results.packages TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON results.diagnoses TO anvil_app;
