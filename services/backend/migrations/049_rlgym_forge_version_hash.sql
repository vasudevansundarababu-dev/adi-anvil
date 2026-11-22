-- RL Gym v2: an activation records ADI Forge's own hash of the published template version (known after Studio's
-- release step 9). It is not part of spec_sha256, like forge_template_id and forge_version.
ALTER TABLE catalog.template_activations ADD COLUMN forge_template_version_hash text;
