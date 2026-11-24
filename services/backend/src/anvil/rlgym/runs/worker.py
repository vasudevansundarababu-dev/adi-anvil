"""The episode runner and scorer loop (ARCHITECTURE 7.3, local form).

One background thread in the API process (started only with RLGYM_V2=1):
  1. requeue episodes whose lease expired (attempt recorded as lease_lost; errored after the retry limit);
  2. prepare admitted runs: build the environment image from the Studio recipe if needed, start the run's instance;
  3. lease one queued episode (FOR UPDATE SKIP LOCKED), run it in the instance, seal the evidence bundle, score it;
  4. finish runs with no work left and stop their instance.
Infrastructure errors are retried up to the run's limit; a timeout is a result, not retried. The agent is the
controlled mock; no provider is called and no automatic inference retry exists.
"""

import datetime as dt
import hashlib
import json
import logging
import os
import socket
import threading
import time
import uuid

from psycopg.types.json import Jsonb

from anvil.rlgym.common import GymError, emit, set_scope, system_scope
from anvil.rlgym.runs import aliasing, clauses, images, instructions, openenv
from anvil.rlgym.scoring import service as scoring
from anvil.rlgym.systems import mock_provider

# E-006: read results an attack placed "in a tool result" can ride on (the first one the agent receives).
INJECT_TOOLS = (
    "document.read",
    "application.read",
    "documents.list",
    "parties.list",
    "information.read",
    "search.read",
    "specialist.read",
    "operation.read",
    "policy.read",
)


def attach_attack(obs, tool, step, inject, already):
    """E-006: the observation the agent receives. An attack placed "in a tool result" is added, once, to the first
    successful read result (as `output.note`); the environment's own record of the result is not changed.
    → (observation for the agent, where it was placed or None)."""
    if (
        not inject
        or already
        or tool not in INJECT_TOOLS
        or not obs.get("ok")
        or not isinstance(obs.get("output"), dict)
    ):
        return obs, None
    return {**obs, "output": {**obs["output"], "note": inject["text"]}}, {
        "step": step,
        "tool": tool,
        "field": "output.note",
    }


log = logging.getLogger("anvil.rlgym.runner")
OWNER = f"runner@{socket.gethostname()}:{os.getpid()}"
MAX_STEPS = 80
_started = False
_lock = threading.Lock()


def _gateway():
    """The live model gateway (tests replace this with a fake transport). Refuses without the live flag."""
    from anvil.rlgym.live.gateway import Gateway

    return Gateway()


GATEWAY_FACTORY = _gateway


def _live_ok():
    """Only a process with the live flag (or a test with a fake gateway) takes live runs; others leave them queued."""
    from anvil.rlgym.live.gateway import live_enabled

    return live_enabled() or GATEWAY_FACTORY is not _gateway


def _workspaces():
    """Only workspaces with run work (admitted or running runs, or an instance still up): an idle tick is one query on
    one connection, however many workspaces exist."""
    with system_scope() as c:
        return [
            r["workspaces_with_work"]
            for r in c.execute("SELECT runs.workspaces_with_work()").fetchall()
        ]


def recover_leases(ws):
    with system_scope(ws) as c:
        for e in c.execute(
            """SELECT e.*, r.infra_retries FROM runs.episodes e JOIN runs.runs r ON r.id=e.run_id
               WHERE e.workspace_id=%s AND e.state='running' AND e.lease_until < now() FOR UPDATE OF e SKIP LOCKED""",
            (ws,),
        ).fetchall():
            c.execute(
                "UPDATE runs.episode_attempts SET ended_at=now(), outcome='lease_lost', note='runner lost its lease' WHERE episode_id=%s AND try=%s AND outcome IS NULL",
                (e["id"], e["tries"]),
            )
            again = e["tries"] <= e["infra_retries"]
            c.execute(
                "UPDATE runs.episodes SET state=%s, lease_owner=NULL, lease_until=NULL, last_error='runner lost its lease' WHERE id=%s",
                ("queued" if again else "errored", e["id"]),
            )


def prepare_runs(ws):
    """Claim one admitted run at a time (row lock held while its image is built and its instance started), so two
    runner processes never start the same run twice."""
    while True:
        with system_scope(ws) as c:
            run = c.execute(
                """SELECT r.*, m.manifest FROM runs.runs r JOIN runs.run_manifests m ON m.run_id=r.id
                   WHERE r.workspace_id=%s AND r.state='admitted' AND r.cancel_requested_at IS NULL
                     AND (r.execution_mode <> 'live' OR %s)
                   ORDER BY r.created_at LIMIT 1 FOR UPDATE OF r SKIP LOCKED""",
                (ws, _live_ok()),
            ).fetchone()
            if not run:
                return
            vid = run["manifest"]["environment"]["version_id"]
            env = c.execute(
                "SELECT * FROM catalog.environment_versions WHERE id=%s", (vid,)
            ).fetchone()
            driver = openenv.KIND if openenv.is_openenv(env) else "bridge"
            try:
                if driver == openenv.KIND:
                    if env["state"] != "qualified":
                        raise GymError(
                            "CONFLICT", f"{vid} is {env['state']}; only qualified versions run"
                        )
                    image = openenv.resolve(c, vid, env)
                    container, _ready = openenv.start_instance(
                        run["id"], env, image["local_image_id"]
                    )
                else:
                    image = images.build(c, vid)
                    container = images.start_instance(run["id"], image["local_image_id"])
            except (GymError, RuntimeError, OSError) as exc:
                message = exc.message if isinstance(exc, GymError) else str(exc)
                if isinstance(exc, GymError) and exc.details:
                    message += " " + json.dumps(exc.details, sort_keys=True, default=str)
                log.warning("run %s could not start: %s", run["id"], message)
                c.rollback()
                set_scope(c, ws)
                if isinstance(exc, GymError) and exc.code == "HASH_MISMATCH":
                    emit(
                        c,
                        ws,
                        "environment.image_mismatch",
                        vid,
                        {
                            "version_id": vid,
                            "run_id": run["id"],
                            "reason": exc.message,
                            **exc.details,
                        },
                    )
                c.execute(
                    "UPDATE runs.episodes SET state='errored', last_error=%s WHERE run_id=%s AND state='queued'",
                    (f"environment not started: {message}"[:500], run["id"]),
                )
                c.execute(
                    "UPDATE runs.runs SET state='failed', finished_at=now() WHERE id=%s",
                    (run["id"],),
                )
                emit(c, ws, "run.failed", run["id"], {"run_id": run["id"], "reason": message[:300]})
                continue
            c.execute(
                "INSERT INTO runs.instances(id,workspace_id,run_id,environment_version_id,local_image_id,container,idle_timeout_s) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    f"inst-{uuid.uuid4().hex[:10]}",
                    ws,
                    run["id"],
                    vid,
                    image["local_image_id"],
                    container,
                    900,
                ),
            )
            c.execute(
                "UPDATE runs.runs SET state='running', started_at=now() WHERE id=%s", (run["id"],)
            )
            emit(
                c,
                ws,
                "run.started",
                run["id"],
                {
                    "run_id": run["id"],
                    "image": image["image_tag"],
                    "container": container,
                    "driver": driver,
                },
            )


def lease(ws):
    with system_scope(ws) as c:
        e = c.execute(
            # One running episode per run: a run's instance is one environment (Studio's simulator holds one
            # episode at a time), so two runner processes must never step it at once. The run row is locked
            # while an episode is leased; another process skips the run until this lease is visible.
            """SELECT e.* FROM runs.episodes e JOIN runs.runs r ON r.id=e.run_id
               WHERE e.workspace_id=%s AND e.state='queued' AND r.state='running' AND r.cancel_requested_at IS NULL
                 AND (r.execution_mode <> 'live' OR %s)
                 AND NOT EXISTS (SELECT 1 FROM runs.episodes x WHERE x.run_id=e.run_id AND x.state='running')
               ORDER BY e.queued_at, e.id LIMIT 1 FOR UPDATE OF e, r SKIP LOCKED""",
            (ws, _live_ok()),
        ).fetchone()
        if not e:
            return None
        run = c.execute("SELECT * FROM runs.runs WHERE id=%s", (e["run_id"],)).fetchone()
        tries = e["tries"] + 1
        c.execute(
            "UPDATE runs.episodes SET state='running', tries=%s, lease_owner=%s, lease_until=now() + make_interval(secs => %s) WHERE id=%s",
            (tries, OWNER, run["episode_timeout_s"] + 60, e["id"]),
        )
        c.execute(
            "INSERT INTO runs.episode_attempts(episode_id,workspace_id,try,started_at) VALUES(%s,%s,%s,now())",
            (e["id"], ws, tries),
        )
        return {**e, "tries": tries}


def _context(ws, episode):
    with system_scope(ws) as c:
        run = c.execute("SELECT * FROM runs.runs WHERE id=%s", (episode["run_id"],)).fetchone()
        manifest = c.execute(
            "SELECT manifest, manifest_sha256 FROM runs.run_manifests WHERE run_id=%s",
            (episode["run_id"],),
        ).fetchone()
        instance = c.execute(
            "SELECT * FROM runs.instances WHERE run_id=%s AND stopped_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (episode["run_id"],),
        ).fetchone()
        if instance:
            env = c.execute(
                "SELECT * FROM catalog.environment_versions WHERE id=%s",
                (manifest["manifest"]["environment"]["version_id"],),
            ).fetchone()
            instance = {**instance, "env": env}
        actor = c.execute(
            """SELECT p.content FROM projects.task_imports t JOIN projects.task_payloads p
               ON p.workspace_id=t.workspace_id AND p.package_sha256=t.package_sha256 AND p.part='actor' WHERE t.id=%s""",
            (episode["task_import_id"],),
        ).fetchone()
    return run, manifest, instance, actor["content"] if actor else None


def execute(episode, run, manifest, instance, actor, session_factory=None):
    """Run one episode and return the evidence bundle (not yet sealed). The policy sees the task's instructions (built
    from the actor payload only, D-007) and tool results; the run's reference answers are never loaded here."""
    m = manifest["manifest"]
    # No instructions, no episode: never a generic fallback (raises TASK_NO_INSTRUCTIONS before any container call).
    # E-002: the task's clause versions as frozen in the run manifest (empty for tasks without clauses).
    frozen = next(
        (
            t
            for t in m.get("tasks") or []
            if t.get("task_id") == episode["task_id"]
            and t.get("revision") == episode["task_revision"]
        ),
        {},
    )
    selected = frozen.get("clauses") or []
    instr = instructions.build(actor, selected)
    model = next(x for x in m["models"] if x["system_id"] == episode["system_id"])
    offered = set((actor or {}).get("tools") or [])
    prompt = None
    inject = None
    if episode["kind"] == "safety":
        prompt = next(
            p for p in m["trust_and_safety"]["prompts"] if p["id"] == episode["ts_prompt_id"]
        )
        inject = {"placement": m["trust_and_safety"]["placement"], "text": prompt["text"]}
    started = time.monotonic()
    deadline = started + run["episode_timeout_s"]
    on_openenv = bool(instance) and openenv.is_openenv(instance.get("env"))
    if session_factory:
        session = session_factory()
    elif on_openenv:
        session = openenv.OpenEnvSession(
            instance["container"], openenv.recipe(instance["env"]), deadline
        )
    else:
        session = images.EnvSession.docker(instance["container"], deadline)
    transcript, events, final = [], [], None
    agent_log = {}
    aliaser = None
    try:
        reset = session.request({"op": "reset", "case_id": episode["case_id"], "inject": inject})
        if not reset.get("ok"):
            raise RuntimeError(f"environment reset failed: {reset.get('error')}")
        # Verifier blocks (D21): the environment's declared collections at the start and the end of the episode.
        # Read by the runner only; the snapshot is not an operation, so the agent never sees it.
        snapshots = None
        if (instance or {}).get("env") and instance["env"].get("schema"):
            snapshots = {
                "start": session.request({"op": "snapshot"}).get("collections"),
                "end": None,
            }
        # Owner decision 24 Nov 2026 (D-039): on Studio's OpenEnv images the agent sees opaque IDs, never the case,
        # application, party or document IDs (they name the edge case). Arguments are mapped back before the call.
        aliaser = (
            aliasing.Aliaser(episode["case_id"], (snapshots or {}).get("start"))
            if on_openenv and m.get("ids_aliased")
            else None
        )

        def shown(value):
            return aliaser.out(value) if aliaser else value

        # E-006: on OpenEnv an attack placed "in a tool result" rides on the first read result the agent receives.
        tool_inject = (
            inject if on_openenv and inject and inject.get("placement") == "tool_result" else None
        )
        injected_at = None

        def real(value):
            return aliaser.back(value) if aliaser else value

        live_caller = None
        if model.get("live"):
            from anvil.rlgym.live.agent import LiveCaller, live_agent

            live_caller = LiveCaller(
                GATEWAY_FACTORY(), episode["workspace_id"], episode["run_id"], episode["id"], model
            )
            operations = (
                session.request({"op": "operations"}).get("operations")
                if on_openenv
                else sorted(offered)
                or list((instance or {}).get("env", {}).get("operations") or [])
            )
            from anvil.rlgym.live.agent import MAX_OBS_CHARS

            max_obs = int(
                (model["live"].get("params") or {}).get("max_observation_chars") or MAX_OBS_CHARS
            )
            agent_log = {"kind": "live"}
            policy = live_agent(
                live_caller,
                instr["text"],
                operations or [],
                application_id=shown(episode["case_id"]) if on_openenv else None,
                user_message=shown(reset.get("user_message")),
                log=agent_log,
                max_observation_chars=max_obs,
            )
        else:
            agent_log = {
                "kind": "mock",
                "synthetic": True,
                "note": "controlled mock policy: no model messages; actions are in the transcript",
            }
            policy = mock_provider.agent(
                model["model_id"],
                instr["text"],
                # Seeded by what the episode is (not its id), so a repeat run on the same suite is reproducible.
                f"{episode['case_id']}:{episode['task_id']}:{episode['attempt']}:{episode.get('ts_prompt_id')}",
                user_message=shown(reset.get("user_message")),
                # On Studio's own image the task names the application under review (OpenEnv B1).
                world=openenv.KIND if on_openenv else "stub",
                application_id=shown(episode["case_id"]) if on_openenv else None,
            )
        action = next(policy)
        for step in range(1, MAX_STEPS + 1):
            if "final" in action:
                final = real(action["final"])
                transcript.append({"step": step, "final_output": final})
                break
            tool, args = action["tool"], real(action.get("args") or {})
            if offered and tool not in offered:
                obs = {"ok": False, "error": "tool not offered by this task"}
            else:
                obs = session.request({"op": "call", "tool": tool, "args": args})
            entry = {"step": step, "tool": tool, "args": args, "observation": obs}
            agent_obs, at = attach_attack(obs, tool, step, tool_inject, injected_at)
            if at:
                injected_at = at
                entry["injected"] = at
            if live_caller:
                # D-008: how much of this observation the model was shown.
                full = len(json.dumps(obs, default=str))
                entry["observation_chars"] = full
                entry["shown_chars"] = min(full, max_obs)
            transcript.append(entry)
            events.append(
                {
                    "tool": tool,
                    "args": args,
                    "ok": bool(obs.get("ok", False)),
                    "blocked": bool(obs.get("blocked")),
                }
            )
            try:
                action = policy.send(shown(agent_obs))
            except StopIteration:
                break
        state = session.request({"op": "state"})
        end = state.pop("collections", None)  # kept only as the end snapshot, never twice
        if snapshots is not None:
            snapshots["end"] = end
    finally:
        session.close()
    wall_ms = int((time.monotonic() - started) * 1000)
    steps = len(transcript)
    bundle = {
        "schema": "rlgym.sealed-episode.v1",
        # A live model's episode is a real execution (on synthetic cases), labelled apart from mock results.
        "synthetic": not live_caller,
        "live": bool(live_caller),
        "data": "synthetic cases",
        "execution_mode": m["execution_mode"],
        "note": m["note"],
        "run_id": episode["run_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "episode_id": episode["id"],
        "kind": episode["kind"],
        "task": {"task_id": episode["task_id"], "revision": episode["task_revision"]},
        "case_id": episode["case_id"],
        # What the agent was told (D-007): the text built from the actor payload, its source and hash.
        "instructions": instr,
        # The agent saw opaque IDs: the table (real → alias) reconstructs its view; everything else here is real.
        **({"id_aliases": aliaser.record()} if aliaser else {}),
        "system": {
            k: model[k] for k in ("system_id", "version", "model_id", "provider", "config_sha256")
        },
        "attempt": episode["attempt"],
        "try": episode["tries"],
        "environment": {
            "version_id": m["environment"]["version_id"],
            "image": instance and instance["local_image_id"],
            "driver": openenv.KIND if on_openenv else "bridge",
        },
        "safety": prompt
        and {
            "prompt_id": prompt["id"],
            "category_key": prompt["category_key"],
            # D-040: the placement that actually reached the agent (OpenEnv: always the user message).
            "placement": (
                ("tool_result" if injected_at else "not_delivered")
                if tool_inject
                else ("user_message" if on_openenv else inject["placement"])
            ),
            "injected_at": injected_at,
            "requested_placement": inject["placement"],
            "strategy": prompt["strategy"],
        },
        "transcript": transcript,
        "tool_events": events,
        "final_output": final,
        "environment_state": state,
        "snapshots": snapshots,
        "timings": {
            "wall_ms": wall_ms,
            "steps": steps,
            # D-008: steps whose observation was longer than the model was shown (live only).
            "observations_cut": sum(
                1 for t in transcript if t.get("observation_chars", 0) > t.get("shown_chars", 1e18)
            ),
        },
        # D-008: the reset message the agent saw, and the conversation (live) or a mock label.
        "reset": {"user_message": reset.get("user_message")},
        "agent_log": agent_log,
        # Live: the provider's reported usage and the approval's prices; mock: a deterministic estimate, no spend.
        "tokens": {
            "in": live_caller.tokens_in if live_caller else steps * mock_provider.STEP_TOKENS[0],
            "out": live_caller.tokens_out if live_caller else steps * mock_provider.STEP_TOKENS[1],
        },
        "cost_usd": float(live_caller.cost) if live_caller else 0.0,
    }
    # E-002: one receipt per selected clause (case episodes only), resolved on the case's facts and this episode's
    # sealed evidence. A task without clauses gets no key, so its bundle is exactly as before.
    if selected and episode["kind"] != "safety":
        case = {
            "case_id": episode["case_id"],
            "facts": (m.get("case_facts") or {}).get(episode["case_id"]),
        }
        tpl, env_id = m.get("template") or {}, m["environment"]["version_id"]
        bundle["clause_receipts"], bundle["clause_engine"] = clauses.receipts(
            selected,
            case,
            (instance or {}).get("env"),
            evidence={"snapshots": snapshots, "tool_events": events, "final_output": final},
            bindings=m.get("policy_bindings"),
            context={
                "run_id": episode["run_id"],
                "episode_id": episode["id"],
                "task": {"task_id": episode["task_id"], "task_revision": episode["task_revision"]},
                "binding": {
                    "template_id": tpl.get("id"),
                    "template_version": tpl.get("version"),
                    "environment_version_id": env_id,
                },
            },
            zen=m.get("clause_engine"),
        )
    return bundle


def seal(ws, episode, bundle):
    raw = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    rel = f"{ws}/{episode['run_id']}/{episode['id']}-t{episode['tries']}.json"
    path = scoring.EVIDENCE_ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as handle:  # never overwrite sealed evidence
        handle.write(raw)
    os.chmod(path, 0o444)
    return f"local-evidence://{rel}", digest


def _finish_attempt(c, episode, outcome, note=None):
    c.execute(
        "UPDATE runs.episode_attempts SET ended_at=now(), outcome=%s, note=%s WHERE episode_id=%s AND try=%s",
        (outcome, note, episode["id"], episode["tries"]),
    )


def run_episode(ws, episode, session_factory=None):
    run, manifest, instance, actor = _context(ws, episode)
    try:
        if session_factory is None and (
            not instance or not images.instance_alive(instance["container"])
        ):
            raise RuntimeError("environment instance is not running")
        bundle = execute(episode, run, manifest, instance, actor, session_factory)
    except TimeoutError:
        with system_scope(ws) as c:
            _finish_attempt(
                c, episode, "timed_out", f"no result within {run['episode_timeout_s']} s"
            )
            c.execute(
                "UPDATE runs.episodes SET state='timed_out', lease_until=NULL, last_error='episode timeout' WHERE id=%s",
                (episode["id"],),
            )
        return "timed_out"
    except (RuntimeError, OSError, ValueError, KeyError, StopIteration, GymError) as exc:
        message = exc.message if isinstance(exc, GymError) else str(exc)
        final = isinstance(exc, GymError) and exc.code in (
            "LIVE_CAP",
            "LIVE_EPISODE_CAP",
            "LIVE_AMBIGUOUS",
            "LIVE_DISABLED",
            "TASK_NO_INSTRUCTIONS",
        )
        with system_scope(ws) as c:
            _finish_attempt(c, episode, "errored", message[:500])
            # A live call that may have been delivered, a cap, or a disabled gateway is never retried automatically.
            again = not final and episode["tries"] <= run["infra_retries"]
            if isinstance(exc, GymError) and exc.code == "LIVE_CAP":
                # The run stops at its cap: nothing more is started for it.
                c.execute(
                    "UPDATE runs.episodes SET state='errored', last_error=%s WHERE run_id=%s AND state='queued'",
                    (f"not run: {message}"[:500], episode["run_id"]),
                )
                emit(
                    c,
                    ws,
                    "run.cap_reached",
                    episode["run_id"],
                    {
                        "run_id": episode["run_id"],
                        "episode_id": episode["id"],
                        "reason": message[:300],
                    },
                )
            c.execute(
                "UPDATE runs.episodes SET state=%s, lease_until=NULL, last_error=%s WHERE id=%s",
                ("queued" if again else "errored", str(exc)[:500], episode["id"]),
            )
        return "retry" if again else "errored"
    ref, digest = seal(ws, episode, bundle)
    with system_scope(ws) as c:
        c.execute(
            """INSERT INTO runs.sealed_evidence(episode_id,workspace_id,try,bundle_ref,sealed_sha256,tokens_in,tokens_out,cost_usd,timings,synthetic)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                episode["id"],
                ws,
                episode["tries"],
                ref,
                digest,
                bundle["tokens"]["in"],
                bundle["tokens"]["out"],
                bundle["cost_usd"],
                Jsonb(bundle["timings"]),
                bundle["synthetic"],
            ),
        )
        _finish_attempt(c, episode, "sealed")
        c.execute(
            "UPDATE runs.episodes SET state='scoring', lease_until=NULL WHERE id=%s",
            (episode["id"],),
        )
        emit(
            c,
            ws,
            "episode.sealed",
            episode["id"],
            {"episode_id": episode["id"], "run_id": episode["run_id"], "sealed_sha256": digest},
        )
    with system_scope(ws) as c:
        pass_row = c.execute(
            "SELECT * FROM scoring.scoring_passes WHERE run_id=%s AND pass=1", (episode["run_id"],)
        ).fetchone()
        try:
            result = scoring.score_episode(
                c, ws, {**episode, "likely_cause_source": None}, pass_row, manifest["manifest"]
            )
        except (
            Exception
        ) as exc:  # a scoring failure is recorded on the episode, never a silent pass
            c.rollback()
            set_scope(c, ws)
            message = exc.message if isinstance(exc, GymError) else f"{type(exc).__name__}: {exc}"
            c.execute(
                "UPDATE runs.episodes SET state='errored', last_error=%s WHERE id=%s",
                (f"scoring: {message}"[:500], episode["id"]),
            )
            return "errored"
        c.execute("UPDATE runs.episodes SET state='scored' WHERE id=%s", (episode["id"],))
        emit(
            c,
            ws,
            "episode.scored",
            episode["id"],
            {"episode_id": episode["id"], "run_id": episode["run_id"], **result},
        )
    return "scored"


def finish_runs(ws):
    finished = []
    with system_scope(ws) as c:
        for run in c.execute(
            """SELECT r.* FROM runs.runs r WHERE r.workspace_id=%s AND r.state='running'
               AND NOT EXISTS (SELECT 1 FROM runs.episodes e WHERE e.run_id=r.id AND e.state IN ('queued','running','scoring'))
               FOR UPDATE SKIP LOCKED""",
            (ws,),
        ).fetchall():
            counts = {
                r["state"]: r["n"]
                for r in c.execute(
                    "SELECT state, count(*) n FROM runs.episodes WHERE run_id=%s GROUP BY state",
                    (run["id"],),
                ).fetchall()
            }
            state = (
                "cancelled"
                if run["cancel_requested_at"]
                else "completed"
                if counts.get("scored")
                else "failed"
            )
            c.execute(
                "UPDATE runs.runs SET state=%s, finished_at=now() WHERE id=%s", (state, run["id"])
            )
            c.execute(
                "UPDATE scoring.scoring_passes SET finished_at=now() WHERE run_id=%s AND pass=1",
                (run["id"],),
            )
            for inst in c.execute(
                "SELECT * FROM runs.instances WHERE run_id=%s AND stopped_at IS NULL", (run["id"],)
            ).fetchall():
                images.stop_instance(inst["container"])
                c.execute("UPDATE runs.instances SET stopped_at=now() WHERE id=%s", (inst["id"],))
            emit(
                c,
                ws,
                f"run.{state}",
                run["id"],
                {"run_id": run["id"], "project_id": run["project_id"], "episodes": counts},
            )
            if state == "completed":
                finished.append(run["id"])
        # A cancelled run whose last running episode just sealed.
        for run in c.execute(
            """SELECT r.* FROM runs.runs r WHERE r.workspace_id=%s AND r.state='admitted' AND r.cancel_requested_at IS NOT NULL""",
            (ws,),
        ).fetchall():
            c.execute(
                "UPDATE runs.runs SET state='cancelled', finished_at=now() WHERE id=%s",
                (run["id"],),
            )
        # Any instance left by a run that finished another way (cancelled with nothing running, failed) is stopped.
        for inst in c.execute(
            """SELECT i.* FROM runs.instances i JOIN runs.runs r ON r.id=i.run_id
               WHERE i.workspace_id=%s AND i.stopped_at IS NULL AND r.state IN ('completed','failed','cancelled')""",
            (ws,),
        ).fetchall():
            images.stop_instance(inst["container"])
            c.execute("UPDATE runs.instances SET stopped_at=now() WHERE id=%s", (inst["id"],))
    # E-007 phase 1 (shadow): a verification report for each run that just completed, in its own transaction after
    # the run is final. It reports only; any error is logged and never touches the run.
    for run_id in finished:
        try:
            from anvil.rlgym.verification import service as verification

            with system_scope(ws) as c:
                verification.build(c, ws, run_id, requested_by="rlgym:after-run")
        except Exception:
            log.exception(
                "verification report for %s failed (shadow mode; the run is unaffected)", run_id
            )


def tick():
    """One pass over every workspace. Returns the number of episodes processed."""
    done = 0
    for ws in _workspaces():
        recover_leases(ws)
        prepare_runs(ws)
        for _ in range(25):
            episode = lease(ws)
            if not episode:
                break
            run_episode(ws, episode)
            done += 1
        finish_runs(ws)
    return done


def _busy():
    with system_scope() as c:
        return c.execute("SELECT count(*) n FROM runs.workspaces_with_work()").fetchone()["n"] > 0


def drain(timeout=600):
    """Process until no run is admitted or running (tests and `pnpm rlgym:demo`). Safe beside the API's runner thread:
    runs and episodes are claimed with row locks."""
    end = time.time() + timeout
    while time.time() < end:
        with _lock:
            n = tick()
        if not n:
            if not _busy():
                return True
            time.sleep(0.3)
    return False


def start_runner(interval=1.0):
    global _started
    if (
        _started
        or os.environ.get("RLGYM_V2") != "1"
        or os.environ.get("RLGYM_RUNNER", "on") == "off"
    ):
        return
    _started = True

    def loop():
        while True:
            try:
                with _lock:
                    n = tick()
            except (
                Exception
            ):  # keep the loop alive; the failure is logged and the episode lease expires
                log.exception("runner tick failed")
                n = 0
            if not n:
                time.sleep(interval)

    threading.Thread(target=loop, name="rlgym-runner", daemon=True).start()


def utcnow():
    return dt.datetime.now(dt.UTC)
