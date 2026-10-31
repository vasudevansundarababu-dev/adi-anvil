-- Independent immutable source/package records. Existing diagnostic scores stay unchanged.
CREATE TABLE anvil.praxis_sources (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 task_id text NOT NULL, task_version text NOT NULL, revision_id text NOT NULL,
 source_sha256 char(64) NOT NULL, source_artifact_id uuid NOT NULL,
 actor_spec jsonb NOT NULL, created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id),
 UNIQUE(project_id,task_id,revision_id),
 FOREIGN KEY(project_id,source_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE TABLE anvil.harbor_packages (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, source_id uuid NOT NULL,
 package_sha256 char(64) NOT NULL, package_artifact_id uuid NOT NULL, manifest jsonb NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id), created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id), UNIQUE(project_id,source_id,package_sha256),
 FOREIGN KEY(project_id,source_id) REFERENCES anvil.praxis_sources(project_id,id),
 FOREIGN KEY(project_id,package_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE TABLE anvil.harbor_approvals (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, package_id uuid NOT NULL,
 approved_by uuid NOT NULL REFERENCES anvil.users(id), rationale text NOT NULL,
 self_approved boolean NOT NULL, scope text NOT NULL CHECK(scope='synthetic_software_checks_only'),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,package_id),
 FOREIGN KEY(project_id,package_id) REFERENCES anvil.harbor_packages(project_id,id)
);
CREATE TABLE anvil.harbor_checks (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, package_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),
 candidate text NOT NULL CHECK(candidate IN ('reference','empty_output')),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','succeeded','failed','cancelled','execution_unknown')),
 cancel_requested boolean NOT NULL DEFAULT false, invocation_count int NOT NULL DEFAULT 0 CHECK(invocation_count BETWEEN 0 AND 1),
 result jsonb, error_code text, started_at timestamptz, finished_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id),
 FOREIGN KEY(project_id,package_id) REFERENCES anvil.harbor_packages(project_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['praxis_sources','harbor_packages','harbor_approvals','harbor_checks'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 IF t <> 'harbor_checks' THEN
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END IF;
 END LOOP;
END $$;
GRANT UPDATE ON anvil.harbor_checks TO anvil_app;
-- General candidate worker cannot read source payloads, packages or reference solutions.
REVOKE ALL ON anvil.praxis_sources,anvil.harbor_packages,anvil.harbor_approvals,anvil.harbor_checks FROM anvil_worker;
GRANT SELECT(id,created_by,project_id) ON anvil.harbor_checks TO anvil_worker;
CREATE FUNCTION anvil.claim_harbor_job() RETURNS SETOF anvil.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 BEGIN
 RETURN QUERY UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),
 lease_until=now()+interval '60 seconds',attempts=attempts+1
 WHERE id=(SELECT id FROM anvil.jobs WHERE kind='harbor_check' AND
 (status='queued' OR (status='leased' AND lease_until<now())) AND attempts<3
 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *;
 END $$;
REVOKE ALL ON FUNCTION anvil.claim_harbor_job() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_harbor_job() TO anvil_worker;
-- Existing worker must never claim Docker-host jobs.
CREATE OR REPLACE FUNCTION anvil.claim_job() RETURNS SETOF anvil.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 BEGIN
 RETURN QUERY UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),
 lease_until=now()+interval '60 seconds',attempts=attempts+1
 WHERE id=(SELECT id FROM anvil.jobs WHERE kind <> 'harbor_check' AND (status='queued' OR (status='leased' AND lease_until<now()))
 AND attempts<3 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *;
 END $$;
INSERT INTO anvil.schema_versions(version) VALUES(20);
