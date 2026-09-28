CREATE TABLE anvil.sales_contacts (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL, email text NOT NULL, organization_label text NOT NULL,
 contact_basis text NOT NULL, status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','suppressed')),
 created_by uuid NOT NULL REFERENCES anvil.users(id), approved_by uuid REFERENCES anvil.users(id),
 content_hash text NOT NULL, row_version int NOT NULL DEFAULT 1, UNIQUE(project_id,id)
);
CREATE TABLE anvil.fixture_senders (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL, scenario text NOT NULL CHECK(scenario IN ('accepted','failed','unknown')),
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','disabled')),
 created_by uuid NOT NULL REFERENCES anvil.users(id), activated_by uuid REFERENCES anvil.users(id),
 content_hash text NOT NULL, row_version int NOT NULL DEFAULT 1, UNIQUE(project_id,id),
 CHECK(activated_by IS NULL OR activated_by<>created_by)
);
CREATE TABLE anvil.delivery_approvals (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 kit_revision_id uuid NOT NULL, contact_id uuid NOT NULL, sender_id uuid NOT NULL,
 binding_hash text NOT NULL, approved_by uuid NOT NULL REFERENCES anvil.users(id),
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,kit_revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,contact_id) REFERENCES anvil.sales_contacts(project_id,id),
 FOREIGN KEY(project_id,sender_id) REFERENCES anvil.fixture_senders(project_id,id), UNIQUE(project_id,id)
);
CREATE TABLE anvil.sales_deliveries (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 approval_id uuid NOT NULL UNIQUE, requested_by uuid NOT NULL REFERENCES anvil.users(id),
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','fixture_accepted','fixture_failed','fixture_unknown','blocked')),
 binding_hash text NOT NULL, attempts int NOT NULL DEFAULT 0, error_code text,
 created_at timestamptz NOT NULL DEFAULT now(), accepted_at timestamptz,
 FOREIGN KEY(project_id,approval_id) REFERENCES anvil.delivery_approvals(project_id,id), UNIQUE(project_id,id), UNIQUE(project_id,binding_hash)
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.delivery_approvals FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['sales_contacts','fixture_senders','delivery_approvals','sales_deliveries'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON anvil.%I TO anvil_app,anvil_worker',t);
 END LOOP;
END $$;
REVOKE UPDATE ON anvil.delivery_approvals FROM anvil_app,anvil_worker;
REVOKE INSERT,UPDATE ON anvil.sales_contacts,anvil.fixture_senders FROM anvil_worker;
INSERT INTO anvil.schema_versions(version) VALUES(4);
