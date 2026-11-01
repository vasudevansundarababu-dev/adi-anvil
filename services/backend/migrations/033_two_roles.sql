-- User decision31Oct2026: exactly two active project roles, without changing identities.
CREATE TABLE anvil.membership_role_history (
 project_id uuid NOT NULL REFERENCES anvil.projects(id),user_id uuid NOT NULL REFERENCES anvil.users(id),
 legacy_role text NOT NULL,was_active boolean NOT NULL,captured_at timestamptz NOT NULL DEFAULT now(),
 policy text NOT NULL DEFAULT 'admin-rl-engineer-v1',
 PRIMARY KEY(project_id,user_id,legacy_role)
);
INSERT INTO anvil.membership_role_history(project_id,user_id,legacy_role,was_active)
 SELECT project_id,user_id,role,active FROM anvil.memberships;
ALTER TABLE anvil.membership_role_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.membership_role_history FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.membership_role_history USING(anvil.in_scope(project_id));
GRANT SELECT ON anvil.membership_role_history TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.membership_role_history FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
ALTER TABLE anvil.memberships DROP CONSTRAINT memberships_role_check;
UPDATE anvil.memberships SET active=false WHERE role<>'admin';
INSERT INTO anvil.memberships(project_id,user_id,role,active)
 SELECT h.project_id,h.user_id,'rl-engineer',true FROM anvil.membership_role_history h
 WHERE h.was_active AND NOT EXISTS(SELECT 1 FROM anvil.membership_role_history a
 WHERE a.project_id=h.project_id AND a.user_id=h.user_id AND a.was_active AND a.legacy_role='admin')
 GROUP BY h.project_id,h.user_id ON CONFLICT(project_id,user_id,role) DO UPDATE SET active=true;
ALTER TABLE anvil.memberships ADD CONSTRAINT memberships_active_two_roles CHECK(NOT active OR role IN ('admin','rl-engineer'));
CREATE UNIQUE INDEX one_active_project_role ON anvil.memberships(project_id,user_id) WHERE active;
-- These are Admin permissions, not additional selectable roles or people.
INSERT INTO anvil.project_assignments(project_id,user_id,capability)
 SELECT m.project_id,m.user_id,c.capability FROM anvil.memberships m
 CROSS JOIN (VALUES('rights_reviewer'),('release_owner')) c(capability)
 WHERE m.active AND m.role='admin' ON CONFLICT(project_id,user_id,capability) DO UPDATE SET active=true;
INSERT INTO anvil.audit_events(project_id,action,metadata)
 SELECT DISTINCT project_id,'access.two_roles_migrated','{"policy":"admin-rl-engineer-v1","identities_promoted":false}'::jsonb FROM anvil.membership_role_history;
INSERT INTO anvil.schema_versions(version) VALUES(33);
