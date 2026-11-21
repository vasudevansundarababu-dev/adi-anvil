"""Synthetic source conformance only; variants are not real approval or admission."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from anvil.golden_kyc_v7_candidate import PublishedVariant, decode_candidate
from anvil.praxis_generic_contract import TemplateRef, canonical, digest
from anvil.praxis_generic_export import actor_projection

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures/praxis-generic-v1"
ABSENT = object()


def source_archive(example, coverage=ABSENT):
    spec = json.loads((FIXTURE / "template-spec.json").read_bytes())
    spec["version"] = 8
    spec["authoring"].setdefault("template", {})["caseSelector"] = {
        "field": "product", "source": "S1.applicationType",
        "values": ["individual", "adult_joint", "teen_joint", "custodial"],
    }
    form = spec["authoring"]["profile"]
    form["sections"][0]["fields"].extend([
        {"key": "applicationType", "type": "pick_list", "required": True, "options": ["individual"]},
        {"key": "exampleGoverningState", "type": "pick_list", "required": False,
         "options": ["CA", "NY", "TX", "FL", "IL"]},
    ])
    root = FIXTURE / "single-agent"
    manifest = json.loads((root / "praxis-export.json").read_bytes())
    entry = manifest["tasks"][0]
    entry["case_selector"] = {"field": "product", "value": "individual"}
    entry["template"].update(version=8, sha256=digest(spec))
    if coverage is not ABSENT:
        entry["coverage"] = None if coverage is None else {"example_governing_state": coverage}
    private = json.loads((root / entry["private_assets"][0]["path"]).read_bytes())
    identity = private["authored"]["sections"]["S1"]
    identity["applicationType"] = "individual"
    if example is not ABSENT:
        identity["exampleGoverningState"] = example
    actor = actor_projection(form, private["authored"])
    assets = {entry["form"]["path"]: form, entry["actor"]["path"]: actor,
              entry["private_assets"][0]["path"]: private}
    for reference in (entry["form"], entry["actor"], entry["private_assets"][0]):
        reference["sha256"] = digest(assets[reference["path"]])
    assets["praxis-export.json"] = manifest
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in assets.items():
            archive.writestr(name, canonical(value))
    variant = PublishedVariant(TemplateRef.model_validate(entry["template"]), "a" * 64, canonical(spec))
    return output.getvalue(), variant


@pytest.mark.parametrize("example", [ABSENT, None, ""])
def test_optional_blank_example_decodes_without_changing_approved_source_bytes(example):
    raw, variant = source_archive(example)
    original = raw
    decoded = decode_candidate(raw, (variant,))
    assert decoded.tasks[0].example_governing_state is None
    assert decoded.package_sha256 == hashlib.sha256(original).hexdigest()
    assert raw == original
    assert decoded.run_authority == "not_granted"


def test_explicit_example_requires_and_preserves_exact_coverage():
    raw, variant = source_archive("CA", "CA")
    assert decode_candidate(raw, (variant,)).tasks[0].example_governing_state == "CA"


@pytest.mark.parametrize("example,coverage", [("", "CA"), (None, "CA"), ("CA", ABSENT),
    ("CA", "NY"), ("CA", None), ("", None), (None, None), (" ", ABSENT),
    ("\t", ABSENT), (" CA ", "CA"), ("ca", "CA"), (False, ABSENT),
    (0, ABSENT), ([], ABSENT), ({}, ABSENT)])
def test_missing_or_contradictory_example_metadata_still_rejected(example, coverage):
    raw, variant = source_archive(example, coverage)
    with pytest.raises(ValueError):
        decode_candidate(raw, (variant,))
