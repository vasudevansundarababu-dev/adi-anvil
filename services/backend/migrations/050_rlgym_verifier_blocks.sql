-- RL Gym v2 work package 2.11, verifier blocks (adi.verifier-blocks.v1, D21).
-- The environment version's declared collections (`schema.collections`, as released) that State blocks read.
ALTER TABLE catalog.environment_versions ADD COLUMN schema jsonb;
-- Where a template's open values come from (case_reference | sme) and its failure codes; part of spec_sha256.
ALTER TABLE catalog.template_activations ADD COLUMN expected_values_from text
  CHECK (expected_values_from IS NULL OR expected_values_from IN ('case_reference','sme'));
ALTER TABLE catalog.template_activations ADD COLUMN failure_taxonomy jsonb;
-- Each criterion's blocks (released with the template, final).
ALTER TABLE catalog.template_criteria ADD COLUMN verifier_blocks jsonb;
-- One receipt line per block: {block_id, kind, expected, actual, verdict, on_fail}.
ALTER TABLE scoring.criterion_receipts ADD COLUMN block_lines jsonb;
