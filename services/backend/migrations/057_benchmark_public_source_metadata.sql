-- Preserve old immutable receipts asunknown rather than invent/backfill owner.
ALTER TABLE anvil.benchmark_import_summaries ADD source_owner text CHECK(source_owner IS NULL OR length(source_owner) BETWEEN 1 AND 20000);
ALTER TABLE anvil.benchmark_import_summaries ADD bank_title text CHECK(bank_title IS NULL OR length(bank_title) BETWEEN 1 AND 20000);
INSERT INTO anvil.schema_versions(version) VALUES(57);
