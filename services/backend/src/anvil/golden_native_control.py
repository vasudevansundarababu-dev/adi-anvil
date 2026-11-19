"""Fixed no-effect transport control, never SQL/model or paid-run authority.

The actual two-read SQL Trial is qualified separately. This control exercises
the same private-PID worker/root-SDK transport without a broker credential,
arbitrary callback, fabricated paid readiness or production qualification.
"""

import os
import time
from dataclasses import dataclass
from uuid import uuid4

from anvil.praxis_generic_contract import digest

PURPOSE = "native_transport_control_only"
PUBLIC = {"schema_version": "anvil.native-transport-control-input.v1", "operation": "fixed_custody_ping", "model_performance": False}
PREPARATION = digest(PUBLIC)


@dataclass(frozen=True, slots=True)
class TransportControlSession:
    binding_sha256: str
    public_sha256: str
    absolute_deadline: float
    preparation_sha256: str = PREPARATION

    def validate(self, binding, public):
        if (public != PUBLIC or digest(binding) != self.binding_sha256 or digest(public) != self.public_sha256
                or self.preparation_sha256 != PREPARATION or os.geteuid() != 10001 or os.getegid() != 10001):
            raise ValueError("Fixed isolated nonspending transport control required")
        self.guard()

    def guard(self):
        if time.monotonic() >= self.absolute_deadline:
            raise RuntimeError("Original transport control cutoff expired")
        return {"ready": True, "binding_sha256": self.binding_sha256, "preparation_sha256": PREPARATION}

    def invoke(self, guard):
        if not guard():
            raise ValueError("Actual SDK custody required before control")
        self.guard()
        result = {"schema_version": "anvil.native-transport-control-output.v1", "purpose": PURPOSE,
                  "operation": "fixed_custody_ping", "worker_uid": os.geteuid(), "worker_pid": os.getpid()}
        receipt = {"schema_version": "anvil.native-transport-control-receipt.v1", "purpose": PURPOSE,
                   "binding_sha256": self.binding_sha256, "output_sha256": digest(result),
                   "task_score": None, "model_performance": False, "qualification_granted": False}
        if not guard():
            raise ValueError("Original SDK custody lost before control completion")
        return result, receipt


def run(root, seconds=300):
    from anvil.golden_native_bridge import _submit

    binding = {key: str(uuid4()) for key in ("project_id", "job_id", "plan_id", "trial_id")}
    binding.update(lease_sha256=digest({"control_nonce": uuid4().hex}), generation=0, input_sha256=digest(PUBLIC))
    session = TransportControlSession(digest(binding), digest(PUBLIC), time.monotonic() + seconds)
    session.validate(binding, PUBLIC)
    return _submit(root, binding, PUBLIC, session.invoke, seconds=seconds, session=session)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError("Installed isolated runtime required")
    # -m executes this file as __main__. Typed admission must use the one
    # installed canonical module/class identity, never its duplicate.
    from anvil.golden_native_control import run as installed_run

    observed = installed_run(args.root)
    print(__import__("json").dumps({"status": "observed_not_qualified", "purpose": PURPOSE,
        "framework_trial_id": observed["framework_trial_id"], "evidence_sha256": digest(observed),
        "qualification_granted": False, "task_score": None, "model_performance": False,
        "model_calls_authorized": 0, "actual_model_calls": None}))
