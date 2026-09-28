ALTER TABLE anvil.source_import_receipts ADD revision_id uuid;
UPDATE anvil.source_import_receipts receipt SET revision_id=resource.current_revision_id
 FROM anvil.resources resource WHERE resource.id=receipt.resource_id AND resource.project_id=receipt.project_id;
ALTER TABLE anvil.source_import_receipts ALTER revision_id SET NOT NULL;
ALTER TABLE anvil.source_import_receipts ADD FOREIGN KEY(project_id,revision_id) REFERENCES anvil.revisions(project_id,id);
ALTER TABLE anvil.import_batches ADD committed_revision_ids jsonb NOT NULL DEFAULT '[]';
UPDATE anvil.import_batches batch SET committed_revision_ids=COALESCE((
 SELECT jsonb_agg(receipt.revision_id ORDER BY item.ordinality)
 FROM jsonb_array_elements(batch.manifest->'cases') WITH ORDINALITY item(value,ordinality)
 JOIN anvil.source_import_receipts receipt ON receipt.project_id=batch.project_id
 AND receipt.partner_key=batch.manifest->>'partner_key'
 AND receipt.external_case_id=item.value->>'external_case_id'
 AND receipt.source_version=item.value->>'source_version'
), '[]'::jsonb)
WHERE batch.manifest->>'schema_version'='anvil.case_import.v1' AND batch.status='committed';
INSERT INTO anvil.schema_versions(version) VALUES(8);
