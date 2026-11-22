-- RL Gym v2: the runner asks once per tick which workspaces have run work, instead of scanning every workspace.
-- SECURITY DEFINER returns workspace ids only (no rows of any workspace); each workspace's work is then read under
-- its own row-level-security scope as before.
CREATE FUNCTION runs.workspaces_with_work() RETURNS SETOF uuid
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path = runs, pg_temp AS $$
 SELECT workspace_id FROM runs.runs WHERE state IN ('admitted','running')
 UNION
 SELECT workspace_id FROM runs.instances WHERE stopped_at IS NULL $$;
REVOKE ALL ON FUNCTION runs.workspaces_with_work() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION runs.workspaces_with_work() TO anvil_app;
