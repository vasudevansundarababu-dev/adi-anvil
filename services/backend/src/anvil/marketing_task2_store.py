"""Locked SQL Task2 episodes; no publication, provider calls or Run admission."""

from anvil.db import Jsonb
from anvil.marketing_task2_contract import WIRE_ROLES
from anvil.marketing_task2_persistence import freeze, restore
from anvil.praxis_case_dataset import CaseDatasetRef
from anvil.praxis_generic_contract import digest


def create(c, project, user, dataset, snapshot_sha256, controller):
    reference = CaseDatasetRef.model_validate(dataset)
    state, fingerprint = freeze(controller)
    c.execute(
        "INSERT INTO marketing_runtime.episodes(id,project_id,assigned_user,case_id,dataset_id,dataset_version,dataset_sha256,snapshot_sha256,generation,state,state_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            controller.trial_id,
            project,
            user,
            controller.case_id,
            reference.id,
            reference.version,
            reference.sha256,
            snapshot_sha256,
            controller.generation,
            Jsonb(state),
            fingerprint,
        ),
    )
    return {
        "trial_id": controller.trial_id,
        "generation": controller.generation,
        "runtime_qualified": False,
        "run_authority": "not_granted",
    }


def locked(c, project, user, episode, generation, *, allow_sealed=False):
    row = c.execute(
        "SELECT * FROM marketing_runtime.episodes WHERE project_id=%s AND id=%s FOR UPDATE",
        (project, episode),
    ).fetchone()
    if (
        not row
        or str(row["assigned_user"]) != str(user)
        or type(generation) is not int
        or row["generation"] != generation
    ):
        raise ValueError("Assigned Marketing episode and current generation required")
    if (
        not allow_sealed
        and c.execute(
            "SELECT 1 FROM marketing_runtime.seals WHERE project_id=%s AND episode_id=%s AND generation=%s",
            (project, episode, generation),
        ).fetchone()
    ):
        raise ValueError("Marketing generation is sealed; explicit reset required")
    controller = restore(row["state"], row["state_sha256"])
    if (
        controller.trial_id != str(row["id"])
        or controller.generation != generation
        or controller.case_id != row["case_id"]
    ):
        raise ValueError("Marketing SQL identity differs from private checkpoint")
    return row, controller


def save(c, row, controller):
    state, fingerprint = freeze(controller)
    c.execute(
        "UPDATE marketing_runtime.episodes SET state=%s,state_sha256=%s,generation=%s,updated_at=now() WHERE project_id=%s AND id=%s",
        (Jsonb(state), fingerprint, controller.generation, row["project_id"], row["id"]),
    )


def call(c, project, user, episode, generation, role, operation, body):
    if role not in WIRE_ROLES:
        raise ValueError("Known canonical Marketing role required")
    row, controller = locked(c, project, user, episode, generation)
    # The bound host adapter selects a role, not a model-supplied token. Private
    # state, future releases and capabilities never become the tool response.
    result = controller.call(controller.credential(WIRE_ROLES[role]), generation, operation, body)
    save(c, row, controller)
    return result


def named_call(
    c,
    project,
    user,
    episode,
    generation,
    role,
    operation,
    body,
    execution,
    request_id,
    *,
    source_refs=(),
):
    """Published-role tool effect and receipt commit together; no inferred replay."""
    from anvil.marketing_task2_tools import execute

    if not c.execute(
        "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE m.project_id=%s AND m.user_id=%s AND m.active AND m.role IN('admin','rl-engineer')",
        (project, user),
    ).fetchone():
        raise ValueError("Current Marketing execution assignment required")
    row, controller = locked(c, project, user, episode, generation)
    check_source_refs(controller, source_refs)
    old = c.execute(
        "SELECT * FROM marketing_runtime.tool_receipts WHERE project_id=%s AND id=%s",
        (project, request_id),
    ).fetchone()
    arguments_sha, catalogue_sha = digest(body), digest(execution)
    if old:
        if (
            str(old["episode_id"]) != str(episode)
            or old["generation"] != generation
            or old["role"] != role
            or old["operation"] != operation
            or old["arguments_sha256"] != arguments_sha
            or old["catalogue_sha256"] != catalogue_sha
            or old["source_refs_sha256"] != digest(list(source_refs))
            or digest(old["result"]) != old["result_sha256"]
        ):
            raise ValueError("Immutable Marketing tool correlation differs; no replay")
        return old["result"]
    result = execute(controller, role, operation, body, execution)
    save(c, row, controller)
    captured_state, captured_state_sha = freeze(controller)
    c.execute(
        "INSERT INTO marketing_runtime.tool_receipts(id,project_id,episode_id,generation,role,operation,arguments_sha256,catalogue_sha256,source_refs_sha256,result,result_sha256,state_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            request_id,
            project,
            episode,
            generation,
            role,
            operation,
            arguments_sha,
            catalogue_sha,
            digest(list(source_refs)),
            Jsonb(result),
            digest(result),
            captured_state_sha,
        ),
    )
    if c.execute(
        "SELECT to_regprocedure('marketing_runtime.capture_paid_tool_state(uuid,jsonb,text,text)') AS function"
    ).fetchone()["function"]:
        from anvil.marketing_paid_state import effect_view

        view = effect_view(captured_state)
        captured = c.execute(
            "SELECT marketing_runtime.capture_paid_tool_state(%s,%s,%s,%s) AS captured",
            (request_id, Jsonb(view), digest(view), captured_state_sha),
        ).fetchone()["captured"]
        if captured is False:
            # State, receipt and private projection commit together. An error
            # leaves the previously committed tool intent unknown, never replayed.
            raise RuntimeError("Marketing private tool-state custody unavailable")
    return result


def check_source_refs(controller, references):
    if not isinstance(references, (list, tuple)) or len(references) > 30:
        raise ValueError("Bounded workflow input artifact references required")
    for reference in references:
        if not isinstance(reference, dict) or set(reference) != {"id", "version", "sha256"}:
            raise ValueError("Exact workflow input artifact reference required")
        current = controller._objects.get(reference["id"])
        if (
            current is None
            or current["version"] != reference["version"]
            or digest(current) != reference["sha256"]
        ):
            raise ValueError("Workflow input artifact was revised; stale node effect denied")


def control(c, project, user, episode, generation, operation, body, *, idempotency_key):
    row, controller = locked(c, project, user, episode, generation)
    result = controller.control(
        controller.controller_credential(),
        generation,
        operation,
        body,
        idempotency_key=idempotency_key,
    )
    save(c, row, controller)
    return result


def seal(c, project, user, episode, generation):
    row, controller = locked(c, project, user, episode, generation, allow_sealed=True)
    capture = controller.capture()
    fingerprint = digest(capture)
    old = c.execute(
        "SELECT capture_sha256 FROM marketing_runtime.seals WHERE project_id=%s AND episode_id=%s AND generation=%s",
        (project, episode, generation),
    ).fetchone()
    if old and old["capture_sha256"] != fingerprint:
        raise ValueError("Immutable Marketing seal differs from current state")
    if not old:
        c.execute(
            "INSERT INTO marketing_runtime.seals(project_id,episode_id,generation,capture,capture_sha256) VALUES(%s,%s,%s,%s,%s)",
            (project, episode, generation, Jsonb(capture), fingerprint),
        )
    return {
        "trial_id": str(row["id"]),
        "generation": generation,
        "capture_sha256": fingerprint,
        "model_performance": False,
        "grading": "not_performed",
    }


def seal_and_queue_grade(
    c,
    project,
    user,
    episode,
    generation,
    *,
    run_id,
    kind,
    task_group_id,
    task_id,
    model_key,
    repetition,
    plan_id=None,
):
    """Trusted host terminal phase; never a candidate tool or approval endpoint."""
    from anvil.db import uid

    if kind not in {"benchmark_run", "workspace_group"} or type(repetition) is not int:
        raise ValueError("Known persisted execution kind and repetition required")
    sealed = seal(c, project, user, episode, generation)
    c.execute(
        "INSERT INTO marketing_runtime.grading_jobs(id,project_id,run_id,kind,task_group_id,task_id,model_key,repetition,episode_id,generation,plan_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id,episode_id,generation) DO NOTHING",
        (
            uid(),
            project,
            run_id,
            kind,
            task_group_id,
            task_id,
            model_key,
            repetition,
            episode,
            generation,
            plan_id,
        ),
    )
    job = c.execute(
        "SELECT * FROM marketing_runtime.grading_jobs WHERE project_id=%s AND run_id=%s AND episode_id=%s AND generation=%s",
        (project, run_id, episode, generation),
    ).fetchone()
    expected = {
        "kind": kind,
        "task_group_id": str(task_group_id),
        "task_id": task_id,
        "model_key": model_key,
        "repetition": repetition,
        "plan_id": str(plan_id) if plan_id else None,
    }
    if not job or any(
        (str(job[key]) if job[key] is not None else None)
        != (str(value) if value is not None else None)
        for key, value in expected.items()
    ):
        raise ValueError("Immutable campaign grading binding differs")
    return sealed | {"grading": "queued_not_scored", "model_requests": 0}


def reset(c, project, user, episode, generation):
    row, controller = locked(c, project, user, episode, generation, allow_sealed=True)
    controller.reset()
    controller.trial_id = str(row["id"])
    save(c, row, controller)
    return {"trial_id": str(row["id"]), "generation": controller.generation, "reset": True}
