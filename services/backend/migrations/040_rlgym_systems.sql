-- RL Gym v2 work package 2.5: systems under test (models), provider keys, probes and model sets.
-- Keys: the database holds only a secret reference (the existing encrypted local store) and the last four characters.
-- Locally the default provider is the controlled mock; live providers stay off without the owner's approval.
CREATE SCHEMA IF NOT EXISTS systems;

CREATE TABLE systems.provider_keys(
 id text NOT NULL, workspace_id uuid NOT NULL,
 provider text NOT NULL CHECK (provider IN ('huggingface','openai','google','anthropic','mistral','vertex','mock')),
 name text NOT NULL CHECK (length(trim(name)) > 0),
 kind text NOT NULL CHECK (kind IN ('api_key','hf_token','service_account','none')),
 scope text NOT NULL CHECK (scope IN ('workspace_default','customer','assist')),
 is_default boolean NOT NULL DEFAULT false,
 secret_ref text NOT NULL, last4 text NOT NULL CHECK (length(last4) <= 4),
 status text NOT NULL CHECK (status IN ('valid','invalid','untested','revoked')),
 status_note text, last_tested_at timestamptz,
 rotated_at timestamptz NOT NULL DEFAULT now(), rotated_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id, id));
CREATE UNIQUE INDEX provider_keys_one_default ON systems.provider_keys (workspace_id, provider) WHERE is_default AND status <> 'revoked';

CREATE TABLE systems.systems(
 workspace_id uuid NOT NULL, system_id text NOT NULL CHECK (system_id ~ '^[a-z0-9][a-z0-9.-]{1,62}$'),
 name text NOT NULL, kind text NOT NULL CHECK (kind IN ('open_weight','frontier','fine_tuned')),
 enabled boolean NOT NULL DEFAULT true, disabled_reason text,
 setup_state text NOT NULL CHECK (setup_state IN ('pending','ready')),
 synthetic boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (enabled OR disabled_reason IS NOT NULL),
 PRIMARY KEY (workspace_id, system_id));

-- Immutable versions: any setting change is version N+1; runs record the exact version.
CREATE TABLE systems.system_versions(
 workspace_id uuid NOT NULL, system_id text NOT NULL, version int NOT NULL CHECK (version > 0),
 kind text NOT NULL CHECK (kind IN ('open_weight','frontier','fine_tuned')),
 provider text NOT NULL, model_id text NOT NULL, hf_revision text,
 key_id text NOT NULL,
 serving jsonb NOT NULL, params jsonb NOT NULL, limits jsonb NOT NULL,
 config_sha256 char(64) NOT NULL,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), change_note text,
 CHECK (kind <> 'open_weight' OR (hf_revision ~ '^[0-9a-f]{40}$')),
 PRIMARY KEY (workspace_id, system_id, version),
 UNIQUE (workspace_id, system_id, config_sha256),
 FOREIGN KEY (workspace_id, system_id) REFERENCES systems.systems,
 FOREIGN KEY (workspace_id, key_id) REFERENCES systems.provider_keys);
CREATE TRIGGER system_versions_append_only BEFORE UPDATE OR DELETE ON systems.system_versions
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

CREATE TABLE systems.system_probes(
 id bigserial PRIMARY KEY, workspace_id uuid NOT NULL, system_id text NOT NULL, system_version int NOT NULL,
 result text NOT NULL CHECK (result IN ('ok','unreachable','auth_failed','rate_limited','live_disabled')),
 latency_ms int, cost_usd numeric, details jsonb NOT NULL DEFAULT '{}', mode text NOT NULL,
 probed_by text NOT NULL, probed_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (workspace_id, system_id, system_version) REFERENCES systems.system_versions (workspace_id, system_id, version));
CREATE TRIGGER system_probes_append_only BEFORE UPDATE OR DELETE ON systems.system_probes
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

CREATE TABLE systems.model_sets(
 workspace_id uuid NOT NULL, id text NOT NULL, version int NOT NULL CHECK (version > 0), name text NOT NULL,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), change_note text,
 members_sha256 char(64) NOT NULL,
 PRIMARY KEY (workspace_id, id, version));
CREATE TABLE systems.model_set_members(
 workspace_id uuid NOT NULL, model_set_id text NOT NULL, model_set_version int NOT NULL,
 system_id text NOT NULL, system_version int NOT NULL,
 PRIMARY KEY (workspace_id, model_set_id, model_set_version, system_id),
 FOREIGN KEY (workspace_id, model_set_id, model_set_version) REFERENCES systems.model_sets,
 FOREIGN KEY (workspace_id, system_id, system_version) REFERENCES systems.system_versions (workspace_id, system_id, version));
CREATE TRIGGER model_sets_append_only BEFORE UPDATE OR DELETE ON systems.model_sets
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TRIGGER model_set_members_append_only BEFORE UPDATE OR DELETE ON systems.model_set_members
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['systems.provider_keys','systems.systems','systems.system_versions','systems.system_probes',
  'systems.model_sets','systems.model_set_members'] LOOP
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP; END $$;

GRANT USAGE ON SCHEMA systems TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON systems.provider_keys, systems.systems TO anvil_app;
GRANT SELECT, INSERT ON systems.system_versions, systems.system_probes, systems.model_sets, systems.model_set_members TO anvil_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA systems TO anvil_app;
