"""API image source/policy controls; no DB, credentials, SDK requests or admission."""

import hashlib
import json
import os
from pathlib import Path

from anvil.golden_kyc_evaluators import OPA_POLICIES, opa_guard
from anvil.golden_kyc_source import source_hash
from anvil.qualification_resources import qualification_root

assert qualification_root() == Path("/app")
source = source_hash()
assert source == os.environ["EXPECTED_SOURCE_SHA256"]
facts = {name: True for name in OPA_POLICIES}
assert opa_guard(facts)["allow"] is True
assert opa_guard(facts | {"assigned_case": False})["allow"] is False
print(
    json.dumps(
        {
            "scope": "installed_API_source_and_policy_controls_only",
            "source_sha256": source,
            "model_calls": 0,
            "native_qualified": False,
            "opa_binary_sha256": hashlib.sha256(Path("/opt/anvil/opa").read_bytes()).hexdigest(),
        }
    )
)
