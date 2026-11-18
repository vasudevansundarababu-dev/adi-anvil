-- Extend only the provider constraint; existing RLS, history and grants remain.
ALTER TABLE anvil.workspace_credentials DROP CONSTRAINT workspace_credentials_provider_check;
ALTER TABLE anvil.workspace_credentials ADD CONSTRAINT workspace_credentials_provider_check
 CHECK(provider IN ('openai','anthropic','gemini','langsmith','huggingface'));
INSERT INTO anvil.schema_versions(version) VALUES(128);
