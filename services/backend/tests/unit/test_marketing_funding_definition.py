"""New source v3 controls; synthetic world wrapper, actual pinned finances."""

from copy import deepcopy

import pytest
from test_marketing_service_definition import candidate
from test_marketing_world_finance import source

from anvil.marketing_world_definition import definition
from anvil.marketing_world_funding_definition import with_finance
from anvil.praxis_generic_contract import digest


def test_explicit_funding_successor_rederives_private_book_and_preserves_v2():
    _, original = candidate()
    before = deepcopy(original)
    files, _ = source()
    successor = with_finance(original, files)
    parsed = definition(successor)
    assert parsed.schema_version == "anvil.marketing-private-world-definition.v3"
    assert parsed.finance_book["ceiling"] == 20000000
    assert parsed.finance_book_sha256 == digest(parsed.finance_book)
    assert original == before
    assert "finance_book" not in definition(original).model_dump()


def test_self_hash_cannot_promote_changed_book_over_original_parent_records():
    _, original = candidate()
    files, _ = source()
    successor = with_finance(original, files)
    successor["finance_book"]["locked_contingency"] = 0
    successor["finance_book_sha256"] = digest(successor["finance_book"])
    with pytest.raises(ValueError, match="original pinned source bytes"):
        definition(successor)


def test_changed_financial_document_fails_inventory_even_with_unchanged_compiled_book():
    _, original = candidate()
    files, _ = source()
    successor = with_finance(original, files)
    successor["finance_source_documents"]["cases/GT2-R01/commitments.json"] = "[]"
    with pytest.raises(ValueError, match="independently pinned"):
        definition(successor)
