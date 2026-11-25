-- KYC Judgment v1 (C4, E-011): a template's output schema (shown to the agent as "Output fields") and the skill each
-- criterion measures. Additive: two nullable columns; every existing template keeps NULL, so its runs are unchanged.
ALTER TABLE catalog.template_activations ADD COLUMN output_schema jsonb;
ALTER TABLE catalog.template_criteria ADD COLUMN skill text
  CHECK (skill IS NULL OR skill IN ('tool_calling','instruction_following','reasoning','decisioning','safety'));
