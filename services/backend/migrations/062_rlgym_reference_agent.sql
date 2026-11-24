-- E-007 §7.2, V-04, V-01: reference-agent runs and the confirmation of each task's reference approach. Additive only:
-- two new append-only tables in the verification schema; nothing existing changes.
CREATE TABLE verification.reference_runs(
 id text NOT NULL, workspace_id uuid NOT NULL, suite_version_id uuid NOT NULL,
 report jsonb NOT NULL, report_sha256 char(64) NOT NULL, requested_by text,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (workspace_id, id));
CREATE INDEX reference_runs_suite ON verification.reference_runs(workspace_id, suite_version_id, created_at DESC);
CREATE TABLE verification.reference_confirmations(
 id text NOT NULL, workspace_id uuid NOT NULL, task_import_id uuid NOT NULL,
 package_sha256 text NOT NULL, summary_sha256 char(64) NOT NULL, summary text NOT NULL,
 verdict text NOT NULL CHECK (verdict IN ('confirmed','not_right')), note text,
 CHECK (verdict = 'confirmed' OR length(trim(coalesce(note,''))) > 0),
 decided_by text NOT NULL, decided_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (workspace_id, id));
DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['verification.reference_runs','verification.reference_confirmations'] LOOP
  EXECUTE format('CREATE TRIGGER %s_final BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION infra.forbid_change()', replace(t,'verification.',''), t);
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP;
END $$;
GRANT SELECT, INSERT ON verification.reference_runs, verification.reference_confirmations TO anvil_app;
