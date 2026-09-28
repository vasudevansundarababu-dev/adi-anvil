ALTER TABLE anvil.artifacts ADD COLUMN original_filename text;
ALTER TABLE anvil.artifacts ADD COLUMN upload_purpose text;
ALTER TABLE anvil.artifacts ADD COLUMN uploaded_by uuid REFERENCES anvil.users(id);

CREATE TABLE anvil.task_datasets (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 objective_id uuid NOT NULL, created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id),
 FOREIGN KEY(project_id,objective_id) REFERENCES anvil.resources(project_id,id)
);
CREATE TABLE anvil.task_imports (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, dataset_id uuid NOT NULL,
 objective_revision_id uuid NOT NULL, source_artifact_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id), created_at timestamptz NOT NULL DEFAULT now(),
 mapping jsonb NOT NULL, validation jsonb NOT NULL, normalized jsonb NOT NULL,
 normalized_sha256 char(64) NOT NULL, revision integer NOT NULL DEFAULT 1,
 status text NOT NULL CHECK(status IN ('invalid','ready','published')),
 published_version_id uuid, UNIQUE(project_id,id),
 FOREIGN KEY(project_id,dataset_id) REFERENCES anvil.task_datasets(project_id,id),
 FOREIGN KEY(project_id,objective_revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,source_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE TABLE anvil.dataset_versions (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, dataset_id uuid NOT NULL,
 version_number integer NOT NULL CHECK(version_number>0), import_id uuid NOT NULL UNIQUE,
 objective_id uuid NOT NULL, objective_revision_id uuid NOT NULL,
 schema_version text NOT NULL CHECK(schema_version='1.0'),
 status text NOT NULL CHECK(status='published'), source jsonb NOT NULL,
 mapping jsonb NOT NULL, validation jsonb NOT NULL, normalized_sha256 char(64) NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL, published_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(dataset_id,version_number), UNIQUE(project_id,id),
 FOREIGN KEY(project_id,dataset_id) REFERENCES anvil.task_datasets(project_id,id),
 FOREIGN KEY(project_id,import_id) REFERENCES anvil.task_imports(project_id,id),
 FOREIGN KEY(project_id,objective_id) REFERENCES anvil.resources(project_id,id),
 FOREIGN KEY(project_id,objective_revision_id) REFERENCES anvil.revisions(project_id,id)
);
ALTER TABLE anvil.task_imports ADD FOREIGN KEY(project_id,published_version_id)
 REFERENCES anvil.dataset_versions(project_id,id);
CREATE TABLE anvil.dataset_tasks (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, version_id uuid NOT NULL,
 row_number integer NOT NULL, external_id text NOT NULL, actor_spec jsonb NOT NULL,
 UNIQUE(version_id,external_id), UNIQUE(project_id,id),
 FOREIGN KEY(project_id,version_id) REFERENCES anvil.dataset_versions(project_id,id)
);
CREATE TABLE anvil.dataset_references (
 task_id uuid PRIMARY KEY, project_id uuid NOT NULL, reference jsonb NOT NULL,
 FOREIGN KEY(project_id,task_id) REFERENCES anvil.dataset_tasks(project_id,id)
);
CREATE TABLE anvil.suite_datasets (
 project_id uuid NOT NULL, suite_revision_id uuid NOT NULL, version_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id), created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(suite_revision_id,version_id),
 FOREIGN KEY(project_id,suite_revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,version_id) REFERENCES anvil.dataset_versions(project_id,id)
);
ALTER TABLE anvil.runs ADD COLUMN dataset_version_id uuid;
ALTER TABLE anvil.runs ADD COLUMN dataset_snapshot jsonb;
ALTER TABLE anvil.runs ADD FOREIGN KEY(project_id,dataset_version_id)
 REFERENCES anvil.dataset_versions(project_id,id);
ALTER TABLE anvil.runs ADD CHECK((dataset_version_id IS NULL) = (dataset_snapshot IS NULL));
CREATE FUNCTION anvil.immutable_dataset_run() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.dataset_version_id,NEW.dataset_snapshot) IS DISTINCT FROM
 ROW(OLD.dataset_version_id,OLD.dataset_snapshot) THEN RAISE EXCEPTION 'immutable dataset run binding'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER immutable_dataset_run BEFORE UPDATE ON anvil.runs
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable_dataset_run();
CREATE FUNCTION anvil.guard_task_import() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF OLD.status='published' OR ROW(NEW.id,NEW.project_id,NEW.dataset_id,NEW.objective_revision_id,
 NEW.source_artifact_id,NEW.created_by,NEW.created_at) IS DISTINCT FROM
 ROW(OLD.id,OLD.project_id,OLD.dataset_id,OLD.objective_revision_id,
 OLD.source_artifact_id,OLD.created_by,OLD.created_at) THEN RAISE EXCEPTION 'immutable import source'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER guard_task_import BEFORE UPDATE ON anvil.task_imports
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_task_import();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['task_datasets','task_imports','dataset_versions','dataset_tasks','dataset_references','suite_datasets'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 IF t <> 'task_imports' THEN
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END IF;
 END LOOP;
END $$;
GRANT UPDATE ON anvil.task_imports TO anvil_app;
GRANT SELECT ON anvil.dataset_tasks,anvil.dataset_versions,anvil.suite_datasets TO anvil_worker;
-- Worker has no access to original imports or reference answers.
INSERT INTO anvil.schema_versions(version) VALUES(13);
