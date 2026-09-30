import pytest
from pydantic import ValidationError

from anvil.provenance import Declaration, publication_blocker


def test_declarations_preserve_class_and_require_synthetic_lineage():
    body = {
        "classification": "adi_synthetic",
        "source_owner": "ADI authors",
        "basis": "Original invented test data",
        "generator_version": "manual-v1",
        "seed": "case-1",
    }
    assert publication_blocker(Declaration.model_validate(body).model_dump()) is None
    for change in [
        {"seed": None},
        {"generator_version": " "},
        {"classification": "bodhium_restricted"},
        {"source_owner": "   "},
    ]:
        with pytest.raises(ValidationError):
            Declaration.model_validate(body | change)


@pytest.mark.parametrize(
    "classification",
    [
        "unclassified",
        "bodhium_restricted",
        "adi_praxis_sme",
        "public_permitted",
        "third_party_licensed",
    ],
)
def test_unreviewed_non_synthetic_sources_block_publication(classification):
    assert publication_blocker({"classification": classification})
