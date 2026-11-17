-- Opaque plan identity only. Private source/packages and credentials stay denied.
GRANT SELECT(agent_plan_id) ON anvil.harbor_checks TO anvil_worker;
REVOKE UPDATE ON anvil.harbor_agent_calls FROM anvil_worker;
REVOKE UPDATE(status,output_json,usage,request_id,actual_micro_usd,finished_at) ON anvil.harbor_agent_calls FROM anvil_worker;
INSERT INTO anvil.schema_versions(version) VALUES(73);
