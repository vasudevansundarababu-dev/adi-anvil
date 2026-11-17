-- Generic template/qualification and protected source resolution. No Run queue.
CREATE TABLE anvil.praxis_template_versions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 template_key text NOT NULL,version bigint NOT NULL CHECK(version>0),spec jsonb NOT NULL,
 spec_sha256 text NOT NULL,part_hashes jsonb NOT NULL,catalogue_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,template_key,version,spec_sha256),UNIQUE(project_id,spec_sha256));
CREATE TABLE anvil.praxis_template_publications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,template_id uuid NOT NULL,
 publication jsonb NOT NULL,publication_sha256 text NOT NULL,
 origin text NOT NULL CHECK(origin IN('praxis_authenticated_api','offline_fixture')),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,template_id) REFERENCES anvil.praxis_template_versions(project_id,id));
CREATE TABLE anvil.praxis_template_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,template_id uuid NOT NULL,
 receipt jsonb NOT NULL,receipt_sha256 text NOT NULL,status text NOT NULL CHECK(status IN('qualified','blocked')),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,template_id) REFERENCES anvil.praxis_template_versions(project_id,id));
CREATE TABLE anvil.praxis_template_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,
 event_sequence bigint NOT NULL,reason text NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,event_sequence),UNIQUE(project_id,qualification_id),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.praxis_template_qualifications(project_id,id));
CREATE TABLE anvil.praxis_export_resolutions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 package_key text NOT NULL,version text NOT NULL,package_sha256 text NOT NULL,
 batch_key text NOT NULL,part_index integer NOT NULL,part_count integer NOT NULL,
 private_archive_id uuid NOT NULL,receipt jsonb NOT NULL,receipt_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,package_key,version),UNIQUE(project_id,batch_key,part_index),
 FOREIGN KEY(project_id,private_archive_id) REFERENCES anvil.artifacts(project_id,id));
CREATE TABLE anvil.praxis_resolved_tasks(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,resolution_id uuid NOT NULL,template_id uuid NOT NULL,
 task_key text NOT NULL,revision text NOT NULL,actor jsonb NOT NULL,actor_sha256 text NOT NULL,
 private_reference_sha256 text NOT NULL,binding jsonb NOT NULL,binding_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,resolution_id,task_key),
 FOREIGN KEY(project_id,resolution_id) REFERENCES anvil.praxis_export_resolutions(project_id,id),
 FOREIGN KEY(project_id,template_id) REFERENCES anvil.praxis_template_versions(project_id,id));
-- Events and attempts are append-only. Failed delivery never changes revocation.
CREATE TABLE anvil.praxis_template_events(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 event_key text NOT NULL,kind text NOT NULL CHECK(kind IN('qualification','revocation')),
 body jsonb NOT NULL,body_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,event_key));
CREATE TABLE anvil.praxis_template_delivery_attempts(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,event_id uuid NOT NULL,
 status text NOT NULL CHECK(status IN('acknowledged','failed','ambiguous','offline_fixture')),
 result jsonb NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,event_id) REFERENCES anvil.praxis_template_events(project_id,id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['praxis_template_versions','praxis_template_publications','praxis_template_qualifications','praxis_template_revocations','praxis_export_resolutions','praxis_resolved_tasks','praxis_template_events','praxis_template_delivery_attempts'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY scoped_insert ON anvil.%I FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND anvil.benchmark_is_admin(project_id,nullif(current_setting(''anvil.user'',true),'''')::uuid) AND created_by=nullif(current_setting(''anvil.user'',true),'''')::uuid)',t);
  EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
