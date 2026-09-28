ALTER TABLE anvil.graph_projection_state ADD projection_version text NOT NULL DEFAULT 'resource-only-v1';
INSERT INTO anvil.schema_versions(version) VALUES(12);
