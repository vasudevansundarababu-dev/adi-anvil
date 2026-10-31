-- Stable profiles and immutable connection versions; no legacy configuration rewrites.
CREATE TABLE anvil.workspace_model_profiles (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 current_connection_id uuid,disabled_at timestamptz,row_version int NOT NULL DEFAULT 1,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id)
);
CREATE TABLE anvil.workspace_model_versions (
 project_id uuid NOT NULL,profile_id uuid NOT NULL,connection_id uuid NOT NULL,
 version_no int NOT NULL CHECK(version_no>0),previous_connection_id uuid,
 PRIMARY KEY(project_id,connection_id),UNIQUE(project_id,profile_id,connection_id),
 UNIQUE(project_id,profile_id,version_no),
 FOREIGN KEY(project_id,profile_id) REFERENCES anvil.workspace_model_profiles(project_id,id),
 FOREIGN KEY(project_id,connection_id) REFERENCES anvil.connections(project_id,id),
 FOREIGN KEY(project_id,profile_id,previous_connection_id)
 REFERENCES anvil.workspace_model_versions(project_id,profile_id,connection_id)
);
ALTER TABLE anvil.workspace_model_profiles ADD FOREIGN KEY(project_id,id,current_connection_id)
 REFERENCES anvil.workspace_model_versions(project_id,profile_id,connection_id);
INSERT INTO anvil.workspace_model_profiles(id,project_id,created_by,created_at)
 SELECT id,project_id,created_by,created_at FROM anvil.connections
 WHERE config->>'workspace_profile_version'='1';
INSERT INTO anvil.workspace_model_versions(project_id,profile_id,connection_id,version_no)
 SELECT project_id,id,id,1 FROM anvil.connections WHERE config->>'workspace_profile_version'='1';
UPDATE anvil.workspace_model_profiles SET current_connection_id=id;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workspace_model_profiles','workspace_model_versions'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
GRANT UPDATE(current_connection_id,disabled_at,row_version) ON anvil.workspace_model_profiles TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.workspace_model_versions
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_workspace_model_header() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_version int; previous uuid; old_version int;
BEGIN
 IF OLD.disabled_at IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN
 RAISE EXCEPTION 'disabled model profile cannot change'; END IF;
 IF NEW.current_connection_id IS DISTINCT FROM OLD.current_connection_id THEN
 SELECT version_no,previous_connection_id INTO target_version,previous
 FROM anvil.workspace_model_versions WHERE project_id=NEW.project_id AND profile_id=NEW.id AND connection_id=NEW.current_connection_id;
 IF OLD.current_connection_id IS NULL THEN
 IF target_version IS DISTINCT FROM 1 OR previous IS NOT NULL OR NEW.row_version<>OLD.row_version THEN
 RAISE EXCEPTION 'initial model version must be version one'; END IF;
 ELSE
 SELECT version_no INTO old_version FROM anvil.workspace_model_versions
 WHERE project_id=OLD.project_id AND connection_id=OLD.current_connection_id;
 IF target_version IS DISTINCT FROM old_version+1 OR previous IS DISTINCT FROM OLD.current_connection_id THEN
 RAISE EXCEPTION 'model versions must advance from the current base'; END IF;
 END IF;
 END IF;
 IF OLD.current_connection_id IS NOT NULL AND NEW.row_version<>OLD.row_version+1 THEN
 RAISE EXCEPTION 'model profile row version must advance'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_workspace_model_header BEFORE UPDATE ON anvil.workspace_model_profiles
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_workspace_model_header();
CREATE FUNCTION anvil.guard_workspace_connection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.config ? 'workspace_profile_version' THEN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'workspace model configuration is immutable'; END IF;
 IF (to_jsonb(NEW)-'status'-'row_version') IS DISTINCT FROM (to_jsonb(OLD)-'status'-'row_version')
 OR (NEW.status IS DISTINCT FROM OLD.status AND NEW.status<>'revoked')
 OR NEW.row_version<OLD.row_version OR NEW.row_version>OLD.row_version+1 THEN
 RAISE EXCEPTION 'workspace model configuration is immutable; create a new version'; END IF;
 ELSIF TG_OP='UPDATE' AND NEW.config ? 'workspace_profile_version' THEN
 RAISE EXCEPTION 'legacy connections cannot be converted in place';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_workspace_connection BEFORE UPDATE OR DELETE ON anvil.connections
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_workspace_connection();
INSERT INTO anvil.schema_versions(version) VALUES(30);
