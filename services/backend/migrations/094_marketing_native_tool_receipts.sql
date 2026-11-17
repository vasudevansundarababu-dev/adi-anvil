CREATE TABLE marketing_runtime.tool_receipts(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,episode_id uuid NOT NULL,generation integer NOT NULL,
 role text NOT NULL CHECK(role IN('orchestrator','intent','performance','brief','policy')),
 operation text NOT NULL,arguments_sha256 text NOT NULL,catalogue_sha256 text NOT NULL,source_refs_sha256 text NOT NULL,
 result jsonb NOT NULL CHECK(octet_length(result::text)<=65536),result_sha256 text NOT NULL,state_sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,episode_id) REFERENCES marketing_runtime.episodes(project_id,id),UNIQUE(project_id,id));
ALTER TABLE marketing_runtime.tool_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing_runtime.tool_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY scheduler ON marketing_runtime.tool_receipts TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
CREATE POLICY grader ON marketing_runtime.tool_receipts FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT,INSERT ON marketing_runtime.tool_receipts TO anvil_golden_scheduler;
GRANT SELECT ON marketing_runtime.tool_receipts TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON marketing_runtime.tool_receipts FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.schema_versions(version) VALUES(94);
