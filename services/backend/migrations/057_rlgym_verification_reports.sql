-- E-007 phase 1 (shadow mode): verification reports for runs. Additive only: one new schema and one append-only
-- table; no existing table, row or score is changed. A report is computed after a run ends (or on request), never
-- blocks anything in this phase, and is never rewritten: a later check is a new row.
CREATE SCHEMA IF NOT EXISTS verification;
CREATE TABLE verification.reports(
 id text NOT NULL, workspace_id uuid NOT NULL,
 run_id text NOT NULL,
 pass_id uuid,
 profile text NOT NULL CHECK (profile IN ('experiment','verified_pilot','model_comparison','training_release')),
 status text NOT NULL CHECK (status IN ('provisional','verified','mismatch','withheld')),
 report jsonb NOT NULL,
 report_sha256 char(64) NOT NULL,
 requested_by text,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id, id));
CREATE INDEX verification_reports_run ON verification.reports(workspace_id, run_id, created_at DESC);
CREATE TRIGGER verification_reports_final BEFORE UPDATE OR DELETE ON verification.reports
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
ALTER TABLE verification.reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_isolation ON verification.reports
 USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace());
GRANT USAGE ON SCHEMA verification TO anvil_app;
GRANT SELECT, INSERT ON verification.reports TO anvil_app;
