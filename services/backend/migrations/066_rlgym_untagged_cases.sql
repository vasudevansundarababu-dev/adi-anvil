-- D-059 (T1): a suite data plan option letting each task also take the untagged cases of its application type.
-- Additive: one column, false for every existing plan, so every saved suite samples and hashes as before.
ALTER TABLE suites.data_plans ADD COLUMN untagged_cases boolean NOT NULL DEFAULT false;
