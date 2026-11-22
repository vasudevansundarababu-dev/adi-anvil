-- RL Gym v2 work package 2.7: runs (admission, frozen manifest, episodes, sealed evidence) and scoring (passes,
-- criterion receipts, episode scores, Trust & Safety outcomes). Schemas `runs` and `scoring`.
CREATE SCHEMA IF NOT EXISTS runs;
CREATE SCHEMA IF NOT EXISTS scoring;

-- Locally built environment images (built with Docker from the Studio recipe; not workspace data).
CREATE TABLE runs.environment_images(
 environment_version_id text PRIMARY KEY REFERENCES catalog.environment_versions,
 image_tag text NOT NULL, local_image_id text NOT NULL, base_image text NOT NULL,
 context_sha256 char(64) NOT NULL, image_seed_sha256 char(64) NOT NULL, cases int NOT NULL,
 built_at timestamptz NOT NULL DEFAULT now(), build_seconds numeric NOT NULL);

CREATE SEQUENCE runs.run_number;
CREATE TABLE runs.runs(
 id text PRIMARY KEY CHECK (id ~ '^run-[0-9]{4,}$'), workspace_id uuid NOT NULL, project_id text NOT NULL,
 name text NOT NULL CHECK (length(trim(name)) > 0), suite_version_id uuid NOT NULL REFERENCES suites.suite_versions,
 model_set jsonb NOT NULL, attempts int NOT NULL CHECK (attempts BETWEEN 1 AND 10),
 budget_usd numeric NOT NULL CHECK (budget_usd > 0),
 episode_timeout_s int NOT NULL DEFAULT 600 CHECK (episode_timeout_s >= 60),
 infra_retries int NOT NULL DEFAULT 2 CHECK (infra_retries BETWEEN 0 AND 5),
 execution_mode text NOT NULL CHECK (execution_mode IN ('controlled_mock','live')),
 state text NOT NULL CHECK (state IN ('admitted','running','completed','failed','cancelled','refused')),
 refusal_reasons jsonb, created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz, finished_at timestamptz, cancel_requested_by text, cancel_requested_at timestamptz,
 rescored boolean NOT NULL DEFAULT false,
 CHECK ((state = 'refused') = (refusal_reasons IS NOT NULL)),
 FOREIGN KEY (workspace_id, project_id) REFERENCES projects.projects);
CREATE INDEX ON runs.runs (workspace_id, state, created_at DESC);

-- The manifest is frozen at Start run and never changes, whatever is later revoked or released.
CREATE TABLE runs.run_manifests(
 run_id text PRIMARY KEY REFERENCES runs.runs, workspace_id uuid NOT NULL,
 manifest jsonb NOT NULL, manifest_sha256 char(64) NOT NULL UNIQUE);
CREATE TRIGGER run_manifests_final BEFORE UPDATE OR DELETE ON runs.run_manifests
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

CREATE TABLE runs.episodes(
 id text PRIMARY KEY, run_id text NOT NULL REFERENCES runs.runs, workspace_id uuid NOT NULL,
 kind text NOT NULL CHECK (kind IN ('case','safety')),
 task_import_id uuid NOT NULL REFERENCES projects.task_imports, task_id text NOT NULL, task_revision int NOT NULL,
 case_id text NOT NULL, application_type text NOT NULL, completeness text NOT NULL, edge_cases text[] NOT NULL,
 ts_prompt_id text, ts_category text,
 system_id text NOT NULL, system_version int NOT NULL, attempt int NOT NULL CHECK (attempt >= 1),
 state text NOT NULL CHECK (state IN ('queued','running','scoring','scored','errored','timed_out','cancelled')),
 tries int NOT NULL DEFAULT 0, last_error text,
 likely_cause text, likely_cause_source text CHECK (likely_cause_source IN ('assist','sme','rl_engineer','rule')),
 lease_owner text, lease_until timestamptz, queued_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((kind = 'safety') = (ts_prompt_id IS NOT NULL)),
 UNIQUE NULLS NOT DISTINCT (run_id, task_import_id, case_id, ts_prompt_id, system_id, attempt));
CREATE INDEX ON runs.episodes (run_id, state);
CREATE INDEX ON runs.episodes (state, queued_at) WHERE state = 'queued';
CREATE INDEX ON runs.episodes (lease_until) WHERE state = 'running';

CREATE TABLE runs.episode_attempts(
 episode_id text NOT NULL REFERENCES runs.episodes, workspace_id uuid NOT NULL, try int NOT NULL,
 started_at timestamptz NOT NULL, ended_at timestamptz,
 outcome text CHECK (outcome IN ('sealed','errored','timed_out','lease_lost','cancelled')),
 note text, PRIMARY KEY (episode_id, try));

-- Sealed evidence: one bundle per sealed episode; the file is read-only and its hash is checked before scoring.
CREATE TABLE runs.sealed_evidence(
 episode_id text PRIMARY KEY REFERENCES runs.episodes, workspace_id uuid NOT NULL, try int NOT NULL,
 bundle_ref text NOT NULL, sealed_sha256 char(64) NOT NULL, tokens_in int NOT NULL, tokens_out int NOT NULL,
 cost_usd numeric NOT NULL, timings jsonb NOT NULL, synthetic boolean NOT NULL,
 sealed_at timestamptz NOT NULL DEFAULT now());
CREATE TRIGGER sealed_evidence_final BEFORE UPDATE OR DELETE ON runs.sealed_evidence
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

CREATE TABLE runs.instances(
 id text PRIMARY KEY, workspace_id uuid NOT NULL, run_id text NOT NULL REFERENCES runs.runs,
 environment_version_id text NOT NULL, local_image_id text NOT NULL, container text NOT NULL,
 started_at timestamptz NOT NULL DEFAULT now(), stopped_at timestamptz, idle_timeout_s int NOT NULL,
 cost_usd numeric NOT NULL DEFAULT 0);

-- Comparison of two runs (SCREENS 3.19); the results module (2.8) reads it.
CREATE TABLE runs.comparisons(
 id text PRIMARY KEY, workspace_id uuid NOT NULL, baseline_run_id text NOT NULL REFERENCES runs.runs,
 compared_run_id text NOT NULL REFERENCES runs.runs, result jsonb NOT NULL, result_sha256 char(64) NOT NULL,
 saved_by text NOT NULL, saved_at timestamptz NOT NULL DEFAULT now(), CHECK (baseline_run_id <> compared_run_id));

-- scoring ---------------------------------------------------------------------------------------------------------
-- Private reference answers fetched from the registry for the cases a run selected. Read only by the scorer (and,
-- in 2.9, audited reviewer-only views); never sent to a runner, a model or an export.
CREATE TABLE scoring.case_references(
 workspace_id uuid NOT NULL, environment_version_id text NOT NULL, case_id text NOT NULL,
 reference jsonb NOT NULL, reference_sha256 char(64) NOT NULL, fetched_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id, environment_version_id, case_id));
CREATE TRIGGER case_references_final BEFORE UPDATE OR DELETE ON scoring.case_references
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

CREATE TABLE scoring.scoring_passes(
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, run_id text NOT NULL REFERENCES runs.runs, pass int NOT NULL,
 reason text NOT NULL CHECK (reason IN ('initial','rescore')), evaluator_versions jsonb NOT NULL,
 evaluator_versions_sha256 char(64) NOT NULL, requested_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, UNIQUE (run_id, pass));
CREATE TABLE scoring.criterion_receipts(
 episode_id text NOT NULL REFERENCES runs.episodes, pass_id uuid NOT NULL REFERENCES scoring.scoring_passes,
 workspace_id uuid NOT NULL, criterion_id text NOT NULL, configuration_id text NOT NULL, configuration_version int NOT NULL,
 verdict text NOT NULL CHECK (verdict IN ('pass','partial','fail','blocked','incomplete','error')),
 points numeric, weight numeric NOT NULL, evidence_refs jsonb NOT NULL, detail jsonb NOT NULL,
 receipt_sha256 char(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (episode_id, pass_id, criterion_id));
CREATE TRIGGER criterion_receipts_final BEFORE UPDATE OR DELETE ON scoring.criterion_receipts
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE scoring.episode_scores(
 episode_id text NOT NULL REFERENCES runs.episodes, pass_id uuid NOT NULL REFERENCES scoring.scoring_passes,
 workspace_id uuid NOT NULL, score numeric, passed boolean NOT NULL, blocked_reasons jsonb NOT NULL,
 failed_criteria text[] NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (episode_id, pass_id));
CREATE TRIGGER episode_scores_final BEFORE UPDATE OR DELETE ON scoring.episode_scores
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE scoring.safety_outcomes(
 episode_id text NOT NULL REFERENCES runs.episodes, pass_id uuid NOT NULL REFERENCES scoring.scoring_passes,
 workspace_id uuid NOT NULL, category_key text NOT NULL,
 outcome text NOT NULL CHECK (outcome IN ('resisted','acted_blocked','acted_not_blocked','unscored')),
 attempted boolean, blocked boolean, critical boolean NOT NULL, severity text NOT NULL, grader text NOT NULL,
 evidence jsonb NOT NULL, PRIMARY KEY (episode_id, pass_id));
CREATE TRIGGER safety_outcomes_final BEFORE UPDATE OR DELETE ON scoring.safety_outcomes
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['runs.runs','runs.run_manifests','runs.episodes','runs.episode_attempts','runs.sealed_evidence',
  'runs.instances','runs.comparisons','scoring.case_references','scoring.scoring_passes','scoring.criterion_receipts',
  'scoring.episode_scores','scoring.safety_outcomes'] LOOP
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP; END $$;

GRANT USAGE ON SCHEMA runs, scoring TO anvil_app;
GRANT USAGE ON SEQUENCE runs.run_number TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON runs.environment_images, runs.runs, runs.episodes, runs.episode_attempts,
 runs.instances, scoring.scoring_passes TO anvil_app;
GRANT SELECT, INSERT ON runs.run_manifests, runs.sealed_evidence, runs.comparisons, scoring.case_references,
 scoring.criterion_receipts, scoring.episode_scores, scoring.safety_outcomes TO anvil_app;
