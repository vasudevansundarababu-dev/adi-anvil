-- Private grader can resolve exact frozen policy targets. No actor/API grants.
GRANT SELECT ON anvil.benchmark_policy_sets TO anvil_golden_grader;
CREATE POLICY private_grader_read ON anvil.benchmark_policy_sets FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT ON anvil.harbor_agent_plans TO anvil_golden_grader;
CREATE POLICY result_grader_read ON anvil.harbor_agent_plans FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
INSERT INTO anvil.schema_versions(version) VALUES(92);
