-- RL Gym E-002: the export's selected clause versions per task (approved-task-export.v1 `policy_clauses`, optional).
-- Additive: NULL for every task exported without clauses, which runs exactly as before.
ALTER TABLE projects.task_imports ADD COLUMN IF NOT EXISTS policy_clauses jsonb;
