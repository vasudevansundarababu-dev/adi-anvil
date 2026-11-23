-- RL Gym E-002 (policy clauses, provisional until Studio's clause-receipt.v1 is approved): a criterion consumed only
-- by clauses that were Skipped, Unresolved or a Setup gap is recorded with that outcome and kept out of the score.
-- Additive: every existing verdict stays valid; runs without clauses never write the new values.
ALTER TABLE scoring.criterion_receipts DROP CONSTRAINT IF EXISTS criterion_receipts_verdict_check;
ALTER TABLE scoring.criterion_receipts ADD CONSTRAINT criterion_receipts_verdict_check
  CHECK (verdict IN ('pass','partial','fail','blocked','incomplete','error','not_applicable','unresolved','setup_gap'));
