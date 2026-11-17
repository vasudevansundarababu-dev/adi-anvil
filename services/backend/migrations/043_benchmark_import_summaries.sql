CREATE TABLE anvil.benchmark_import_summaries (
 project_id uuid NOT NULL,receipt_id uuid NOT NULL,
 task_count int NOT NULL CHECK(task_count BETWEEN 1 AND 100),payload_count int NOT NULL CHECK(payload_count BETWEEN 1 AND 5000),
 source_classification text NOT NULL CHECK(source_classification IN ('original_synthetic_fixture','partner_restricted','public_licensed')),
 schema_version text NOT NULL CHECK(schema_version='praxis.anvil.benchmark_bundle.v1'),
 scoring_profile text NOT NULL CHECK(scoring_profile IN ('sme_points_v1','bodhium_pilot_v1')),
 PRIMARY KEY(project_id,receipt_id),FOREIGN KEY(project_id,receipt_id) REFERENCES anvil.benchmark_bundle_receipts(project_id,id)
);
ALTER TABLE anvil.benchmark_import_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_import_summaries FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_import_summaries USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.benchmark_import_summaries TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_import_summaries FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.schema_versions(version) VALUES(43);
