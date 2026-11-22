-- RL Gym v2 work package 2.12: S4 edge cases and S1 slice lists mirrored from activation (inside spec_sha256), and
-- each imported task's slice tags (complexity, archetype) from the private part of its package.
ALTER TABLE catalog.template_activations ADD COLUMN edge_cases jsonb;
ALTER TABLE catalog.template_activations ADD COLUMN slice_lists jsonb;
ALTER TABLE projects.task_imports ADD COLUMN complexity text;
ALTER TABLE projects.task_imports ADD COLUMN archetype text;
