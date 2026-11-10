import base64
import copy

import pytest

from anvil.environment_seeds import CATALOG, generate, validate


@pytest.mark.parametrize("template", list(CATALOG))
def test_all_thirty_materialized_packs_are_reproducible(template):
    checksums = set()
    for scenario in CATALOG[template]["scenarios"]:
        pack = generate(template, scenario, 42)
        assert pack == generate(template, scenario, 42)
        result = validate(pack)
        assert result["runtime_loaded"] is False
        assert pack["provider_calls"] == 0 and pack["origin"] == "synthetic_reference"
        assert all(base64.b64decode(f["bytes_base64"]) for f in pack["files"])
        checksums.add(result["sha256"])
    assert len(checksums) == 5


@pytest.mark.parametrize("path", ["../x", "/x", "a/.env", "a//b", "a\\b"])
def test_imported_pack_cannot_escape_file_namespace(path):
    pack = generate("BNK-KYC", "complete")
    pack["files"][0]["path"] = path
    with pytest.raises(ValueError):
        validate(pack)


def test_pack_hashes_collections_and_ids_cannot_be_forged():
    pack = generate("BOD-FIN", "comparable")
    mutations = [
        lambda p: p["files"][0].update(sha256="0" * 64),
        lambda p: p["records"].pop("companies"),
        lambda p: p["records"]["companies"].append(p["records"]["companies"][0]),
        lambda p: p.update(provider_calls=1),
    ]
    for mutate in mutations:
        altered = copy.deepcopy(pack)
        mutate(altered)
        with pytest.raises(ValueError):
            validate(altered)


def test_csv_replacement_preserves_base_pack_and_exact_source_bytes():
    from anvil.environment_data import import_csv

    original = generate("BOD-FIN", "comparable", 7)
    text = "key,label\nfictional-7-1,Replacement A\nfictional-7-2,Replacement B\nfictional-7-3,Replacement C\n"
    before = copy.deepcopy(original)
    updated = import_csv(
        "BOD-FIN",
        "comparable",
        7,
        "companies",
        text,
        {"id": "key", "name": "label"},
        "Customer-declared reference CSV",
        "Declared test use only, not reviewed rights",
        original,
    )
    assert original == before
    assert updated["records"]["companies"][0]["name"] == "Replacement A"
    assert (
        updated["records"]["financial_statement_lines"]
        == original["records"]["financial_statement_lines"]
    )
    assert updated["origin"] == "hybrid_reference"
    retained = next(f for f in updated["files"] if f["path"] == updated["input_sources"][0]["path"])
    assert base64.b64decode(retained["bytes_base64"]) == text.encode()
    assert validate(updated)["sha256"] != validate(original)["sha256"]
    with pytest.raises(ValueError, match="reference"):
        import_csv(
            "BOD-FIN",
            "comparable",
            7,
            "companies",
            "key,label\nnew-id,Missing relationship\n",
            {"id": "key", "name": "label"},
            "Invalid source",
            "Declared local test data",
            original,
        )


def test_creative_disclosure_is_rendered_in_actual_png_pixels():
    import io

    from PIL import Image

    good = generate("MKT-LOCALE", "complete")
    bad = generate("MKT-LOCALE", "missing_disclosure")

    def artifact(pack):
        f = next(f for f in pack["files"] if f["path"] == "assets/search-en-IN.png")
        return base64.b64decode(f["bytes_base64"])

    good_image = Image.open(io.BytesIO(artifact(good))).convert("RGB")
    bad_image = Image.open(io.BytesIO(artifact(bad))).convert("RGB")
    assert good_image.size == bad_image.size == (320, 180)
    assert (
        good_image.crop((0, 135, 320, 180)).tobytes()
        != bad_image.crop((0, 135, 320, 180)).tobytes()
    )


@pytest.mark.parametrize(
    "target", ["id,name\na,A\na,B\n", "id,id\na,b\n", "id,name\na,A,unexpected\n"]
)
def test_csv_duplicate_keys_headers_and_excess_fields_rejected(target):
    from anvil.environment_data import import_csv

    with pytest.raises(ValueError):
        import_csv(
            "BOD-FIN",
            "comparable",
            1,
            "companies",
            target,
            {"id": "id", "name": "name"},
            "Malformed CSV",
            "Declared local fixture only",
        )
