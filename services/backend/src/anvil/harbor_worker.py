"""Dedicated Docker-host adapter: synthetic checks and explicitly admitted mediated agents.

Provider calls stay in the bounded server gateway; Harbor never receives provider keys.
The normal app/worker containers receive neither Docker socket nor this opt-in process.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from anvil import artifacts, auth, domain
from anvil.config import ROOT
from anvil.db import Jsonb, audit, one, project_fence, transaction
from anvil.harbor_package import HARBOR_VERSION, apply_check_overlay, unpack


def argv(executable, task_dir, result_dir, candidate, model=None):
    if candidate not in ("reference", "empty_output", "constraint_failure", "agent"):
        raise ValueError("Unmetered agent execution is blocked")
    if candidate == "agent" and not model:
        raise ValueError("Exact model and guarded gateway required")
    result = [
        str(executable),
        "run",
        "--path",
        str(task_dir),
        "--agent",
        "anvil_harbor.agent:StructuredAgent"
        if candidate == "agent"
        else "nop"
        if candidate == "empty_output"
        else "oracle",
        "--env",
        "docker",
        "--n-concurrent",
        "1",
        "--n-attempts",
        "1",
        "--max-retries",
        "0",
        "--jobs-dir",
        str(result_dir),
        "--job-name",
        "check",
    ]
    if candidate == "agent":
        result += ["--model", model, "--agent-timeout-multiplier", "2"]
    return result


def child_environment(home):
    # Explicit allowlist: no database URL, provider key, cloud identity or parent HOME.
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
        "HOME": str(home),
        "HARBOR_TELEMETRY": "0",
        "LITELLM_LOCAL_MODEL_COST_MAP": "true",
        "PYTHONUNBUFFERED": "1",
    }
    # Discover the installed Compose plugin without inheriting Docker login credentials.
    docker = shutil.which("docker")
    plugin_dir = Path(docker).resolve().parent.parent / "cli-plugins" if docker else None
    config_dir = home / "docker-config"
    config_dir.mkdir(mode=0o700, exist_ok=True)
    config = (
        {"cliPluginsExtraDirs": [str(plugin_dir)]} if plugin_dir and plugin_dir.is_dir() else {}
    )
    (config_dir / "config.json").write_text(json.dumps(config))
    env["DOCKER_CONFIG"] = str(config_dir)
    docker_host = os.environ.get("ANVIL_HARBOR_DOCKER_HOST")
    if docker_host:
        if not docker_host.startswith("unix://"):
            raise RuntimeError("Docker host must be a local Unix socket")
        env["DOCKER_HOST"] = docker_host
    return env


@contextmanager
def scoped(job, user):
    with transaction(job["project_id"], user) as c:
        project_fence(c, job["project_id"])
        yield c


def lease(c, job):
    if not one(
        c,
        "SELECT 1 FROM anvil.jobs WHERE id=%s AND lease_token=%s AND status='leased' AND lease_until>now() FOR UPDATE",
        (job["id"], job["lease_token"]),
    ):
        raise RuntimeError("lease_lost")


def authorized(c, job, user):
    roles = auth.project_roles(c, job["project_id"], user)
    auth.require(roles, "admin", "rl-engineer", "researcher", "product-owner")
    row = one(c, "SELECT * FROM anvil.harbor_checks WHERE id=%s FOR UPDATE", (job["target_id"],))
    if not row:
        raise RuntimeError("check_missing")
    workspace_plan = (
        one(c, "SELECT config FROM anvil.harbor_agent_plans WHERE id=%s", (row["agent_plan_id"],))
        if row["agent_plan_id"]
        else None
    )
    if not workspace_plan or not workspace_plan["config"].get("workspace_execution_group"):
        approval = one(
            c, "SELECT * FROM anvil.harbor_approvals WHERE package_id=%s", (row["package_id"],)
        )
        if not approval or str(approval["approved_by"]) not in domain.administrators(
            c, job["project_id"]
        ):
            raise RuntimeError("approval_revoked")
    if row["candidate"] == "agent":
        from anvil.harbor_agents import plan, readiness

        ready = readiness(c, plan(c, row["agent_plan_id"]))
        if not ready["ready"]:
            raise RuntimeError("live_agent_gates_revoked")
    return row


def finish(job, user, state, result=None, error=None, live=False):
    with transaction(job["project_id"], worker=True) as c:
        project_fence(c, job["project_id"])
        lease(c, job)
        changed = one(
            c,
            "UPDATE anvil.harbor_checks SET state=%s,result=%s,error_code=%s,finished_at=now() WHERE id=%s AND state IN ('queued','running') RETURNING id",
            (state, Jsonb(result) if result else None, error, job["target_id"]),
        )
        if not changed:
            c.execute(
                "UPDATE anvil.jobs SET status='cancelled',error_code='already_terminal' WHERE id=%s",
                (job["id"],),
            )
            audit(c, job["project_id"], user, "harbor.terminal_result_preserved", job["target_id"])
            return
        c.execute(
            "UPDATE anvil.jobs SET status=%s,error_code=%s WHERE id=%s",
            (
                "succeeded"
                if state == "succeeded"
                else "cancelled"
                if state == "cancelled"
                else "failed",
                error,
                job["id"],
            ),
        )
        audit(
            c,
            job["project_id"],
            user,
            "harbor.check_" + state,
            job["target_id"],
            {
                "error_code": error,
                "origin": (result or {}).get("origin")
                or (
                    "provider_dispatch_attempt_unverified"
                    if live
                    else "synthetic_software_verification"
                ),
                "model_performance": bool(result and result.get("model_performance")),
            },
        )


def stop_process(process):
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def cleanup_sandboxes(workspace, env):
    """Only exact Compose labels from this check's generated trial directories; no volumes."""
    results = workspace / "results/check"
    if not results.exists():
        return
    for trial in results.iterdir():
        if not trial.is_dir() or not re.fullmatch(r"task__[A-Za-z0-9]{7,16}", trial.name):
            continue
        label = "com.docker.compose.project=" + trial.name.lower() + "__env"
        for resource, listing in (
            ("container", ["ps", "-aq"]),
            ("network", ["network", "ls", "-q"]),
        ):
            found = subprocess.run(
                ["docker", *listing, "--filter", "label=" + label],
                env=env,
                capture_output=True,
                timeout=20,
                check=True,
            )
            identifiers = found.stdout.decode().split()
            if any(not re.fullmatch(r"[a-f0-9]{12,64}", identifier) for identifier in identifiers):
                raise RuntimeError("cleanup_required")
            if identifiers:
                command = (
                    ["docker", "rm", "-f", *identifiers]
                    if resource == "container"
                    else ["docker", "network", "rm", *identifiers]
                )
                subprocess.run(command, env=env, capture_output=True, timeout=30, check=True)


def linux_process_identity(pid, proc_root=Path("/proc")):
    try:
        stat = (proc_root / str(pid) / "stat").read_text()
        boot = (proc_root / "sys/kernel/random/boot_id").read_text().strip()
    except FileNotFoundError:
        return ""
    # comm can contain whitespace and parentheses; fields after the final ') '
    # begin at field3. Field22 is the process start tick, stable across exec.
    fields = stat.rpartition(") ")[2].split()
    if len(fields) < 20 or not fields[19].isdigit() or not boot:
        raise RuntimeError("process_identity_unavailable")
    return "linux:" + boot + ":" + str(pid) + ":" + fields[19]


def process_identity(pid):
    if Path("/proc/self/stat").is_file():
        return linux_process_identity(pid)
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart=", "-o", "command="], capture_output=True, timeout=5
    )
    return result.stdout.decode().strip() if result.returncode == 0 else ""


def recover_child(workspace):
    path = workspace / "process.json"
    if not path.exists():
        return
    stored = json.loads(path.read_text())
    pid = stored["pid"]
    if type(pid) is not int or pid <= 1 or not stored["identity"]:
        raise RuntimeError("cleanup_required")
    if process_identity(pid) == stored["identity"]:
        os.killpg(pid, signal.SIGINT)
        for _ in range(15):
            if process_identity(pid) != stored["identity"]:
                return
            time.sleep(1)
        if process_identity(pid) == stored["identity"]:
            os.killpg(pid, signal.SIGKILL)


def check_workspace(check_id):
    return Path(os.environ.get("ANVIL_HARBOR_WORK_ROOT", ROOT / ".local/harbor-checks")) / str(
        check_id
    )


def process(job):
    with transaction(job["project_id"], worker=True) as c:
        owner = one(
            c, "SELECT created_by FROM anvil.harbor_checks WHERE id=%s", (job["target_id"],)
        )
    if not owner:
        raise RuntimeError("check_missing")
    user = owner["created_by"]
    child = None
    gateway = None
    model = None
    run_timeout = 300
    workspace = check_workspace(job["target_id"])
    try:
        with scoped(job, user) as c:
            lease(c, job)
            row = authorized(c, job, user)
            if row["state"] not in ("queued", "running"):
                c.execute("UPDATE anvil.jobs SET status='cancelled' WHERE id=%s", (job["id"],))
                return
            if row["invocation_count"]:
                if workspace.exists():
                    recover_child(workspace)
                    cleanup_sandboxes(workspace, child_environment(workspace))
                # Durable dispatch has happened. Never retry an ambiguous process after a crash.
                c.execute(
                    "UPDATE anvil.harbor_checks SET state='execution_unknown',error_code='dispatch_outcome_unknown',finished_at=now() WHERE id=%s",
                    (row["id"],),
                )
                c.execute(
                    "UPDATE anvil.jobs SET status='failed',error_code='dispatch_outcome_unknown' WHERE id=%s",
                    (job["id"],),
                )
                audit(c, job["project_id"], user, "harbor.execution_unknown", row["id"])
                return
            if row["cancel_requested"]:
                c.execute(
                    "UPDATE anvil.harbor_checks SET state='cancelled',finished_at=now() WHERE id=%s",
                    (row["id"],),
                )
                c.execute("UPDATE anvil.jobs SET status='cancelled' WHERE id=%s", (job["id"],))
                return
            package = one(
                c, "SELECT * FROM anvil.harbor_packages WHERE id=%s", (row["package_id"],)
            )
            archive = artifacts.read(c, package["package_artifact_id"])
            executable = Path(
                os.environ.get("ANVIL_HARBOR_EXECUTABLE", ROOT / ".local/harbor-venv/bin/harbor")
            )
            if not executable.is_file():
                raise RuntimeError("harbor_runtime_unavailable")
        if package["manifest"].get("binding") == "mcp-tool-agent-v1":
            from anvil.import_execution import process as process_tool_trial

            process_tool_trial(job, user, row, package)
            return
        if os.environ.get("ANVIL_ENV") == "cloud":
            # Cloud QA uses the preloaded, no-build/no-pull native custody path.
            # Never fall through to stock Harbor's implicit image build/cleanup.
            from anvil.environment_structured_agent import process as process_structured

            process_structured(job, user, row, package)
            return
        workspace.mkdir(parents=True, exist_ok=False, mode=0o700)
        task_dir, results = workspace / "task", workspace / "results"
        unpack(archive, task_dir, package["package_sha256"])
        overlay = apply_check_overlay(task_dir, row["candidate"])
        env = child_environment(workspace)
        if row["candidate"] == "agent":
            from anvil.harbor_agents import Gateway, plan

            with scoped(job, user) as c:
                record = plan(c, row["agent_plan_id"])
                model = record["config"]["model"]
                run_timeout = 180 + 120 * record["config"]["max_calls"]
                if record["config"].get("workspace_execution_group"):
                    run_timeout = record["config"]["episode_timeout_seconds"]
            gateway = Gateway(job["project_id"], user, row["agent_plan_id"])
            env["ANVIL_HARBOR_GATEWAY_SOCKET"] = gateway.path
            env["ANVIL_HARBOR_GATEWAY_TOKEN"] = gateway.token
            env["PYTHONPATH"] = os.environ.get(
                "ANVIL_HARBOR_AGENT_PATH", str(ROOT / "services/harbor/src")
            )
        version = subprocess.run(
            [str(executable), "--version"], env=env, capture_output=True, timeout=15
        )
        if version.returncode or HARBOR_VERSION not in version.stdout.decode():
            raise RuntimeError("harbor_version_mismatch")
        with scoped(job, user) as c:
            lease(c, job)
            current = authorized(c, job, user)
            if current["cancel_requested"]:
                raise RuntimeError("cancelled")
            c.execute(
                "UPDATE anvil.harbor_checks SET state='running',started_at=now(),invocation_count=1 WHERE id=%s",
                (row["id"],),
            )
            audit(
                c,
                job["project_id"],
                user,
                "harbor.dispatch_started",
                row["id"],
                {"harbor_version": HARBOR_VERSION},
            )
        started = time.monotonic()
        with (workspace / "runtime.log").open("wb") as log:
            child = subprocess.Popen(
                argv(executable, task_dir, results, row["candidate"], model),
                env=env,
                cwd=workspace,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            (workspace / "process.json").write_text(
                json.dumps({"pid": child.pid, "identity": process_identity(child.pid)})
            )
            while child.poll() is None:
                time.sleep(1)
                with scoped(job, user) as c:
                    lease(c, job)
                    current = authorized(c, job, user)
                    if current["cancel_requested"]:
                        raise RuntimeError("cancelled")
                    c.execute(
                        "UPDATE anvil.jobs SET lease_until=now()+interval '60 seconds' WHERE id=%s AND lease_token=%s",
                        (job["id"], job["lease_token"]),
                    )
                if time.monotonic() - started > run_timeout:
                    raise RuntimeError("check_timeout")
                if (workspace / "runtime.log").stat().st_size > 2 * 1024 * 1024:
                    raise RuntimeError("log_limit")
        if child.returncode:
            raise RuntimeError("harbor_failed")
        files = sorted(results.rglob("diagnostics.json"))
        if (
            not files
            or len(files) > len(package["manifest"]["stage_order"])
            or any(p.stat().st_size > 65536 for p in files)
        ):
            raise RuntimeError("verifier_evidence_missing")
        diagnostics = [json.loads(p.read_text()) for p in files]
        trials = [p for p in results.rglob("result.json") if p.parent.name != "check"]
        if len(trials) != 1:
            raise RuntimeError("trial_evidence_missing")
        trial = json.loads(trials[0].read_text())
        if trial.get("exception_info") or any(
            s.get("exception_info") for s in trial.get("step_results") or []
        ):
            raise RuntimeError("harbor_trial_failed")
        if package["manifest"]["schema_version"] == "praxis.anvil.task.v2":
            reward = min(d["reward"] for d in diagnostics)
            if len(diagnostics) != len(package["manifest"]["stage_order"]):
                reward = 0.0
            diagnostic = {
                "reward": reward,
                "stages": diagnostics,
                "completed_stages": len(diagnostics),
                "declared_stages": len(package["manifest"]["stage_order"]),
            }
        else:
            diagnostic = diagnostics[0]
        if (trial.get("verifier_result") or {}).get("rewards", {}).get("reward") != diagnostic[
            "reward"
        ]:
            raise RuntimeError("verifier_evidence_mismatch")
        evidence = []
        with scoped(job, user) as c:
            lease(c, job)
            mock_execution = bool(
                row.get("agent_plan_id")
                and one(
                    c,
                    "SELECT 1 FROM anvil.harbor_agent_calls WHERE plan_id=%s AND usage->>'dispatch_origin'='sdk_mock' LIMIT 1",
                    (row["agent_plan_id"],),
                )
            )
            for path in [
                *files,
                *sorted(results.rglob("output.json")),
                *sorted(results.rglob("output.txt")),
            ]:
                if path.is_symlink() or path.stat().st_size > 65536:
                    raise RuntimeError("verifier_evidence_missing")
                aid = artifacts.store(
                    c,
                    job["project_id"],
                    path.read_bytes(),
                    "internal",
                    mime="text/plain" if path.name == "output.txt" else "application/json",
                    origin="adi_executed"
                    if row["candidate"] == "agent" and not mock_execution
                    else "illustrative",
                )
                evidence.append(
                    {
                        "artifact_id": str(aid),
                        "kind": path.name,
                        "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                    }
                )
        result = {
            "origin": "live_model_unreviewed"
            if row["candidate"] == "agent"
            else "synthetic_software_verification",
            "model_performance": row["candidate"] == "agent",
            "mock_execution": mock_execution,
            "model": model,
            "agent_plan_id": str(row["agent_plan_id"]) if row["agent_plan_id"] else None,
            "harbor_version": HARBOR_VERSION,
            "package_sha256": package["package_sha256"],
            "candidate": row["candidate"],
            "execution_overlay": overlay,
            "diagnostics": diagnostic,
            "evidence": evidence,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "trajectory": "Observable per-stage JSON outputs only; no private reasoning inferred"
            if row["candidate"] == "agent"
            else "Reference script or no-op only; no model trajectory generated",
            "analysis": "Automated rubric results; human scientific review pending"
            if row["candidate"] == "agent"
            else "Software feasibility check; no model capability conclusion",
        }
        if mock_execution:
            result.update(
                origin="native_sdk_mock_verification",
                model_performance=False,
                analysis="Mocked SDK and Harbor software verification; no real model performance measured",
            )
        finish(job, user, "succeeded", result, live=row["candidate"] == "agent")
    except Exception as exc:
        if child and child.poll() is None:
            stop_process(child)
        if child:
            try:
                cleanup_sandboxes(workspace, child_environment(workspace))
            except (OSError, RuntimeError, subprocess.SubprocessError):
                finish(job, user, "execution_unknown", error="cleanup_required")
                return
        code = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        if code not in {
            "cancelled",
            "approval_revoked",
            "check_missing",
            "harbor_runtime_unavailable",
            "harbor_version_mismatch",
            "check_timeout",
            "log_limit",
            "harbor_failed",
            "verifier_evidence_missing",
            "verifier_evidence_mismatch",
            "trial_evidence_missing",
            "harbor_trial_failed",
            "live_agent_gates_revoked",
        }:
            code = "harbor_operational_failure"
        live = bool("row" in locals() and row["candidate"] == "agent")
        pending = None
        if live:
            with transaction(job["project_id"], worker=True) as c:
                pending = one(
                    c,
                    "SELECT 1 FROM anvil.harbor_agent_calls WHERE plan_id=%s AND status IN ('dispatching','execution_unknown') LIMIT 1",
                    (row["agent_plan_id"],),
                )
        state = "execution_unknown" if pending else "cancelled" if code == "cancelled" else "failed"
        finish(job, user, state, error=code, live=live)
    finally:
        if gateway:
            gateway.close()


def tick():
    from anvil.import_worker import tick as import_tick

    if import_tick():
        return True
    with transaction(worker=True) as c:
        job = one(c, "SELECT * FROM anvil.claim_harbor_job()")
    if not job:
        return False
    process(job)
    return True


def main():
    if os.environ.get("ANVIL_HARBOR_WORKER_ENABLED") != "synthetic-checks-only":
        raise RuntimeError("Explicit dedicated Docker-host software-check opt-in required")
    while True:
        if not tick():
            time.sleep(2)


if __name__ == "__main__":
    main()
