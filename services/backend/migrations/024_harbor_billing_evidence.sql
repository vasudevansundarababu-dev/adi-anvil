-- Capture billing outcomes after membership/approval revocation without exposing private inputs.
GRANT SELECT(id,project_id,plan_id,status) ON anvil.harbor_agent_calls TO anvil_worker;
GRANT UPDATE(status,output_json,usage,request_id,actual_micro_usd,finished_at) ON anvil.harbor_agent_calls TO anvil_worker;
INSERT INTO anvil.schema_versions(version) VALUES(24);
