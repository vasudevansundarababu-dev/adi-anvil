-- Six-template local component runtime. Cloud and model dispatch remain separate gates.
CREATE TABLE anvil.environment_packs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 template_id text NOT NULL,scenario_id text NOT NULL,content jsonb NOT NULL,
 content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),
 validation jsonb NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),UNIQUE(project_id,content_sha256));
CREATE TABLE anvil.environment_versions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,pack_id uuid NOT NULL,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 120),manifest jsonb NOT NULL,
 manifest_sha256 text NOT NULL CHECK(manifest_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,pack_id) REFERENCES anvil.environment_packs(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.environment_instances(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,environment_id uuid NOT NULL,
 state text NOT NULL CHECK(state IN('initializing','active','closed')),
 generation integer NOT NULL DEFAULT 0 CHECK(generation>=0),initial_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,environment_id) REFERENCES anvil.environment_versions(project_id,id),UNIQUE(project_id,id));
-- Each collection is a logical application-owned table, isolated by Project and instance.
CREATE TABLE anvil.environment_records(
 project_id uuid NOT NULL,instance_id uuid NOT NULL,collection text NOT NULL,record_id text NOT NULL,
 content jsonb NOT NULL,PRIMARY KEY(instance_id,collection,record_id),
 FOREIGN KEY(project_id,instance_id) REFERENCES anvil.environment_instances(project_id,id));
CREATE TABLE anvil.environment_files(
 project_id uuid NOT NULL,instance_id uuid NOT NULL,path text NOT NULL,media_type text NOT NULL,
 content bytea NOT NULL,sha256 text NOT NULL,PRIMARY KEY(instance_id,path),
 FOREIGN KEY(project_id,instance_id) REFERENCES anvil.environment_instances(project_id,id));
CREATE TABLE anvil.environment_events(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,instance_id uuid NOT NULL,generation integer NOT NULL,
 sequence integer NOT NULL,operation text NOT NULL,arguments jsonb NOT NULL,result jsonb NOT NULL,
 previous_sha256 text,content_sha256 text NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(instance_id,sequence),
 FOREIGN KEY(project_id,instance_id) REFERENCES anvil.environment_instances(project_id,id));
CREATE TABLE anvil.environment_receipts(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,environment_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN('validation','registration','evidence','reset','cleanup')),
 instance_id uuid,content jsonb NOT NULL,content_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,environment_id) REFERENCES anvil.environment_versions(project_id,id),
 FOREIGN KEY(project_id,instance_id) REFERENCES anvil.environment_instances(project_id,id),UNIQUE(project_id,id));
CREATE FUNCTION anvil.environment_author() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid
 OR NOT anvil.golden_engineer(NEW.project_id) THEN RAISE EXCEPTION 'authenticated project engineer required';END IF;
 RETURN NEW;END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['environment_packs','environment_versions','environment_instances','environment_records','environment_files','environment_events','environment_receipts'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY engineer ON anvil.%I TO anvil_app USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id))',t);
  EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
  IF t IN ('environment_instances','environment_records','environment_files') THEN
   EXECUTE format('GRANT UPDATE ON anvil.%I TO anvil_app',t);
  ELSE
   EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  END IF;
  IF t IN ('environment_records','environment_files') THEN
   EXECUTE format('GRANT DELETE ON anvil.%I TO anvil_app',t);
  ELSE
   EXECUTE format('CREATE TRIGGER actual_author BEFORE INSERT ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.environment_author()',t);
  END IF;
 END LOOP;
END $$;
