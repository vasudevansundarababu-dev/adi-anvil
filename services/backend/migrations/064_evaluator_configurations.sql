-- Append-only project-scoped configuration and local known-case receipts.
CREATE TABLE anvil.evaluator_configurations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 160),
 adapter text NOT NULL CHECK(adapter IN ('builtin','zen','opa-local','nemo','promptfoo','opa','arthur','openlayer')),
 adapter_version text NOT NULL,configuration jsonb NOT NULL CHECK(jsonb_typeof(configuration)='object'),
 configuration_sha256 text NOT NULL CHECK(configuration_sha256~'^[a-f0-9]{64}$'),
 secret_ref text,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id));
CREATE TABLE anvil.evaluator_validation_receipts(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),configuration_id uuid NOT NULL,
 configuration_sha256 text NOT NULL CHECK(configuration_sha256~'^[a-f0-9]{64}$'),
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object'),
 evidence_sha256 text NOT NULL CHECK(evidence_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,configuration_id) REFERENCES anvil.evaluator_configurations(project_id,id));
CREATE TABLE anvil.evaluator_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),configuration_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,configuration_id) REFERENCES anvil.evaluator_configurations(project_id,id),
 UNIQUE(project_id,configuration_id));
CREATE FUNCTION anvil.guard_evaluator_author() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid
 OR NOT anvil.golden_engineer(NEW.project_id) THEN RAISE EXCEPTION 'actual project evaluator author required';END IF;
 IF TG_TABLE_NAME='evaluator_validation_receipts' THEN
 IF NOT EXISTS(
 SELECT 1 FROM anvil.evaluator_configurations c WHERE c.project_id=NEW.project_id AND c.id=NEW.configuration_id
 AND c.configuration_sha256=NEW.configuration_sha256) THEN RAISE EXCEPTION 'exact evaluator configuration required';END IF;
 END IF;
 RETURN NEW;END $$;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['evaluator_configurations','evaluator_validation_receipts','evaluator_revocations'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY scope ON anvil.%I USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 EXECUTE format('CREATE TRIGGER author BEFORE INSERT ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.guard_evaluator_author()',t);
 END LOOP;END $$;
INSERT INTO anvil.schema_versions(version) VALUES('064') ON CONFLICT DO NOTHING;
