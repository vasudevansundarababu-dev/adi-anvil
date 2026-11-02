-- Installation settings are a separate scope of Admin, never inferred from project grants.
CREATE TABLE anvil.import_generation_settings (
 id uuid PRIMARY KEY, config jsonb NOT NULL, secret_reference uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 revoked_at timestamptz
);
GRANT SELECT,INSERT ON anvil.import_generation_settings TO anvil_app;
GRANT UPDATE(revoked_at) ON anvil.import_generation_settings TO anvil_app;
CREATE TABLE anvil.executable_imports (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 source_id uuid NOT NULL, settings_id uuid NOT NULL REFERENCES anvil.import_generation_settings(id),
 cap_micro_usd bigint NOT NULL CHECK(cap_micro_usd>0),
 charged_micro_usd bigint NOT NULL DEFAULT 0 CHECK(charged_micro_usd>=0),
 reserved_micro_usd bigint NOT NULL DEFAULT 0 CHECK(reserved_micro_usd>=0),
 current_revision_id uuid,ready_revision_id uuid,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,source_id),
 FOREIGN KEY(project_id,source_id) REFERENCES anvil.praxis_sources(project_id,id),
 CHECK(charged_micro_usd+reserved_micro_usd<=cap_micro_usd)
);
CREATE TABLE anvil.executable_import_revisions (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,import_id uuid NOT NULL,base_revision_id uuid,
 state text NOT NULL CHECK(state IN ('queued','generating','validating','ready','needs_clarification','generation_failed','environment_unavailable','validation_failed','budget_paused','outcome_unknown','cancelled')),
 kind text NOT NULL CHECK(kind IN ('generate','edit','validate')),
 bundle_artifact_id uuid,package_id uuid,report jsonb NOT NULL DEFAULT '{}'::jsonb,
 cancel_requested boolean NOT NULL DEFAULT false,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
 UNIQUE(project_id,id),UNIQUE(project_id,import_id,id),
 FOREIGN KEY(project_id,import_id) REFERENCES anvil.executable_imports(project_id,id),
 FOREIGN KEY(project_id,base_revision_id) REFERENCES anvil.executable_import_revisions(project_id,id),
 FOREIGN KEY(project_id,bundle_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,package_id) REFERENCES anvil.harbor_packages(project_id,id)
);
ALTER TABLE anvil.executable_imports ADD FOREIGN KEY(project_id,id,current_revision_id) REFERENCES anvil.executable_import_revisions(project_id,import_id,id);
ALTER TABLE anvil.executable_imports ADD FOREIGN KEY(project_id,id,ready_revision_id) REFERENCES anvil.executable_import_revisions(project_id,import_id,id);
CREATE TABLE anvil.import_generation_calls (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,import_id uuid NOT NULL,revision_id uuid NOT NULL,
 reservation_micro_usd bigint NOT NULL CHECK(reservation_micro_usd>0),
 charged_micro_usd bigint CHECK(charged_micro_usd>=0),
 state text NOT NULL CHECK(state IN ('intent','completed','unknown','rejected')),
 request_sha256 char(64) NOT NULL,usage jsonb,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,revision_id),
 FOREIGN KEY(project_id,import_id) REFERENCES anvil.executable_imports(project_id,id),
 FOREIGN KEY(project_id,revision_id) REFERENCES anvil.executable_import_revisions(project_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['executable_imports','executable_import_revisions','import_generation_calls'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION anvil.claim_import_job() RETURNS SETOF anvil.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 BEGIN RETURN QUERY UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds',attempts=attempts+1
 WHERE id=(SELECT id FROM anvil.jobs WHERE kind='executable_import' AND (status='queued' OR (status='leased' AND lease_until<now())) AND attempts<3 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *; END $$;
REVOKE ALL ON FUNCTION anvil.claim_import_job() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_import_job() TO anvil_worker;
GRANT SELECT(id,project_id,created_by) ON anvil.executable_import_revisions TO anvil_worker;
-- Worker terminal capture must survive actor revocation without enabling another dispatch.
GRANT SELECT,UPDATE ON anvil.executable_imports,anvil.executable_import_revisions,anvil.import_generation_calls TO anvil_worker;
CREATE TABLE anvil.import_tool_observations (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,plan_id uuid NOT NULL,stage_index integer NOT NULL,
 event jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,plan_id,stage_index),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id)
);
ALTER TABLE anvil.import_tool_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.import_tool_observations FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.import_tool_observations USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.import_tool_observations TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.import_tool_observations FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE OR REPLACE FUNCTION anvil.claim_job() RETURNS SETOF anvil.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 BEGIN RETURN QUERY UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds',attempts=attempts+1
 WHERE id=(SELECT id FROM anvil.jobs WHERE kind NOT IN ('harbor_check','executable_import') AND (status='queued' OR (status='leased' AND lease_until<now())) AND attempts<3 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *; END $$;
INSERT INTO anvil.schema_versions(version) VALUES(36);
