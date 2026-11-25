-- A test-channel template activation (the KYC Judgment v1 end-to-end test before Studio's release): only test-only
-- projects may export against it, never leaderboard-eligible, labelled TEST. Additive: one nullable column.
ALTER TABLE catalog.template_activations ADD COLUMN channel text;
