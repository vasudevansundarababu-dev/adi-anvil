-- RL Gym v2 work package 2.6: suites (versions with draft and save), bindings, data plans, Trust & Safety plans.
-- A saved suite version never changes (suite_sha256); edits happen on a draft and saving makes version N+1.
CREATE SCHEMA IF NOT EXISTS suites;

CREATE TABLE suites.suites(
 workspace_id uuid NOT NULL, project_id text NOT NULL, suite_id text NOT NULL CHECK (suite_id ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
 name text NOT NULL, is_default boolean NOT NULL DEFAULT false, created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id, project_id, suite_id));
CREATE UNIQUE INDEX one_default_suite ON suites.suites (workspace_id, project_id) WHERE is_default;

CREATE TABLE suites.suite_versions(
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, project_id text NOT NULL, suite_id text NOT NULL,
 version int, name text NOT NULL,
 state text NOT NULL CHECK (state IN ('draft','saved')),
 suite_sha256 char(64), planned_on_env_version text NOT NULL,
 based_on uuid REFERENCES suites.suite_versions(id),
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 saved_by text, saved_at timestamptz,
 CHECK ((state = 'draft') = (version IS NULL AND suite_sha256 IS NULL)),
 UNIQUE (workspace_id, project_id, suite_id, version),
 FOREIGN KEY (workspace_id, project_id, suite_id) REFERENCES suites.suites);
CREATE UNIQUE INDEX one_draft_per_suite ON suites.suite_versions (workspace_id, project_id, suite_id) WHERE state = 'draft';

CREATE TABLE suites.suite_bindings(
 suite_version_id uuid NOT NULL REFERENCES suites.suite_versions, workspace_id uuid NOT NULL, alias text NOT NULL,
 rule_kind text NOT NULL CHECK (rule_kind IN ('pinned','same_data','latest','project_rule')),
 pinned_version_id text, seed_family text,
 source text NOT NULL CHECK (source IN ('project_default','ai_suggestion','custom')),
 reason text, CHECK (source <> 'custom' OR length(trim(coalesce(reason,''))) > 0),
 PRIMARY KEY (suite_version_id, alias));
CREATE TABLE suites.suite_criterion_bindings(
 suite_version_id uuid NOT NULL REFERENCES suites.suite_versions, workspace_id uuid NOT NULL, criterion_id text NOT NULL,
 configuration_id text NOT NULL,
 rule_kind text NOT NULL CHECK (rule_kind IN ('latest_qualified','pinned','project_rule')), pinned_version int,
 CHECK (rule_kind <> 'pinned' OR pinned_version IS NOT NULL),
 source text NOT NULL CHECK (source IN ('project_default','ai_suggestion','custom')),
 reason text, CHECK (source <> 'custom' OR length(trim(coalesce(reason,''))) > 0),
 PRIMARY KEY (suite_version_id, criterion_id));
CREATE TABLE suites.suite_tasks(
 suite_version_id uuid NOT NULL REFERENCES suites.suite_versions, workspace_id uuid NOT NULL, task_import_id uuid NOT NULL,
 PRIMARY KEY (suite_version_id, task_import_id));

CREATE TABLE suites.data_plans(
 suite_version_id uuid PRIMARY KEY REFERENCES suites.suite_versions, workspace_id uuid NOT NULL,
 sample_size int NOT NULL CHECK (sample_size > 0), stratify_by text[] NOT NULL,
 completeness_quotas jsonb NOT NULL, required_edges jsonb NOT NULL DEFAULT '{}',
 sampling_seed bigint NOT NULL,
 missing_policy text NOT NULL CHECK (missing_policy IN ('block','use_available')),
 source text NOT NULL DEFAULT 'manual', ai_suggested jsonb);
CREATE TABLE suites.data_plan_cells(
 suite_version_id uuid NOT NULL REFERENCES suites.data_plans, workspace_id uuid NOT NULL, cell_key text NOT NULL,
 dimension_values jsonb NOT NULL,
 quota_kind text NOT NULL CHECK (quota_kind IN ('count','percent')), quota_value numeric NOT NULL,
 quota int NOT NULL CHECK (quota >= 0), original_quota int, available int NOT NULL, inbox_item_id text,
 PRIMARY KEY (suite_version_id, cell_key));

CREATE TABLE suites.ts_plans(
 suite_version_id uuid PRIMARY KEY REFERENCES suites.suite_versions, workspace_id uuid NOT NULL,
 enabled boolean NOT NULL, domain text NOT NULL, strategies text[] NOT NULL,
 prompts_per_category int NOT NULL CHECK (prompts_per_category BETWEEN 1 AND 10), placement text NOT NULL
  CHECK (placement IN ('tool_result','user_message','case_document')),
 state text NOT NULL CHECK (state IN ('draft','generated','approved')),
 generator text, approved_by text, approved_at timestamptz, prompt_set_sha256 char(64),
 promptfoo_version text NOT NULL,
 CHECK (state <> 'approved' OR (approved_by IS NOT NULL AND prompt_set_sha256 IS NOT NULL)));
CREATE TABLE suites.ts_categories(
 suite_version_id uuid NOT NULL REFERENCES suites.ts_plans, workspace_id uuid NOT NULL, key text NOT NULL,
 name text NOT NULL, category_group text NOT NULL, source text NOT NULL CHECK (source IN ('pack','custom')),
 boundary_tested text NOT NULL, observable_check text NOT NULL, promptfoo_plugin text, grounding text, policy_text text,
 PRIMARY KEY (suite_version_id, key));
CREATE TABLE suites.ts_prompts(
 suite_version_id uuid NOT NULL REFERENCES suites.ts_plans, workspace_id uuid NOT NULL, id text NOT NULL,
 category_key text NOT NULL, text text NOT NULL, strategy text NOT NULL, severity text NOT NULL,
 approved boolean NOT NULL DEFAULT true, synthetic boolean NOT NULL DEFAULT true,
 PRIMARY KEY (suite_version_id, id));

-- A saved version and everything under it are final.
CREATE FUNCTION suites.saved_is_final() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sv uuid; st text;
BEGIN
 sv := CASE WHEN TG_OP = 'DELETE' THEN OLD.suite_version_id ELSE NEW.suite_version_id END;
 SELECT state INTO st FROM suites.suite_versions WHERE id = sv;
 IF st = 'saved' THEN RAISE EXCEPTION 'saved suite version % is final; edit a draft', sv; END IF;
 RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['suites.suite_bindings','suites.suite_criterion_bindings','suites.suite_tasks','suites.data_plans',
  'suites.data_plan_cells','suites.ts_plans','suites.ts_categories','suites.ts_prompts'] LOOP
  EXECUTE format('CREATE TRIGGER saved_is_final BEFORE INSERT OR UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION suites.saved_is_final()', t);
 END LOOP; END $$;
CREATE FUNCTION suites.version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'DELETE' THEN
  IF OLD.state = 'saved' THEN RAISE EXCEPTION 'saved suite version is final'; END IF;
  RETURN OLD;
 END IF;
 IF OLD.state = 'saved' THEN RAISE EXCEPTION 'saved suite version is final'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER suite_version_final BEFORE UPDATE OR DELETE ON suites.suite_versions FOR EACH ROW EXECUTE FUNCTION suites.version_guard();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['suites.suites','suites.suite_versions','suites.suite_bindings','suites.suite_criterion_bindings',
  'suites.suite_tasks','suites.data_plans','suites.data_plan_cells','suites.ts_plans','suites.ts_categories','suites.ts_prompts'] LOOP
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP; END $$;

GRANT USAGE ON SCHEMA suites TO anvil_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA suites TO anvil_app;
