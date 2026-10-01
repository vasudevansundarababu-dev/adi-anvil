-- D-SIMPLE wizard: one evaluation plan drives existing objective/rubric/task/suite/protocol
-- records. The plan never replaces their version binding; it records the chosen inputs and the
-- single Product Owner decision.
CREATE TABLE anvil.evaluation_plans(
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 title text NOT NULL CHECK(length(title) BETWEEN 3 AND 200),
 state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','submitted','approved','changes_requested')),
 objective_id uuid NOT NULL REFERENCES anvil.resources(id),
 background jsonb NOT NULL DEFAULT '{}'::jsonb,
 benchmark jsonb NOT NULL DEFAULT '{}'::jsonb,
 case_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
 rubric jsonb,
 grader_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
 candidates jsonb NOT NULL DEFAULT '["fixture-correct","fixture-constraint-blind"]'::jsonb,
 task_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
 suite_id uuid REFERENCES anvil.resources(id), protocol_id uuid REFERENCES anvil.resources(id),
 run_id uuid REFERENCES anvil.runs(id),
 created_by uuid NOT NULL REFERENCES anvil.users(id),
 decided_by uuid REFERENCES anvil.users(id), decided_at timestamptz, self_approved boolean,
 decision_rationale text,
 row_version int NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX evaluation_plans_project ON anvil.evaluation_plans(project_id, created_at DESC);
ALTER TABLE anvil.evaluation_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.evaluation_plans FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.evaluation_plans USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT,UPDATE ON anvil.evaluation_plans TO anvil_app;
GRANT SELECT ON anvil.evaluation_plans TO anvil_worker;
INSERT INTO anvil.schema_versions(version) VALUES(19);
