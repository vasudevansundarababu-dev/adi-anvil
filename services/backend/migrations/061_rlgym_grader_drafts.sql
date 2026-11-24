-- E-004 §3.2-3.3: grader drafts, draft re-scores and promotion with a second approver. Additive only: two new
-- append-only tables, one nullable column on scoring passes and one widened CHECK (pass reason 'draft'). No row of an
-- existing table changes; draft passes are never the "latest" pass of a run (reports, leaderboard, SME review).
CREATE TABLE catalog.grader_drafts(
 id text NOT NULL, workspace_id uuid NOT NULL, project_id text NOT NULL,
 criterion_id text NOT NULL, configuration_id text NOT NULL, base_version int NOT NULL,
 settings jsonb NOT NULL, note text,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id, id));
CREATE TRIGGER grader_drafts_final BEFORE UPDATE OR DELETE ON catalog.grader_drafts
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE catalog.grader_promotions(
 id text NOT NULL, workspace_id uuid NOT NULL, project_id text NOT NULL, draft_id text NOT NULL,
 configuration_id text NOT NULL, criterion_id text NOT NULL,
 proposed_by text NOT NULL, proposed_at timestamptz NOT NULL DEFAULT now(), reason text NOT NULL,
 state text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed','approved','rejected')),
 decided_by text, decided_at timestamptz, decision_reason text, fix_version int,
 CHECK (decided_by IS NULL OR decided_by <> proposed_by),
 PRIMARY KEY (workspace_id, id));
ALTER TABLE scoring.scoring_passes ADD COLUMN draft jsonb;
ALTER TABLE scoring.scoring_passes DROP CONSTRAINT IF EXISTS scoring_passes_reason_check;
ALTER TABLE scoring.scoring_passes ADD CONSTRAINT scoring_passes_reason_check
  CHECK (reason IN ('initial','rescore','draft'));
DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['catalog.grader_drafts','catalog.grader_promotions'] LOOP
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP;
END $$;
GRANT SELECT, INSERT ON catalog.grader_drafts TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON catalog.grader_promotions TO anvil_app;
