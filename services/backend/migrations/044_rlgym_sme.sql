-- RL Gym v2 work package 2.9: SME review loop (batches sent to ADI Forge, decisions back, reviewed scores, follow-ups,
-- validation runs). Schema `results`. SMEs work only in ADI Forge; they have no RL Gym account.
CREATE SEQUENCE results.batch_number;
CREATE TABLE results.sme_review_batches(
 id text PRIMARY KEY CHECK (id ~ '^smr-[0-9]{4,}$'), workspace_id uuid NOT NULL, project_id text NOT NULL,
 run_id text NOT NULL REFERENCES runs.runs, template_id text NOT NULL, template_version int NOT NULL,
 state text NOT NULL CHECK (state IN ('building','sent','in_review','decided','corrections_imported','validated')),
 forge_batch_ref text, batch_sha256 char(64) NOT NULL, created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), sent_at timestamptz, decided_at timestamptz);
CREATE TABLE results.sme_review_items(
 id text PRIMARY KEY, batch_id text NOT NULL REFERENCES results.sme_review_batches, workspace_id uuid NOT NULL,
 episode_id text NOT NULL REFERENCES runs.episodes, task_id text NOT NULL, task_revision int NOT NULL,
 suspected_cause text,
 decision text CHECK (decision IN ('agent_failure','task_correction','rubric_correction','grader_wrong','environment_wrong')),
 criterion_id text, rationale text, decided_by text, decided_at timestamptz, evidence_refs jsonb,
 excluded_from_reviewed boolean, follow_up jsonb NOT NULL DEFAULT '{}', inbox_item_id text,
 fix_configuration text, fix_version int,
 CHECK (decision IS NULL OR (rationale IS NOT NULL AND decided_by IS NOT NULL)),
 UNIQUE (batch_id, episode_id));
-- Items are fixed once the batch leaves `building`; only decision and follow-up fields change afterwards.
CREATE FUNCTION results.sme_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE st text;
BEGIN
 SELECT state INTO st FROM results.sme_review_batches WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.batch_id ELSE NEW.batch_id END;
 IF TG_OP IN ('INSERT','DELETE') AND st <> 'building' THEN RAISE EXCEPTION 'a sent SME review batch is immutable'; END IF;
 IF TG_OP = 'UPDATE' AND (NEW.batch_id, NEW.episode_id, NEW.task_id, NEW.task_revision, NEW.suspected_cause)
    IS DISTINCT FROM (OLD.batch_id, OLD.episode_id, OLD.task_id, OLD.task_revision, OLD.suspected_cause) AND st <> 'building'
   THEN RAISE EXCEPTION 'a sent SME review batch is immutable'; END IF;
 IF TG_OP = 'UPDATE' AND OLD.decision IS NOT NULL AND NEW.decision IS DISTINCT FROM OLD.decision
   THEN RAISE EXCEPTION 'an SME decision is final'; END IF;
 RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER sme_item_guard BEFORE INSERT OR UPDATE OR DELETE ON results.sme_review_items
 FOR EACH ROW EXECUTE FUNCTION results.sme_item_guard();

CREATE TABLE results.reviewed_scores(
 run_id text NOT NULL REFERENCES runs.runs, workspace_id uuid NOT NULL, system_id text NOT NULL, system_version int NOT NULL,
 batch_id text NOT NULL REFERENCES results.sme_review_batches, pass_id uuid NOT NULL,
 automated numeric, reviewed numeric, excluded int NOT NULL, computed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (run_id, system_id, system_version, batch_id));

CREATE TABLE results.validation_links(
 item_id text NOT NULL REFERENCES results.sme_review_items, workspace_id uuid NOT NULL,
 validation_run_id text NOT NULL REFERENCES runs.runs, corrected_task_import_id uuid NOT NULL REFERENCES projects.task_imports,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (item_id, validation_run_id));

-- A validation run re-runs one corrected task on the original cases and systems; it is not a suite run.
ALTER TABLE runs.runs ADD COLUMN purpose text NOT NULL DEFAULT 'benchmark' CHECK (purpose IN ('benchmark','validation'));

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['results.sme_review_batches','results.sme_review_items','results.reviewed_scores','results.validation_links'] LOOP
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP; END $$;

GRANT USAGE ON SEQUENCE results.batch_number TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON results.sme_review_batches, results.sme_review_items TO anvil_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON results.reviewed_scores TO anvil_app;
GRANT SELECT, INSERT ON results.validation_links TO anvil_app;
