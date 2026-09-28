ALTER TABLE anvil.users ADD COLUMN is_synthetic boolean NOT NULL DEFAULT true;
CREATE TABLE anvil.project_assignments(
 project_id uuid NOT NULL REFERENCES anvil.projects(id), user_id uuid NOT NULL REFERENCES anvil.users(id),
 capability text NOT NULL CHECK(capability IN ('rights_reviewer','release_owner')),
 active boolean NOT NULL DEFAULT true, PRIMARY KEY(project_id,user_id,capability));
CREATE TABLE anvil.connections(
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id), provider_key text NOT NULL,
 model_id text, destination text NOT NULL, secret_reference text NOT NULL,
 config jsonb NOT NULL, config_hash char(64) NOT NULL, status text NOT NULL DEFAULT 'draft',
 created_by uuid NOT NULL REFERENCES anvil.users(id), created_at timestamptz NOT NULL DEFAULT now(),
 row_version int NOT NULL DEFAULT 1, UNIQUE(project_id,id));
CREATE TABLE anvil.provider_approvals(
 id uuid PRIMARY KEY, project_id uuid NOT NULL, connection_id uuid NOT NULL,
 approver_id uuid NOT NULL REFERENCES anvil.users(id), purpose text NOT NULL CHECK(purpose IN ('activation','paid_scope')),
 subject_hash char(64) NOT NULL, cap_micro_usd bigint NOT NULL CHECK(cap_micro_usd>=0),
 authority_reference text NOT NULL, expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,connection_id) REFERENCES anvil.connections(project_id,id),
 UNIQUE(connection_id,purpose,subject_hash,approver_id));
CREATE TABLE anvil.evaluation_spend_windows(
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 cap_micro_usd bigint NOT NULL CHECK(cap_micro_usd>=0), reserved_micro_usd bigint NOT NULL DEFAULT 0 CHECK(reserved_micro_usd>=0),
 settled_micro_usd bigint NOT NULL DEFAULT 0 CHECK(settled_micro_usd>=0),
 start_at timestamptz NOT NULL DEFAULT now(),end_at timestamptz NOT NULL,
 status text NOT NULL CHECK(status IN ('active','closed')),authority_reference text NOT NULL,
 row_version int NOT NULL DEFAULT 1, UNIQUE(project_id,id),
 CHECK(reserved_micro_usd+settled_micro_usd<=cap_micro_usd));
CREATE TABLE anvil.run_budgets(
 project_id uuid NOT NULL,run_id uuid PRIMARY KEY,window_id uuid NOT NULL,
 cap_micro_usd bigint NOT NULL CHECK(cap_micro_usd>=0), reserved_micro_usd bigint NOT NULL DEFAULT 0 CHECK(reserved_micro_usd>=0),
 settled_micro_usd bigint NOT NULL DEFAULT 0 CHECK(settled_micro_usd>=0),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.runs(project_id,id),
 FOREIGN KEY(project_id,window_id) REFERENCES anvil.evaluation_spend_windows(project_id,id),
 CHECK(reserved_micro_usd+settled_micro_usd<=cap_micro_usd));
CREATE TABLE anvil.budget_reservations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,window_id uuid NOT NULL,run_id uuid NOT NULL,
 operation_key text NOT NULL UNIQUE,amount_micro_usd bigint NOT NULL CHECK(amount_micro_usd>0),
 actual_micro_usd bigint CHECK(actual_micro_usd>=0),status text NOT NULL CHECK(status IN ('reserved','unknown','settled','released')),
 FOREIGN KEY(project_id,window_id) REFERENCES anvil.evaluation_spend_windows(project_id,id),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.runs(project_id,id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['project_assignments','connections','provider_approvals','evaluation_spend_windows','run_budgets','budget_reservations'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING (anvil.in_scope(project_id)) WITH CHECK (anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 END LOOP;
END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.provider_approvals FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
GRANT SELECT,INSERT,UPDATE ON anvil.project_assignments,anvil.connections,anvil.provider_approvals,anvil.evaluation_spend_windows,anvil.run_budgets,anvil.budget_reservations TO anvil_app,anvil_worker;
REVOKE UPDATE ON anvil.provider_approvals FROM anvil_app,anvil_worker;
REVOKE INSERT,UPDATE,DELETE ON anvil.users,anvil.memberships,anvil.organizations FROM anvil_app,anvil_worker;
INSERT INTO anvil.schema_versions(version) VALUES(2);
