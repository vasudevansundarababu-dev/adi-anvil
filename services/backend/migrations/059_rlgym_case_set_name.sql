-- E-005 §3: a data plan's sampling seed becomes a named "case set" (e.g. "KYC set A"). Additive: one nullable column;
-- a plan without a name shows its seed as before, and no plan, cell or selection changes.
ALTER TABLE suites.data_plans ADD COLUMN case_set_name text
  CHECK (case_set_name IS NULL OR length(trim(case_set_name)) BETWEEN 1 AND 80);
