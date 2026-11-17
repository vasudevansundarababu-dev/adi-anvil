CREATE TABLE anvil.benchmark_window_ownership (
 project_id uuid NOT NULL,window_id uuid NOT NULL,category text NOT NULL CHECK(category IN ('legacy','benchmark')),
 run_id uuid,purpose text CHECK(purpose IN ('candidate','judge')),created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(project_id,window_id),FOREIGN KEY(project_id,window_id) REFERENCES anvil.evaluation_spend_windows(project_id,id),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_comparisons(project_id,run_id),
 CHECK((category='legacy' AND run_id IS NULL AND purpose IS NULL)
 OR (category='benchmark' AND run_id IS NOT NULL AND purpose IS NOT NULL))
);
ALTER TABLE anvil.benchmark_window_ownership ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_window_ownership FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_window_ownership USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT ON anvil.benchmark_window_ownership TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_window_ownership FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.benchmark_window_ownership(project_id,window_id,category)
 SELECT project_id,window_id,'legacy' FROM anvil.run_budgets
 UNION SELECT project_id,window_id,'legacy' FROM anvil.workspace_execution_groups WHERE window_id IS NOT NULL;
INSERT INTO anvil.benchmark_window_ownership(project_id,window_id,category,run_id,purpose)
 SELECT project_id,window_id,'benchmark',run_id,purpose FROM anvil.benchmark_spend_bindings;

CREATE FUNCTION anvil.guard_benchmark_window_ownership() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE own anvil.benchmark_window_ownership%ROWTYPE; parent_run uuid; BEGIN
 IF TG_TABLE_NAME='benchmark_spend_bindings' THEN
 INSERT INTO anvil.benchmark_window_ownership(project_id,window_id,category,run_id,purpose)
 VALUES(NEW.project_id,NEW.window_id,'benchmark',NEW.run_id,NEW.purpose) ON CONFLICT DO NOTHING;
 SELECT * INTO own FROM anvil.benchmark_window_ownership WHERE project_id=NEW.project_id AND window_id=NEW.window_id;
 IF own.category<>'benchmark' OR own.run_id<>NEW.run_id OR own.purpose<>NEW.purpose
 THEN RAISE EXCEPTION 'exclusive benchmark window already owned' USING ERRCODE='23514'; END IF;
 ELSE
 IF NEW.window_id IS NULL THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME='workspace_execution_groups' THEN
 SELECT run_id INTO parent_run FROM anvil.benchmark_comparison_groups WHERE project_id=NEW.project_id AND group_id=NEW.id;
 END IF;
 IF parent_run IS NOT NULL THEN
 SELECT * INTO own FROM anvil.benchmark_window_ownership WHERE project_id=NEW.project_id AND window_id=NEW.window_id;
 IF NOT FOUND OR own.category<>'benchmark' OR own.run_id<>parent_run OR own.purpose<>'candidate'
 THEN RAISE EXCEPTION 'benchmark child requires parent candidate window' USING ERRCODE='23514'; END IF;
 ELSE
 INSERT INTO anvil.benchmark_window_ownership(project_id,window_id,category)
 VALUES(NEW.project_id,NEW.window_id,'legacy') ON CONFLICT DO NOTHING;
 SELECT * INTO own FROM anvil.benchmark_window_ownership WHERE project_id=NEW.project_id AND window_id=NEW.window_id;
 IF own.category<>'legacy' THEN RAISE EXCEPTION 'benchmark window cannot fund legacy work' USING ERRCODE='23514'; END IF;
 END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION anvil.guard_benchmark_window_ownership() FROM PUBLIC;
CREATE TRIGGER benchmark_window_owner BEFORE INSERT ON anvil.benchmark_spend_bindings FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_window_ownership();
CREATE TRIGGER benchmark_window_owner BEFORE INSERT OR UPDATE OF window_id ON anvil.run_budgets FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_window_ownership();
CREATE TRIGGER benchmark_window_owner BEFORE INSERT OR UPDATE OF window_id ON anvil.workspace_execution_groups FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_window_ownership();
INSERT INTO anvil.schema_versions(version) VALUES(42);
