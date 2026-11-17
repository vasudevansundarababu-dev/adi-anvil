"""Private API fence/ledger contract; process shutdown is separate evidence.

Only the locked private SQL producer may supply context to this module. Pure
projection or a valid hash is not native runtime authority or a stop receipt.
"""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from anvil.dataset_export_contract import Sha
from anvil.praxis_generic_contract import digest
from anvil.schemas import Strict


class Pending(Strict):
    sdk_dispatching: int = Field(strict=True, ge=0, le=1000)
    sdk_unknown: int = Field(strict=True, ge=0, le=1000)
    tool_pending: int = Field(strict=True, ge=0, le=8000)
    workflow_pending: int = Field(strict=True, ge=0, le=400)
    workflow_unknown: int = Field(strict=True, ge=0, le=400)


class Wire(Strict):
    @model_validator(mode="before")
    @classmethod
    def exact_flags(cls, value):
        if isinstance(value, dict):
            for key in (
                "new_work_permitted",
                "api_quiescent",
                "physical_stop_verified",
                "native_qualified",
            ):
                if key in value and type(value[key]) is not bool:
                    raise ValueError("Actual JSON Boolean receipt flags required")
            if "fence_epoch" in value and type(value["fence_epoch"]) is not int:
                raise ValueError("Exact integer fence epoch required")
        return value


class Scope(Wire):
    project_id: UUID
    job_id: UUID
    plan_id: UUID
    world_binding_id: UUID
    world_binding_sha256: Sha
    episode_id: UUID
    generation: int = Field(strict=True, ge=0)
    lease_sha256: Sha
    source_qualification_sha256: Sha
    execution_sha256: Sha


class Fence(Scope):
    schema_version: Literal["anvil.marketing-world-fence.v1"]
    fence_id: UUID
    fence_epoch: Literal[1]
    fenced_at: AwareDatetime
    graph_ledger_sha256: Sha
    reconstruction_sha256: Sha | None
    new_work_permitted: Literal[False]
    receipt_sha256: Sha

    @model_validator(mode="after")
    def body_hash(self):
        if digest(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("Exact immutable API fence body required")
        return self


class Quiescence(Scope):
    schema_version: Literal["anvil.marketing-world-quiescence.v2"]
    fence_id: UUID
    fence_epoch: Literal[1]
    fence_receipt_sha256: Sha
    quiescence_id: UUID
    observed_at: AwareDatetime
    graph_ledger_sha256: Sha
    reconstruction_sha256: Sha
    fenced_graph_ledger_sha256: Sha
    fenced_reconstruction_sha256: Sha | None
    terminal_status: Literal["recorded_done", "recorded_hold_requires_qualification"]
    pending: Pending
    new_work_permitted: Literal[False]
    api_quiescent: Literal[True]
    physical_stop_verified: Literal[False]
    native_qualified: Literal[False]
    receipt_sha256: Sha

    @model_validator(mode="after")
    def actual_zero_and_hash(self):
        if any(self.pending.model_dump().values()):
            raise ValueError("API quiescence requires zero actual pending/unknown ledger entries")
        if digest(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("Exact immutable API quiescence body required")
        return self


class Status(Wire):
    schema_version: Literal["anvil.marketing-world-quiescence-status.v2"]
    fence: Fence
    state: Literal["fenced_pending", "fenced_unknown", "api_quiescent"]
    pending: Pending
    quiescence: Quiescence | None
    physical_stop_verified: Literal[False]
    native_qualified: Literal[False]

    @model_validator(mode="after")
    def consistent(self):
        if (self.state == "api_quiescent") != (self.quiescence is not None):
            raise ValueError("Only a retained immutable quiescence receipt permits api_quiescent")
        if self.quiescence is not None:
            proof = self.quiescence
            scope = Scope.model_fields
            if (
                any(getattr(self.fence, key) != getattr(proof, key) for key in scope)
                or proof.fence_id != self.fence.fence_id
                or proof.fence_epoch != self.fence.fence_epoch
                or proof.fence_receipt_sha256 != self.fence.receipt_sha256
                or proof.fenced_graph_ledger_sha256 != self.fence.graph_ledger_sha256
                or proof.fenced_reconstruction_sha256 != self.fence.reconstruction_sha256
                or self.pending != proof.pending
            ):
                raise ValueError("Exact same fenced scope/graph and zero ledger receipt required")
        return self


def recorded_terminal(reconstruction):
    """Classify actual readonly reconstruction, never infer abort from silence."""
    if type(reconstruction) is not dict:
        raise ValueError("Actual recorded reconstruction required")
    body = {key: value for key, value in reconstruction.items() if key != "reconstruction_sha256"}
    if digest(body) != reconstruction.get("reconstruction_sha256"):
        raise ValueError("Actual reconstruction body hash required")
    if reconstruction.get("partial_reason") is not None:
        return None
    state = reconstruction.get("state")
    if type(state) is not dict:
        return None
    if state.get("terminal") == "done" and reconstruction.get("workflow_status") == "closed":
        return "recorded_done"
    if (
        state.get("terminal") == "awaiting_authority"
        and reconstruction.get("workflow_status") == "hold_requires_qualification"
    ):
        return "recorded_hold_requires_qualification"
    return None


def unresolved_state(pending):
    pending = Pending.model_validate(pending)
    if pending.sdk_unknown or pending.workflow_unknown:
        return "fenced_unknown"
    if any(pending.model_dump().values()):
        return "fenced_pending"
    # Zero counters alone cannot supply terminal/abort proof or a receipt.
    return "fenced_unknown"


def _context_steps(claim):
    from anvil.campaign_semantic_contract import bounded_json

    value = (yield (
        "SELECT marketing_runtime.world_stop_context(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ))["value"]
    if not value:
        raise RuntimeError("marketing_exact_current_world_stop_context_required")
    bounded_json(value, 33554432, max_nodes=300000)
    row = value["session"]
    if (
        any(str(row[name]) != str(claim.value[name]) for name in ("world_binding_id", "episode_id"))
        or row["generation"] != claim.value["generation"]
        or row["world_binding_sha256"] != claim.value["world_binding_sha256"]
    ):
        raise ValueError("Exact current leased private world stop scope required")
    Pending.model_validate(value["pending"])
    from anvil.marketing_world_service_api import checked_records

    service = (yield (
        "SELECT marketing_runtime.private_world_service_records(%s,%s,%s) AS value",
        (claim.job_id, claim.lease_token, claim.plan_id),
    ))["value"]
    value["graph_records"]["service_records"] = checked_records(service)
    return value


def _retained(value, name, model):
    record = value[name]
    if not record or digest(record["receipt"]) != record["body_sha256"]:
        raise ValueError("Actual immutable private API stop receipt custody required")
    return model.model_validate(record["receipt"])


def _dispatch_steps(claim):
    """API-only. All context/writes remain in the caller's commit transaction."""
    if claim.operation not in {"fence", "drain", "quiescence"}:
        raise ValueError("Fixed stop-only world operation required")
    from anvil.db import uid
    from anvil.marketing_world_release import recorded_records
    from anvil.praxis_generic_contract import canonical
    from anvil.praxis_marketing_contract import MarketingExecution

    value = (yield from _context_steps(claim))  # Group -> exclusive plan fence -> exact private session.
    row = value["session"]
    if digest(value["execution"]) != row["attachment"]["execution_sha256"]:
        raise ValueError("Exact immutable bound execution required for stop evidence")
    execution = MarketingExecution.model_validate(value["execution"]).model_dump(mode="json")
    if claim.operation == "fence" and value["fence"] is None:
        try:
            graph, _ = recorded_records(value["graph_records"], row, execution)
            terminal = {
                "terminal_status": recorded_terminal(graph),
                "reconstruction_sha256": graph["reconstruction_sha256"],
            }
        except ValueError:
            # Fence new work even when the actual ledger cannot reconstruct.
            # Absence of proof never fabricates terminal/abort/quiescence.
            terminal = {"terminal_status": None, "reconstruction_sha256": None}
        scope = Scope.model_validate(
            {
                **{
                    name: row[name]
                    for name in (
                        "project_id",
                        "job_id",
                        "plan_id",
                        "world_binding_id",
                        "world_binding_sha256",
                        "episode_id",
                        "generation",
                        "lease_sha256",
                    )
                },
                "source_qualification_sha256": value["source_qualification_sha256"],
                "execution_sha256": row["attachment"]["execution_sha256"],
            }
        ).model_dump(mode="json")
        body = {
            "schema_version": "anvil.marketing-world-fence.v1",
            **scope,
            "fence_id": uid(),
            "fence_epoch": 1,
            "fenced_at": TypeAdapter(AwareDatetime).dump_python(
                TypeAdapter(AwareDatetime).validate_python(value["observed_at"]), mode="json"
            ),
            "graph_ledger_sha256": value["graph_ledger_sha256"],
            "reconstruction_sha256": terminal["reconstruction_sha256"],
            "new_work_permitted": False,
        }
        receipt = Fence.model_validate(body | {"receipt_sha256": digest(body)}).model_dump(
            mode="json"
        )
        if not (yield (
            "SELECT marketing_runtime.record_world_fence(%s,%s,%s,%s,%s,%s,%s) AS allowed",
            (
                claim.job_id,
                claim.lease_token,
                claim.plan_id,
                value["graph_ledger_sha256"],
                canonical(terminal).decode(),
                canonical(receipt).decode(),
                digest(receipt),
            ),
        ))["allowed"]:
            raise RuntimeError("marketing_world_fence_commit_unconfirmed_no_replay")
        value = (yield from _context_steps(claim))
    fence = _retained(value, "fence", Fence)
    pending = Pending.model_validate(value["pending"])
    terminal = value["fence"]["terminal"]
    if claim.operation in {"fence", "drain"} and value["quiescence"] is None:
        try:
            graph, _ = recorded_records(value["graph_records"], row, execution)
            terminal = {
                "terminal_status": recorded_terminal(graph),
                "reconstruction_sha256": graph["reconstruction_sha256"],
            }
        except ValueError:
            terminal = {"terminal_status": None, "reconstruction_sha256": None}
    # A readback is side-effect free. Only explicit fence/drain operations may
    # persist its unique immutable zero-ledger receipt in the same transaction.
    if (
        claim.operation in {"fence", "drain"}
        and value["quiescence"] is None
        and not any(pending.model_dump().values())
        and terminal["terminal_status"] in {"recorded_done", "recorded_hold_requires_qualification"}
    ):
        body = fence.model_dump(
            mode="json", exclude={"schema_version", "fenced_at", "receipt_sha256"}
        ) | {
            "schema_version": "anvil.marketing-world-quiescence.v2",
            "graph_ledger_sha256": value["graph_ledger_sha256"],
            "reconstruction_sha256": terminal["reconstruction_sha256"],
            "fenced_graph_ledger_sha256": fence.graph_ledger_sha256,
            "fenced_reconstruction_sha256": fence.reconstruction_sha256,
            "fence_receipt_sha256": fence.receipt_sha256,
            "quiescence_id": uid(),
            "observed_at": TypeAdapter(AwareDatetime).dump_python(
                TypeAdapter(AwareDatetime).validate_python(value["observed_at"]), mode="json"
            ),
            "terminal_status": terminal["terminal_status"],
            "pending": pending.model_dump(),
            "api_quiescent": True,
            "physical_stop_verified": False,
            "native_qualified": False,
        }
        receipt = Quiescence.model_validate(body | {"receipt_sha256": digest(body)}).model_dump(
            mode="json"
        )
        if not (yield (
            "SELECT marketing_runtime.record_world_quiescence(%s,%s,%s,%s,%s,%s,%s) AS allowed",
            (
                claim.job_id,
                claim.lease_token,
                claim.plan_id,
                value["graph_ledger_sha256"],
                canonical(terminal).decode(),
                canonical(receipt).decode(),
                digest(receipt),
            ),
        ))["allowed"]:
            raise RuntimeError("marketing_world_quiescence_commit_unconfirmed_no_replay")
        value = (yield from _context_steps(claim))
        pending = Pending.model_validate(value["pending"])
    quiescence = (
        _retained(value, "quiescence", Quiescence) if value["quiescence"] is not None else None
    )
    if quiescence is not None and quiescence.graph_ledger_sha256 != value["graph_ledger_sha256"]:
        raise RuntimeError("marketing_retained_quiescence_final_ledger_drift_unknown")
    return Status(
        schema_version="anvil.marketing-world-quiescence-status.v2",
        fence=fence,
        state="api_quiescent" if quiescence is not None else unresolved_state(pending),
        pending=pending,
        quiescence=quiescence,
        physical_stop_verified=False,
        native_qualified=False,
    ).model_dump(mode="json")


def _drive(connection, steps):
    value = None
    try:
        while True:
            try:
                sql, parameters = steps.send(value)
            except StopIteration as done:
                return done.value
            value = connection.execute(sql, parameters).fetchone()
    finally:
        steps.close()


def _context(connection, claim):
    return _drive(connection, _context_steps(claim))


def dispatch(connection, claim):
    """Legacy synchronous utility; native capture uses async scoped SQL."""
    return _drive(connection, _dispatch_steps(claim))


async def dispatch_async(connection, claim):
    """Same single-pass receipt algorithm, awaiting each original SQL operation."""
    steps, value = _dispatch_steps(claim), None
    try:
        while True:
            try:
                sql, parameters = steps.send(value)
            except StopIteration as done:
                return done.value
            value = await (await connection.execute(sql, parameters)).fetchone()
    finally:
        steps.close()
