import base64
import copy
import hashlib
import json
import runpy
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from anvil.benchmark_bundle import (
    Manifest,
    TrustedSigner,
    actor_view,
    canonical_path,
    parse_manifest,
    verify_signature,
)

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures/benchmark-bundle/fictional-points-v1"
CONTRACT = ROOT / "contracts/praxis/benchmark-bundle-v1"
NOW = datetime(2026, 11, 7, 18, tzinfo=timezone.utc)


def source():
    return json.loads((FIXTURE / "manifest.json").read_bytes())


def encoded(body):
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()


def test_fictional_fixture_is_complete_hash_bound_and_not_partner_data():
    parsed = parse_manifest((FIXTURE / "manifest.json").read_bytes())
    manifest = parsed.manifest
    assert manifest.source.classification == "original_synthetic_fixture"
    assert manifest.scoring.profile == "sme_points_v1"
    assert manifest.scoring.task_maxima == {"FX-001": 24, "FX-002": 6, "FX-003": 51}
    assert sum(len(task.criteria) for task in manifest.tasks) == 81
    assert manifest.scoring.suite_maximum == 81
    assert parsed.canonical == rfc8785.dumps(source())
    assert parsed.canonical_sha256 == hashlib.sha256(parsed.canonical).hexdigest()
    assert parsed.raw_sha256 == hashlib.sha256(parsed.raw).hexdigest()
    declared = {entry.path for entry in manifest.files}
    actual = {str(p.relative_to(FIXTURE)) for p in FIXTURE.rglob("*") if p.is_file()}
    assert actual == declared | {"manifest.json"}
    for entry in manifest.files:
        data = (FIXTURE / entry.path).read_bytes()
        assert len(data) == entry.byte_size
        assert hashlib.sha256(data).hexdigest() == entry.sha256
    assert (
        json.loads((CONTRACT / "manifest.schema.json").read_text()) == Manifest.model_json_schema()
    )


@pytest.mark.parametrize("index", range(3))
def test_actor_projection_never_reaches_private_or_other_task_material(index):
    manifest = parse_manifest(encoded(source())).manifest
    task = manifest.tasks[index]
    projection = actor_view(manifest, task.id)
    text = json.dumps(projection)
    assert projection["task_id"] == task.id
    assert projection["origin"] == "original_synthetic_fixture"
    assert "evaluation_private" not in text and "eval_pack/" not in text
    assert (
        "criteria" not in text and "calibration" not in text and "evaluator_requirement" not in text
    )
    assert "PRIVATE-FICTIONAL" not in text
    assert "rights_references" not in text
    for other in manifest.tasks:
        if other.id != task.id:
            assert other.id not in text
    for path in [projection["prompt_path"], *projection["actor_asset_paths"]]:
        assert path.startswith(f"runtime_pack/{task.id}/")


def test_unknown_actor_task_is_not_projected():
    with pytest.raises(ValueError, match="Unknown task"):
        actor_view(parse_manifest(encoded(source())).manifest, "FX-404")


@pytest.mark.parametrize(
    "path",
    [
        "/absolute",
        "../escape",
        "a/../b",
        "a//b",
        "a/./b",
        "a\\b",
        "C:/x",
        " a",
        "a ",
        "a\n",
        "a/\u0000b",
        "a/.hidden",
        "a/é",
        "a/ｅ",
        "a/setup.py",
        "a/autorun.sh",
        "a/entrypoint.sh",
        "a/" + "x" * 241,
        "/".join(["a"] * 14),
    ],
)
def test_path_aliases_controls_unicode_and_autorun_are_rejected(path):
    with pytest.raises(ValueError):
        canonical_path(path)


def test_json_duplicate_keys_nonfinite_surrogates_depth_and_size_reject():
    raw = encoded(source())
    cases = [
        b'{"schema_version":"x","schema_version":"y"}',
        b'{"n":NaN}',
        b'{"n":Infinity}',
        b'{"n":1e999}',
        b'{"n":"\\ud800"}',
        b"[" * 40 + b"0" + b"]" * 40,
        b" " * (2 * 1024 * 1024 + 1),
    ]
    for case in cases:
        with pytest.raises(ValueError):
            parse_manifest(case)
    assert parse_manifest(raw).manifest.bank.id == "fictional-points"


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "unknown",
        "bool_points",
        "zero_points",
        "duplicate_task",
        "duplicate_criterion",
        "case_alias",
        "file_dir_alias",
        "file_size",
        "total_size",
        "private_prompt",
        "cross_task",
        "missing_actor",
        "extra_actor",
        "private_sidecar",
        "output_alias",
        "reserved_output",
        "bad_rule",
        "bad_calibration",
        "tool_hash",
        "sum",
        "suite_sum",
        "maxima_tasks",
        "missing_criterion",
        "wrong_image_digest",
        "image_credentials",
        "foreign_member",
        "self_manifest",
        "bodhium_fake",
        "timestamp",
        "timeout",
        "key_in_source",
    ],
)
def test_contract_rejects_ambiguous_incomplete_or_authority_smuggling_metadata(mutation):
    body = copy.deepcopy(source())
    t = body["tasks"][0]
    if mutation == "version":
        body["schema_version"] = "praxis.anvil.benchmark_bundle.v2"
    elif mutation == "unknown":
        body["bank"]["approved"] = True
    elif mutation == "bool_points":
        t["criteria"][0]["possible_points"] = True
    elif mutation == "zero_points":
        t["criteria"][0]["possible_points"] = 0
    elif mutation == "duplicate_task":
        body["tasks"].append(copy.deepcopy(t))
    elif mutation == "duplicate_criterion":
        t["criteria"][1]["id"] = t["criteria"][0]["id"]
    elif mutation == "case_alias":
        f = copy.deepcopy(body["files"][0])
        f["path"] = f["path"].upper()
        body["files"].append(f)
    elif mutation == "file_dir_alias":
        f = copy.deepcopy(body["files"][0])
        f["path"] += "/child.txt"
        body["files"].append(f)
    elif mutation == "file_size":
        body["files"][0]["byte_size"] = 50 * 1024 * 1024 + 1
    elif mutation == "total_size":
        for f in body["files"]:
            f["byte_size"] = 50 * 1024 * 1024
    elif mutation == "private_prompt":
        t["prompt_path"] = t["criteria"][0]["rule_ref"]
    elif mutation == "cross_task":
        t["actor_asset_paths"].append(body["tasks"][1]["prompt_path"])
    elif mutation == "missing_actor":
        t["actor_asset_paths"].clear()
    elif mutation == "extra_actor":
        f = copy.deepcopy(body["files"][0])
        f["path"] = "runtime_pack/FX-001/extra.txt"
        body["files"].append(f)
    elif mutation == "private_sidecar":
        t["outputs"][0]["schema_ref"] = t["criteria"][0]["rule_ref"]
    elif mutation == "output_alias":
        t["outputs"].append(copy.deepcopy(t["outputs"][0]))
    elif mutation == "reserved_output":
        t["outputs"][0]["path"] = "eval_pack/result.md"
    elif mutation == "bad_rule":
        t["criteria"][0]["rule_ref"] = body["tasks"][1]["criteria"][0]["rule_ref"]
    elif mutation == "bad_calibration":
        t["calibration_paths"] = [t["prompt_path"]]
    elif mutation == "tool_hash":
        t["tools"][0]["schema_sha256"] = hashlib.sha256(b"different").hexdigest()
    elif mutation == "sum":
        body["scoring"]["task_maxima"][t["id"]] += 1
    elif mutation == "suite_sum":
        body["scoring"]["suite_maximum"] += 1
    elif mutation == "maxima_tasks":
        body["scoring"]["task_maxima"]["missing"] = 1
    elif mutation == "missing_criterion":
        t["criteria"].pop()
    elif mutation == "wrong_image_digest":
        t["environment"]["oci_manifest_digest"] = (
            "sha256:" + hashlib.sha256(b"different").hexdigest()
        )
    elif mutation == "image_credentials":
        t["environment"]["image_reference"] = "https://user:password@example.invalid/image"
    elif mutation == "foreign_member":
        body["files"][0]["task_id"] = "unknown"
    elif mutation == "self_manifest":
        body["files"][0]["path"] = "manifest.json"
    elif mutation == "bodhium_fake":
        body["scoring"]["profile"] = "bodhium_pilot_v1"
    elif mutation == "timestamp":
        body["exported_at"] = "2026-02-30T18:00:00Z"
    elif mutation == "timeout":
        t["timeout_seconds"] = 1801
    else:
        body["source"]["destination_project"] = "cannot-choose-target"
    with pytest.raises(ValueError):
        parse_manifest(encoded(body))


def signing_case(raw):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    signer = TrustedSigner("unit-signer", public, NOW - timedelta(days=1), NOW + timedelta(days=1))
    signature = {
        "profile": "ed25519-jcs-v1",
        "key_id": signer.key_id,
        "algorithm": "Ed25519",
        "signature_base64": base64.b64encode(private.sign(rfc8785.dumps(json.loads(raw)))).decode(),
    }
    return signer, signature


def test_real_ed25519_canonical_signature_and_raw_identity_are_separate():
    raw = encoded(source())
    signer, signature = signing_case(raw)
    pretty = json.dumps(source(), indent=4).encode()
    a = verify_signature(raw, encoded(signature), signers={signer.key_id: signer}, now=NOW)
    b = verify_signature(pretty, encoded(signature), signers={signer.key_id: signer}, now=NOW)
    assert a.status == b.status == "verified"
    assert a.canonical_sha256 == b.canonical_sha256
    assert a.raw_sha256 != b.raw_sha256
    assert a.key_id == signer.key_id


def test_unsigned_unknown_expired_revoked_never_become_verified():
    raw = encoded(source())
    signer, signature = signing_case(raw)
    assert verify_signature(raw, None, signers={}, now=NOW).status == "quarantined_unsigned"
    assert (
        verify_signature(raw, encoded(signature), signers={}, now=NOW).status
        == "quarantined_unknown_signer"
    )
    assert (
        verify_signature(
            raw, encoded(signature), signers={signer.key_id: signer}, now=signer.not_after
        ).status
        == "quarantined_expired_signer"
    )
    revoked = TrustedSigner(
        signer.key_id, signer.public_key, signer.not_before, signer.not_after, revoked=True
    )
    assert (
        verify_signature(raw, encoded(signature), signers={signer.key_id: revoked}, now=NOW).status
        == "quarantined_revoked_signer"
    )
    assert (
        verify_signature(
            raw,
            encoded(signature),
            signers={signer.key_id: signer},
            now=signer.not_before - timedelta(seconds=1),
        ).status
        == "quarantined_expired_signer"
    )


def test_tampering_algorithm_embedded_roots_and_bad_signatures_reject():
    raw = encoded(source())
    signer, signature = signing_case(raw)
    changed = source()
    changed["bank"]["title"] += " changed"
    for bad_raw, bad_sig in [
        (encoded(changed), signature),
        (raw, {**signature, "algorithm": "none"}),
        (raw, {**signature, "public_key": base64.b64encode(signer.public_key).decode()}),
        (raw, {**signature, "signature_base64": "not-base64"}),
        (raw, {**signature, "signature_base64": base64.b64encode(b"short").decode()}),
    ]:
        with pytest.raises(ValueError):
            verify_signature(bad_raw, encoded(bad_sig), signers={signer.key_id: signer}, now=NOW)
    with pytest.raises(ValueError):
        verify_signature(
            raw, encoded(signature), signers={signer.key_id: signer}, now=NOW.replace(tzinfo=None)
        )


def test_duplicate_signature_keys_do_not_select_an_alternate_trust_root():
    raw = encoded(source())
    with pytest.raises(ValueError):
        verify_signature(raw, b'{"key_id":"a","key_id":"b"}', signers={}, now=NOW)


@pytest.mark.parametrize("scope", ["payload", "output"])
def test_nonadjacent_file_directory_aliases_reject(scope):
    body = source()
    if scope == "payload":
        entry = next(f for f in body["files"] if f["path"] == "eval_pack/FX-001/rules.json")
        for suffix in ["-interposed", "/child.json"]:
            body["files"].append({**entry, "path": entry["path"] + suffix})
    else:
        entry = body["tasks"][0]["outputs"][0]
        for suffix in ["-interposed", "/child.md"]:
            body["tasks"][0]["outputs"].append({**entry, "path": entry["path"] + suffix})
    with pytest.raises(ValueError, match="alias"):
        parse_manifest(encoded(body))


def test_fictional_oracle_good_bad_empty_bool_and_injection_paths():
    folder = FIXTURE / "eval_pack/FX-001"
    evaluate = runpy.run_path(str(folder / "evaluator.py"))["evaluate"]
    rules = json.loads((folder / "rules.json").read_bytes())
    cases = json.loads((folder / "calibration.json").read_bytes())
    assert sum(evaluate(rules, cases["good"]).values()) == 24
    for output in [
        cases["bad"],
        cases["empty"],
        {"item-001": True},
        {"item-001": cases["injection_text"]},
    ]:
        assert sum(evaluate(rules, output).values()) == 0


def test_fictional_stdio_tool_real_process_schema_and_error_paths(tmp_path):
    script = FIXTURE / "runtime_pack/FX-001/tool-server.py"
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "square", "arguments": {"n": 7}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "square", "arguments": {"n": True}},
        },
    ]
    result = subprocess.run(
        [sys.executable, str(script)],
        input="".join(json.dumps(v) + "\n" for v in messages),
        text=True,
        capture_output=True,
        timeout=5,
        cwd=tmp_path,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    schema = json.loads((script.parent / "tools.json").read_text())
    assert replies[0]["result"]["tools"] == schema["tools"]
    assert replies[1]["result"]["content"][0]["text"] == "49"
    assert replies[1]["result"]["isError"] is False
    assert replies[2]["result"]["isError"] is True
