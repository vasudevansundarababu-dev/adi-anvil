-- G4 (E-011 §3): the no-AI lookup baseline runs of a suite version, append-only, workspace-isolated.
-- Additive: one new table; nothing existing changes.
CREATE TABLE verification.lookup_runs(
 id text NOT NULL, workspace_id uuid NOT NULL, suite_version_id uuid NOT NULL,
 report jsonb NOT NULL, report_sha256 char(64) NOT NULL, requested_by text,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (workspace_id, id));
CREATE INDEX lookup_runs_suite ON verification.lookup_runs(workspace_id, suite_version_id, created_at DESC);
CREATE TRIGGER lookup_runs_final BEFORE UPDATE OR DELETE ON verification.lookup_runs FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
ALTER TABLE verification.lookup_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_isolation ON verification.lookup_runs USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace());
GRANT SELECT, INSERT ON verification.lookup_runs TO anvil_app;
