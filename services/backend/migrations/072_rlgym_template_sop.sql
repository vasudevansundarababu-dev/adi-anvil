-- KYC Judgment v1: the template's Bank SOP (Studio bridge template.sop: sop_id, version, steps with ids such as "8a",
-- titles, when each is required and its tools). Rendered for the agent, who writes sop_step in the audit trail;
-- covered by spec_sha256. Additive: one nullable column.
ALTER TABLE catalog.template_activations ADD COLUMN sop jsonb;
