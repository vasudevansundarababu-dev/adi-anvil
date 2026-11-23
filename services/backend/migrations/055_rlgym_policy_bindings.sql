-- RL Gym E-002: the template release's policy_bindings (fact catalog, logical fact -> environment fact, and per clause
-- the tools, evidence tables and checks its obligation needs), embedded by Studio in the RL Gym template document.
-- Additive: NULL for every template without policy bindings (v1-v7), which behave as before.
ALTER TABLE catalog.template_activations ADD COLUMN IF NOT EXISTS policy_bindings jsonb;
