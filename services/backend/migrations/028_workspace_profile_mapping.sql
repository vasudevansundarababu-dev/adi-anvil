-- Historical mapping evidence only: never an authorization grant or membership rewrite.
CREATE TABLE anvil.workspace_profile_mappings (
 project_id uuid NOT NULL REFERENCES anvil.projects(id),
 user_id uuid NOT NULL REFERENCES anvil.users(id),
 profile text NOT NULL CHECK(profile IN ('admin','rl_engineer')),
 legacy_roles jsonb NOT NULL CHECK(jsonb_typeof(legacy_roles)='array'),
 mapping_policy text NOT NULL DEFAULT 'existing-grants-v1',
 recorded_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(project_id,user_id)
);
INSERT INTO anvil.workspace_profile_mappings(project_id,user_id,profile,legacy_roles)
 SELECT m.project_id,m.user_id,
 CASE WHEN bool_or(m.role='admin') THEN 'admin' ELSE 'rl_engineer' END,
 jsonb_agg(m.role ORDER BY m.role)
 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
 WHERE m.active AND u.active GROUP BY m.project_id,m.user_id
 HAVING bool_or(m.role IN ('admin','researcher','data-engineer'));
INSERT INTO anvil.audit_events(project_id,actor_id,action,target_id,metadata)
 SELECT project_id,NULL,'workspace.profile_mapping_recorded',user_id,
 jsonb_build_object('profile',profile,'legacy_roles',legacy_roles,
 'mapping_policy',mapping_policy,'authorization_changed',false)
 FROM anvil.workspace_profile_mappings;
ALTER TABLE anvil.workspace_profile_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.workspace_profile_mappings FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.workspace_profile_mappings
 USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT ON anvil.workspace_profile_mappings TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.workspace_profile_mappings
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.schema_versions(version) VALUES(28);
