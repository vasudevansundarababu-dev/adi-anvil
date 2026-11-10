-- Disjoint software rehearsals: never qualification, approval or model observations.
CREATE TABLE anvil.benchmark_rehearsals(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 160),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','completed','failed')),
 manifest jsonb NOT NULL CHECK(jsonb_typeof(manifest)='object'),
 manifest_sha256 text NOT NULL CHECK(manifest_sha256~'^[a-f0-9]{64}$'),
 result jsonb,executed_at timestamptz,
 CHECK((state='draft' AND result IS NULL AND executed_at IS NULL) OR
 (state IN ('completed','failed') AND result IS NOT NULL AND executed_at IS NOT NULL)),
 UNIQUE(project_id,id));
ALTER TABLE anvil.benchmark_rehearsals ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_rehearsals FORCE ROW LEVEL SECURITY;
CREATE POLICY read_rehearsal ON anvil.benchmark_rehearsals FOR SELECT USING(anvil.golden_engineer(project_id));
CREATE POLICY insert_rehearsal ON anvil.benchmark_rehearsals FOR INSERT WITH CHECK(
 anvil.golden_engineer(project_id) AND state='draft' AND result IS NULL AND executed_at IS NULL
 AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY update_rehearsal ON anvil.benchmark_rehearsals FOR UPDATE
 USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id));
GRANT SELECT,INSERT ON anvil.benchmark_rehearsals TO anvil_app;
GRANT UPDATE(state,result,executed_at) ON anvil.benchmark_rehearsals TO anvil_app;
CREATE FUNCTION anvil.guard_rehearsal() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR OLD.state<>'draft' THEN RAISE EXCEPTION 'immutable rehearsal'; END IF;
 IF NEW.state NOT IN ('completed','failed') THEN RAISE EXCEPTION 'terminal transition required';END IF;
 RETURN NEW; END $$;
CREATE TRIGGER terminal_immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_rehearsals
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_rehearsal();
CREATE INDEX rehearsal_project_created ON anvil.benchmark_rehearsals(project_id,created_at,id);
INSERT INTO anvil.schema_versions(version) VALUES('061') ON CONFLICT DO NOTHING;
