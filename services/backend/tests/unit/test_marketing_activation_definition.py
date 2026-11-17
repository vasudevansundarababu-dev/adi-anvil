"""New exact-byte private v4 and bounded source-codec controls."""

import base64
import os
import zlib
from copy import deepcopy
from pathlib import Path

import pytest
from test_marketing_service_definition import candidate
from test_marketing_world_finance import source

from anvil.marketing_world_activation_definition import paths, with_activation
from anvil.marketing_world_calendar import propose, with_program
from anvil.marketing_world_definition import definition
from anvil.marketing_world_funding_definition import with_finance
from anvil.marketing_world_source_encoding import LIMIT, decode, encode
from anvil.praxis_generic_contract import canonical


def proposal():
    _, service_world = candidate()
    files, _ = source()
    funded = with_finance(service_world, files)
    root = Path(os.environ["ANVIL_MARKETING_SOURCE_FIXTURE_ROOT"])
    files.update({path: (root / path).read_bytes() for path in paths("GT2-R01")})
    # Explicitly apply the operator proposal to this manufactured source
    # wrapper. No deployed environment, task count or business date changes.
    funded = with_program(funded, propose("GT2-R01", files, funded["source_hashes"], funded["service_contract"]))
    return funded, with_activation(funded, files)


def test_private_v4_preserves_outer_limits_and_complete_baseline_with_three_pinned_alternatives():
    previous, value = proposal()
    before = deepcopy(previous)
    parsed = definition(value)
    assert parsed.schema_version == "anvil.marketing-private-world-definition.v4"
    assert len(canonical(value)) < 16777216
    assert len(parsed.records["reports"]) == 2208
    assert previous == before and "activation_source_documents" not in previous
    for branch in ("positive", "null", "negative"):
        finance, reports = parsed.selected_programs(branch)
        assert finance["case_id"] == reports["case_id"] == "GT2-R01"
        assert reports["branch"] == branch


def test_self_encoded_changed_source_cannot_bypass_independent_inventory():
    _, value = proposal()
    path = "reviewer_only/us-pair/GT2-R01/reuse-test-positive/alternative_daily_performance.jsonl"
    value["activation_source_documents"][path] = encode(b'{"id":"forged"}\n')
    with pytest.raises(ValueError, match="independently pinned"):
        definition(value)


def test_actor_baseline_cannot_be_replaced_by_outcome_data_before_activation():
    _, value = proposal()
    value["records"]["reports"][0]["public"]["verified_visits"] += 1
    with pytest.raises(ValueError, match="complete pinned baseline"):
        definition(value)


@pytest.mark.parametrize("raw", [b"x", b"x" * LIMIT, b'[{"some":"fixture"}]\n'])
def test_bounded_private_source_encoding_is_lossless(raw):
    assert decode(encode(raw)) == raw


@pytest.mark.parametrize("packed", [zlib.compress(b"x" * (LIMIT + 1)), zlib.compress(b"x")[:-1],
                                     zlib.compress(b"x") + zlib.compress(b"y"), zlib.compress(b"")])
def test_oversized_truncated_multistream_and_empty_private_sources_deny(packed):
    with pytest.raises(ValueError):
        decode(base64.b64encode(packed).decode("ascii"))
