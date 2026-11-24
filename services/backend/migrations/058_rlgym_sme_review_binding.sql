-- E-007 (Authoring 7c12b835): an SME Benchmark review decision names what it reviewed: its verdict (accept, or dispute
-- of the task, rubric, grader or environment), the score pass and the sealed evidence digest. Additive only: three
-- nullable columns, written with the decision (decisions stay final under the existing guard); existing rows unchanged.
ALTER TABLE results.sme_review_items ADD COLUMN review_verdict text
  CHECK (review_verdict IS NULL OR review_verdict IN ('accept','dispute_task','dispute_rubric','dispute_grader','dispute_environment'));
ALTER TABLE results.sme_review_items ADD COLUMN score_pass int CHECK (score_pass IS NULL OR score_pass >= 1);
ALTER TABLE results.sme_review_items ADD COLUMN evidence_sha256 char(64)
  CHECK (evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$');
