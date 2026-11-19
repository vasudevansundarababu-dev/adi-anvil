"""Trusted scheduler controller: OpenEnv tools and lease RPC, no provider keys.

Separate process/connection from both API and private grader. No paid request
retry, lease reclaim, predetermined investigator or private expected answer.
"""

import os
from time import monotonic

from anvil.db import Jsonb
from anvil.golden_kyc_deadline_transport import forward
from anvil.golden_kyc_paid_session import actions, tool_turn
from anvil.marketing_native_wire_bounds import remaining as original_remaining
from anvil.praxis_generic_contract import digest


def process_one(
    connections,
    *,
    dispatch=forward,
    environment=None,
    harness=None,
    checkpointer=None,
    tools_factory=None,
):
    controller_deadline=monotonic()+600
    if environment is None:
        from anvil.golden_kyc_openenv import GoldenEnvironment

        environment = GoldenEnvironment
    claim_started=monotonic()
    with connections() as c:
        job = c.execute("SELECT banking.claim_paid_agent_job() AS job").fetchone()["job"]
    if job is None:
        return None
    from anvil.golden_kyc_deadline_database import SchedulerConnections

    if type(connections) is SchedulerConnections:
        from anvil.golden_kyc_episode_clock import deadline as episode_deadline

        controller_deadline=episode_deadline(job.get("episode_cutoff"),request_started=claim_started,original_cutoff=controller_deadline)
        connections=connections.for_actor(job["actor_id"],absolute_deadline=controller_deadline)
        controller_deadline=connections.absolute_deadline
    elif dispatch is forward:
        raise RuntimeError("Operational KYC controller requires bounded dedicated scheduler connections")
    try:
        from anvil.golden_phase_checkpoints import execute as execute_phases

        return execute_phases(
            connections,
            job,
            lambda: execute(
                connections,
                job,
                dispatch=dispatch,
                environment=environment,
                harness=harness,
                tools_factory=tools_factory,
                absolute_deadline=controller_deadline,
            ),
            checkpointer=checkpointer,
        )
    except Exception:
        # One status-only finalization attempt is safe after uncertainty: it
        # cannot dispatch or refund. If unavailable, the operator reconciles
        # the expired lease through the separate Admin endpoint.
        try:
            dispatch(
                job,
                job["actor_id"],
                job["plan_id"],
                0,
                operation="finish",
                native={"failure": True},
                absolute_deadline=controller_deadline,
            )
        except Exception:
            pass
        raise


def execute(connections, job, *, dispatch, environment, harness=None, tools_factory=None, absolute_deadline=None):
    started = monotonic()
    deadline=[min(started+600,absolute_deadline) if absolute_deadline is not None else started+600]
    original_dispatch=dispatch

    def dispatch(*args,**kwargs):
        left=int(original_remaining(deadline[0]))
        if left<1:
            raise TimeoutError("Original KYC controller cutoff elapsed")
        kwargs['remaining_seconds']=min(kwargs.get('remaining_seconds',120),left)
        kwargs['absolute_deadline']=deadline[0]
        return original_dispatch(*args,**kwargs)

    user, plan = job["actor_id"], job["plan_id"]
    prepared = dispatch(job, user, plan, 0, operation="prepare")
    if prepared.get("mode") != "golden-native":
        raise RuntimeError("golden_native_admission_required")
    native = prepared["native_binding"]
    deadline[0]=min(deadline[0],started+prepared["episode_timeout_seconds"])
    original_remaining(deadline[0])
    from anvil.golden_kyc_deadline_database import SchedulerConnections

    if type(connections) is SchedulerConnections:
        connections=connections.for_actor(job["actor_id"],absolute_deadline=deadline[0])
    elif original_dispatch is forward:
        raise RuntimeError("Operational KYC episode requires bounded dedicated scheduler connections")
    from anvil.golden_kyc_runtime import create_trial

    with connections() as c:
        trial = create_trial(
            c,
            job["project_id"],
            user,
            native["pack_id"],
            native["application_id"],
            prepared["model_label"],
            prepared["repetition"],
        )
    episode = environment(connections, job["project_id"], user, trial["trial_id"])
    episode.policy_deadline = deadline[0]
    try:
        episode.reset()
        with connections() as c:
            if not c.execute(
                "SELECT banking.bind_paid_agent_trial(%s,%s,%s,%s) AS ok",
                (job["id"], job["lease_token"], plan, trial["trial_id"]),
            ).fetchone()["ok"]:
                raise RuntimeError("golden_paid_trial_binding_denied")
        def candidate(native_guard):
            nonlocal tools_factory
            if tools_factory is None:
                from anvil.golden_mcp_client import McpEpisode

                tools_factory = McpEpisode
            scope = {
                "schema_version": "anvil.golden-mcp-scope.v1",
                "project_id": str(job["project_id"]),
                "trial_id": str(trial["trial_id"]),
                "generation": episode.credentials["generation"],
                "resolved_task_id": native["resolved_task_id"],
                "application_id": native["application_id"],
                "runtime_sha256": native["runtime_sha256"],
                "case_assignment_sha256": digest(native.get("case_assignment")),
            }
            active_stage = [0]

            def tool_authority():
                if not native_guard():
                    return False
                try:
                    return dispatch(job, user, plan, active_stage[0], operation="readiness") is True
                except Exception:
                    return False

            with tools_factory(episode, scope, tool_authority) as tool_episode:
                return candidate_turns(native_guard, tool_episode, active_stage)

        def candidate_turns(native_guard, tool_episode, active_stage):
            observation, turns = {"actions": [], "closed": False}, 0
            for stage in range(prepared["max_calls"]):
                active_stage[0] = stage
                if not native_guard():
                    raise RuntimeError("golden_native_coordinator_lost_no_retry")
                remaining = int(prepared["episode_timeout_seconds"] - (monotonic() - started))
                if remaining < prepared["request_timeout_seconds"]:
                    break
                with connections() as c:
                    if not c.execute(
                        "SELECT banking.heartbeat_paid_agent_job(%s,%s) AS ok",
                        (job["id"], job["lease_token"]),
                    ).fetchone()["ok"]:
                        raise RuntimeError("golden_paid_lease_lost")
                text = dispatch(
                    job,
                    user,
                    plan,
                    stage,
                    remaining_seconds=min(remaining, prepared["request_timeout_seconds"]),
                )
                if not native_guard():
                    raise RuntimeError("golden_native_coordinator_lost_after_response_no_retry")
                parsed = actions(text)
                observation = tool_turn(tool_episode, text)
                if hasattr(tool_episode, "public_receipt"):
                    observation["mcp"] = tool_episode.public_receipt()
                with connections() as c:
                    if not c.execute(
                        "SELECT banking.record_paid_agent_turn(%s,%s,%s,%s,%s,%s,%s,%s) AS ok",
                        (
                            job["id"],
                            job["lease_token"],
                            plan,
                            stage,
                            text,
                            digest({"actions": parsed}),
                            Jsonb(observation),
                            digest(observation),
                        ),
                    ).fetchone()["ok"]:
                        raise RuntimeError("golden_paid_turn_capture_denied")
                turns += 1
                if observation["closed"]:
                    break
            return observation, {
                "project_id": str(job["project_id"]),
                "job_id": str(job["id"]),
                "plan_id": str(plan),
                "trial_id": str(trial["trial_id"]),
                "generation": episode.credentials["generation"],
                "turns": turns,
                "closed": observation["closed"],
                "last_observation_sha256": digest(observation),
            }

        public = {"task": prepared["public_actor"], "application_id": native["application_id"]}
        binding = {
            "project_id": str(job["project_id"]),
            "job_id": str(job["id"]),
            "plan_id": str(plan),
            "trial_id": str(trial["trial_id"]),
            "lease_sha256": digest(str(job["lease_token"])),
            "generation": episode.credentials["generation"],
            "input_sha256": digest(public),
        }
        if harness is None:
            from anvil.golden_kyc_worker_bridge import KycWorkerSession
            from anvil.golden_native_bridge import submit_v2

            def harness(binding, public, callback, seconds):
                session = KycWorkerSession(callback, digest(binding), digest(public), digest(prepared), deadline[0])
                return submit_v2(
                    os.environ["ANVIL_NATIVE_BRIDGE_ROOT"],
                    binding,
                    public,
                    session,
                    seconds=seconds,
                )

        framework = harness(binding, public, candidate, prepared["episode_timeout_seconds"])
        return dispatch(
            job,
            user,
            plan,
            0,
            operation="finish",
            native={"schema_version": "anvil.golden-paid-finish.v2", "framework": framework},
        )
    finally:
        # On ambiguous dispatch, preserve lease/state/reservation. The operator
        # reconciles the ledger; this controller never invokes a second request.
        episode.close()
