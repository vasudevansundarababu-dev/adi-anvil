"""Both installed consumers must pin the actual shared operator source."""

import hashlib

from anvil.config import ROOT
from anvil.environment_harbor import OPERATOR_PROOF_SHA256 as kyc_pin
from anvil.marketing_native_private_records import OPERATOR_PROOF_SHA256 as marketing_pin


def test_shared_operator_pins_match_the_packaged_source():
    actual = hashlib.sha256((ROOT / "services/harbor/src/anvil_harbor/operator_proof.py").read_bytes()).hexdigest()
    assert kyc_pin == marketing_pin == actual
