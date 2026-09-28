CREATE TABLE anvil.readiness_items (
 project_id uuid NOT NULL REFERENCES anvil.projects(id), source_revision_id uuid NOT NULL,
 item_key text NOT NULL, status text NOT NULL CHECK(status IN ('available','partial','missing','not_applicable')),
 explanation text NOT NULL, owner_user_id uuid REFERENCES anvil.users(id), evidence_ids jsonb NOT NULL DEFAULT '[]',
 updated_by uuid NOT NULL REFERENCES anvil.users(id), updated_at timestamptz NOT NULL DEFAULT now(),
 row_version int NOT NULL DEFAULT 1,
 PRIMARY KEY(project_id,source_revision_id,item_key),
 FOREIGN KEY(project_id,source_revision_id) REFERENCES anvil.revisions(project_id,id)
);
ALTER TABLE anvil.readiness_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.readiness_items FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.readiness_items USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT,UPDATE ON anvil.readiness_items TO anvil_app;
GRANT SELECT ON anvil.readiness_items TO anvil_worker;
INSERT INTO anvil.schema_versions(version) VALUES(10);
