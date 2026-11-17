-- User selections are immutable revisions. Qualification is owned by the release
-- operator, not by an API client, scheduler, candidate or checkbox in the UI.
ALTER TABLE anvil.benchmark_task_groups ADD COLUMN display_id bigint GENERATED ALWAYS AS IDENTITY UNIQUE;
GRANT USAGE ON SEQUENCE anvil.benchmark_task_groups_display_id_seq TO anvil_app;
CREATE TABLE anvil.project_binding_versions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,
 version integer NOT NULL CHECK(version>0),snapshot jsonb NOT NULL,
 snapshot_sha256 text NOT NULL CHECK(snapshot_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),
 UNIQUE(project_id,id),UNIQUE(task_group_id,version));
CREATE TABLE anvil.project_binding_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,binding_id uuid NOT NULL,
 release_sha256 text NOT NULL CHECK(release_sha256~'^[a-f0-9]{64}$'),
 evidence jsonb NOT NULL,evidence_sha256 text NOT NULL CHECK(evidence_sha256~'^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,binding_id) REFERENCES anvil.project_binding_versions(project_id,id),
 UNIQUE(project_id,id));
CREATE TABLE anvil.project_binding_qualification_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,
 reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.project_binding_qualifications(project_id,id),
 UNIQUE(qualification_id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['project_binding_versions','project_binding_qualifications','project_binding_qualification_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.in_scope(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE POLICY engineer_insert ON anvil.project_binding_versions FOR INSERT TO anvil_app
 WITH CHECK(anvil.in_scope(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid
 AND EXISTS(SELECT 1 FROM anvil.memberships WHERE project_id=project_binding_versions.project_id
 AND user_id=created_by AND active AND role IN('admin','rl-engineer')));
GRANT INSERT ON anvil.project_binding_versions TO anvil_app;
-- Deliberately no application/worker INSERT privilege on qualifications/revocations.
-- A deployment-qualified evidence producer must supply real receipts; no seed.
