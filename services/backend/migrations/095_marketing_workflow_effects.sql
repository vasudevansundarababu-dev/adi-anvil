CREATE TABLE marketing_runtime.workflow_effects(
 id uuid PRIMARY KEY, project_id uuid NOT NULL, episode_id uuid NOT NULL,
 generation integer NOT NULL CHECK(generation>=0), execution_sha256 text NOT NULL CHECK(execution_sha256~'^[a-f0-9]{64}$'),
 node_id text NOT NULL, node_sha256 text NOT NULL, week integer NOT NULL CHECK(week BETWEEN 1 AND 12),
 visit integer NOT NULL CHECK(visit BETWEEN 1 AND 400), input_sha256 text NOT NULL,
 state text NOT NULL CHECK(state IN('claimed','completed','execution_unknown')),
 result jsonb, result_sha256 text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), completed_at timestamptz,
 FOREIGN KEY(project_id,episode_id) REFERENCES marketing_runtime.episodes(project_id,id),
 UNIQUE(project_id,episode_id,generation,execution_sha256,node_id,week,visit),
 CHECK((state='completed')=(result IS NOT NULL AND result_sha256 IS NOT NULL)),
 CHECK(result IS NULL OR octet_length(result::text)<=65536)
);
ALTER TABLE marketing_runtime.workflow_effects ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing_runtime.workflow_effects FORCE ROW LEVEL SECURITY;
CREATE POLICY scheduler ON marketing_runtime.workflow_effects TO anvil_golden_scheduler
 USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
CREATE POLICY grader ON marketing_runtime.workflow_effects FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT,INSERT,UPDATE ON marketing_runtime.workflow_effects TO anvil_golden_scheduler;
GRANT SELECT ON marketing_runtime.workflow_effects TO anvil_golden_grader;
CREATE FUNCTION marketing_runtime.workflow_effect_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR OLD.state<>'claimed' OR NEW.state NOT IN('completed','execution_unknown')
 OR (to_jsonb(NEW)-ARRAY['state','result','result_sha256','completed_at']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['state','result','result_sha256','completed_at']) THEN
  RAISE EXCEPTION 'Marketing workflow effects cannot be replayed or rewritten';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER custody BEFORE UPDATE OR DELETE ON marketing_runtime.workflow_effects FOR EACH ROW EXECUTE FUNCTION marketing_runtime.workflow_effect_transition();
-- Keep role mutation privileges out of the scheduler. PostgreSQL row locks on
-- membership require UPDATE privilege, so expose only this scoped Boolean.
CREATE FUNCTION marketing_runtime.execution_guard(p_actor uuid,p_episode uuid,p_generation integer)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE p uuid=nullif(current_setting('anvil.project',true),'')::uuid;BEGIN
 PERFORM 1 FROM marketing_runtime.episodes e WHERE e.project_id=p AND e.id=p_episode AND e.assigned_user=p_actor AND e.generation=p_generation FOR SHARE OF e;
 IF NOT FOUND THEN
  RETURN false;
 END IF;
 PERFORM 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
 WHERE m.project_id=p AND m.user_id=p_actor AND m.active AND u.active AND m.role IN('admin','rl-engineer') FOR SHARE OF m,u;
 RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.execution_guard(uuid,uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.execution_guard(uuid,uuid,integer) TO anvil_golden_scheduler;
INSERT INTO anvil.schema_versions(version) VALUES(95);
