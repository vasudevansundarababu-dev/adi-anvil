-- Public export resolution only; never private grading or actor service state.
CREATE TABLE anvil.dataset_export_receipts(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 package_id text NOT NULL,package_version text NOT NULL,
 package_sha256 text NOT NULL CHECK(package_sha256~'^[a-f0-9]{64}$'),
 original_zip bytea NOT NULL CHECK(octet_length(original_zip)<=1048576),
 resolution jsonb NOT NULL,resolution_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,package_id,package_version));
ALTER TABLE anvil.dataset_export_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.dataset_export_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY export_read ON anvil.dataset_export_receipts FOR SELECT TO anvil_app
 USING(anvil.golden_engineer(project_id));
CREATE POLICY export_insert ON anvil.dataset_export_receipts FOR INSERT TO anvil_app
 WITH CHECK(anvil.golden_engineer(project_id));
GRANT SELECT,INSERT ON anvil.dataset_export_receipts TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.dataset_export_receipts
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE TABLE anvil.dataset_export_clients(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 120),token_hash text NOT NULL UNIQUE,
 can_resolve boolean NOT NULL DEFAULT false,created_by uuid NOT NULL REFERENCES anvil.users(id),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id));
CREATE TABLE anvil.dataset_export_client_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,client_id uuid NOT NULL UNIQUE,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,client_id) REFERENCES anvil.dataset_export_clients(project_id,id));
ALTER TABLE anvil.dataset_export_clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.dataset_export_clients FORCE ROW LEVEL SECURITY;
-- Narrow pre-auth lookup is project-only and still requires an unguessable token
-- digest in the API query. It confers no table mutation or public listing endpoint.
CREATE POLICY export_client_lookup ON anvil.dataset_export_clients FOR SELECT TO anvil_app
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE POLICY export_client_insert ON anvil.dataset_export_clients FOR INSERT TO anvil_app
 WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
ALTER TABLE anvil.dataset_export_client_revocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.dataset_export_client_revocations FORCE ROW LEVEL SECURITY;
CREATE POLICY export_client_revocation_lookup ON anvil.dataset_export_client_revocations FOR SELECT TO anvil_app
 USING(project_id=nullif(current_setting('anvil.project',true),'')::uuid);
CREATE POLICY export_client_revocation_insert ON anvil.dataset_export_client_revocations FOR INSERT TO anvil_app
 WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
GRANT SELECT,INSERT ON anvil.dataset_export_clients,anvil.dataset_export_client_revocations TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.dataset_export_clients
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.dataset_export_client_revocations
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
