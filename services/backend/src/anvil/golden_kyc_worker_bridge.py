"""Fixed KYC worker session; model credentials remain in the existing broker.

Only the installed candidate closure and bounded operational scheduler are
accepted. Authoring/task JSON cannot supply a callable, interpreter or script.
The guard rechecks the current broker lease/readiness, never grants spending.
"""

from dataclasses import dataclass
from types import CodeType, FunctionType

from anvil.marketing_native_wire_bounds import remaining
from anvil.praxis_generic_contract import digest


@dataclass(frozen=True, slots=True)
class KycWorkerSession:
    candidate: object
    binding_sha256: str
    public_sha256: str
    preparation_sha256: str
    absolute_deadline: float

    def _closure(self):
        from anvil import golden_kyc_paid_worker
        from anvil.golden_kyc_deadline_database import SchedulerConnections
        from anvil.golden_kyc_deadline_transport import forward

        execute = golden_kyc_paid_worker.execute

        expected = next(code for code in execute.__code__.co_consts if type(code) is CodeType and code.co_name == "candidate")
        if (type(self.candidate) is not FunctionType or self.candidate.__code__ is not expected
                or self.candidate.__globals__ is not vars(golden_kyc_paid_worker)):
            raise ValueError("Exact installed KYC candidate handler required")
        values = dict(zip(expected.co_freevars, (cell.cell_contents for cell in self.candidate.__closure__ or ())))
        turns = values["candidate_turns"]
        turns_code = next(code for code in execute.__code__.co_consts if type(code) is CodeType and code.co_name == "candidate_turns")
        if type(turns) is not FunctionType or turns.__code__ is not turns_code or turns.__globals__ is not vars(golden_kyc_paid_worker):
            raise ValueError("Exact installed KYC stage handler required")
        for key, value in zip(turns_code.co_freevars, (cell.cell_contents for cell in turns.__closure__ or ())):
            if key in values and values[key] is not value:
                raise ValueError("KYC handler closure identity changed")
            values[key] = value
        dispatch_code = next(code for code in execute.__code__.co_consts if type(code) is CodeType and code.co_name == "dispatch")
        dispatch = values["dispatch"]
        if type(dispatch) is not FunctionType or dispatch.__code__ is not dispatch_code or dispatch.__globals__ is not vars(golden_kyc_paid_worker):
            raise ValueError("Exact bounded KYC broker handler required")
        dispatch_values = dict(zip(dispatch_code.co_freevars, (cell.cell_contents for cell in dispatch.__closure__ or ())))
        if dispatch_values["original_dispatch"] is not forward or type(values["connections"]) is not SchedulerConnections:
            raise ValueError("Dedicated scheduler and fixed broker transport required")
        from anvil.golden_kyc_openenv import GoldenEnvironment
        from anvil.golden_mcp_client import McpEpisode

        if type(values["episode"]) is not GoldenEnvironment or values["tools_factory"] not in (None, McpEpisode):
            raise ValueError("Exact installed KYC environment and MCP handler required")
        if digest(values["prepared"]) != self.preparation_sha256:
            raise ValueError("Original KYC preparation changed")
        remaining(self.absolute_deadline)
        if dispatch_values["deadline"][0] != self.absolute_deadline:
            raise ValueError("Original KYC controller cutoff changed")
        return values

    def validate(self, binding, public):
        values = self._closure()
        if digest(binding) != self.binding_sha256 or digest(public) != self.public_sha256:
            raise ValueError("Exact immutable KYC bridge binding required")
        expected = {"project_id": str(values["job"]["project_id"]), "job_id": str(values["job"]["id"]),
                    "plan_id": str(values["plan"]), "lease_sha256": digest(str(values["job"]["lease_token"])),
                    "trial_id": str(values["trial"]["trial_id"]), "generation": values["episode"].credentials["generation"],
                    "input_sha256": digest(public)}
        if binding != expected:
            raise ValueError("Actual leased KYC job and trial required")

    def guard(self):
        values = self._closure()
        if values["dispatch"](values["job"], values["user"], values["plan"], 0, operation="readiness") is not True:
            raise RuntimeError("Current KYC lease, rights and readiness required")
        return {"ready": True, "binding_sha256": self.binding_sha256, "preparation_sha256": self.preparation_sha256}

    def invoke(self, heartbeat):
        if not heartbeat():
            raise RuntimeError("Original SDK guardian required before readiness")
        self.guard()

        def authority():
            if not heartbeat():
                return False
            try:
                self.guard()
                return True
            except Exception:
                return False

        return self.candidate(authority)
