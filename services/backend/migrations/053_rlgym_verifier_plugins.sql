-- RL Gym v2 work package 2.14, verifier plug-ins (adi.verifier-plugin.v1, D22). framework_versions become plug-in
-- versions: the runtime id is free-form (the plug-in id), and a version stores its manifest, image, settings schema,
-- what it reads and whether it calls a model. Today's python row keeps working unchanged (no manifest = built-in).
ALTER TABLE catalog.framework_versions DROP CONSTRAINT IF EXISTS framework_versions_runtime_id_check;
ALTER TABLE catalog.framework_versions ADD CONSTRAINT framework_versions_runtime_id_format
  CHECK (runtime_id ~ '^[a-z0-9][a-z0-9-]{0,62}$');
ALTER TABLE catalog.framework_versions ADD COLUMN manifest jsonb;
ALTER TABLE catalog.framework_versions ADD COLUMN manifest_sha256 char(64);
ALTER TABLE catalog.framework_versions ADD COLUMN settings_schema jsonb;
ALTER TABLE catalog.framework_versions ADD COLUMN reads text[];
ALTER TABLE catalog.framework_versions ADD COLUMN calls_model boolean NOT NULL DEFAULT false;
ALTER TABLE catalog.framework_versions ADD COLUMN known_case_results jsonb;
-- Rules files and other verifier files a template release carries (A-03 `verifier_files`, by SHA-256; in spec_sha256).
ALTER TABLE catalog.template_activations ADD COLUMN verifier_files jsonb;
