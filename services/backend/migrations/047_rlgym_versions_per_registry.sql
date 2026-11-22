-- RL Gym v2: version numbers are unique per registry. The local Studio issues its own ids (`golden-kyc-openenv@3`) and
-- seed family for the same contract the Studio stub released as `golden-kyc-openenv@v3`; both stay mirrored side by
-- side (stub releases remain historical and keep serving projects bound to them).
ALTER TABLE catalog.environment_versions DROP CONSTRAINT environment_versions_contract_id_version_key;
ALTER TABLE catalog.environment_versions ADD CONSTRAINT environment_versions_registry_contract_version UNIQUE (registry, contract_id, version);
