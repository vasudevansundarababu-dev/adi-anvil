-- D-056 (owner-approved fix, attach maps additively): Authoring's policy_id_map can arrive on a re-export of a task
-- revision that is already imported (same revision, same package_sha256). The map is kept here, append-only and keyed
-- to that task_imports row, which is never updated. The newest map for an import is the one a NEW suite draft
-- captures; each draft row of suites.suite_tasks records the map it captured, so saved suite versions (and the runs
-- admitted on them) keep exactly the map they were saved with, never a later attachment.
-- Additive only: one new table and one nullable column. projects.task_imports.policy_id_map (migration 064) stays,
-- unused and empty; nothing is dropped.
CREATE TABLE projects.task_policy_maps(
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, task_import_id uuid NOT NULL REFERENCES projects.task_imports(id),
 export_id text NOT NULL, policy_id_map jsonb NOT NULL, map_sha256 char(64) NOT NULL,
 received_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX task_policy_maps_import ON projects.task_policy_maps(task_import_id, received_at DESC);
CREATE TRIGGER task_policy_maps_append_only BEFORE UPDATE OR DELETE ON projects.task_policy_maps
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
ALTER TABLE projects.task_policy_maps ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_isolation ON projects.task_policy_maps USING (workspace_id = infra.current_workspace())
 WITH CHECK (workspace_id = infra.current_workspace());
GRANT SELECT, INSERT ON projects.task_policy_maps TO anvil_app;
ALTER TABLE suites.suite_tasks ADD COLUMN policy_map_id uuid REFERENCES projects.task_policy_maps(id);
