CREATE TABLE anvil.source_provenance(
 project_id uuid NOT NULL, artifact_id uuid PRIMARY KEY,
 declaration jsonb NOT NULL CHECK(declaration ? 'classification' AND declaration->>'classification' IN
 ('bodhium_restricted','adi_praxis_sme','adi_synthetic','public_permitted','third_party_licensed')),
 declared_by uuid NOT NULL REFERENCES anvil.users(id), created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
ALTER TABLE anvil.source_provenance ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.source_provenance FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.source_provenance USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.source_provenance FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
GRANT SELECT,INSERT ON anvil.source_provenance TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(18);
