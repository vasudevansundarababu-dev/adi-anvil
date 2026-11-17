"""Producer-specific numeric argument hashing; no SQL or SDK admission claim."""

from contextlib import contextmanager

from anvil.db import digest as metadata_digest
from anvil.marketing_paid_turn import BeforeEffect
from anvil.praxis_generic_contract import digest as producer_digest


def test_action_intent_keeps_rfc8785_hash_for_real_json_numeric_arguments():
    arguments = {"content": {"whole_float": 1.0, "small": 1e-7, "negative_zero": -0.0}}
    observed = []

    class Connection:
        def execute(self, query, values):
            observed.append(values[-1])
            return self

        def fetchone(self):
            return {"allowed": True}

    @contextmanager
    def connections():
        yield Connection()

    callback = BeforeEffect(
        connections, {"id": "job", "lease_token": "lease", "plan_id": "plan"}, 0, "call"
    )
    callback("a" * 32, "intent.write", arguments)
    assert observed == [producer_digest(arguments)]
    assert observed[0] != metadata_digest(arguments)
    assert producer_digest(arguments) == producer_digest(
        {"content": {"whole_float": 1, "small": 0.0000001, "negative_zero": 0}}
    )
