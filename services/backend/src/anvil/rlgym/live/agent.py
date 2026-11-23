"""A live model as the agent (behind an approval). Same protocol as the mock agents: a generator that yields
{"tool", "args"} or {"final": {...}} and is sent each observation.

The model sees only what a candidate sees: the task's instructions (built from the actor payload, D-007), the application it reviews (Studio's images), the
declared operations and the observations. It answers with one JSON action per turn. Each model call goes through
`LiveCaller`, which checks the caps before the call (its maximum cost), records the call with its tokens and cost,
and stops the episode at a cap or on an ambiguous dispatch (never retried).
"""

import hashlib
import json
import time
from decimal import Decimal

from anvil.rlgym.common import GymError, system_scope
from anvil.rlgym.live import approvals
from anvil.rlgym.live.gateway import Ambiguous, parse_json

PROTOCOL = (
    "You are the agent under evaluation. Work only through the operations listed below. Reply with exactly one JSON "
    'object per turn and nothing else: {"tool": "<operation id>", "args": {...}} to call an operation, or '
    '{"final": {...}} when you are done (include "decision" and your findings). Observations come back as JSON.'
)
MAX_OBS_CHARS = (
    12000  # default; a model version may set params.max_observation_chars (part of its config hash)
)


def render_observation(obs, limit=MAX_OBS_CHARS):
    """The observation text the model is shown and the full length (D-008). A longer observation is cut with an explicit
    line, never silently mid-JSON."""
    text = json.dumps(obs, default=str)
    total = len(text)
    if total <= limit:
        return text, total
    return text[
        :limit
    ] + f"\n[cut: showing {limit} of {total} characters; narrow the request]", total


class CapReached(GymError):
    """The approval cannot pay for more: revoked, expired, or its per-run / total cap reached. Stops the run."""

    def __init__(self, message):
        super().__init__("LIVE_CAP", message)


class EpisodeCapReached(GymError):
    """This episode's own spend limit (the model version's spend per episode) is reached. Ends this episode only; the
    run goes on with the next one."""

    def __init__(self, message):
        super().__init__("LIVE_EPISODE_CAP", message)


class LiveCaller:
    """One episode's model calls against one approval: caps checked first, every call recorded."""

    def __init__(self, gateway, ws, run_id, episode_id, model, use="agent"):
        self.gateway, self.ws, self.run_id, self.episode_id = gateway, ws, run_id, episode_id
        self.model, self.live, self.use = model, model["live"], use
        self.params = self.live.get("params") or {}
        self.max_out = int(self.params.get("max_output_tokens") or 1024)
        self.episode_cap = Decimal(str(model.get("spend_per_episode_usd") or 0))
        self.tokens_in = self.tokens_out = 0
        self.cost = Decimal(0)

    def _approval(self, c):
        a = c.execute(
            "SELECT * FROM systems.live_approvals WHERE workspace_id=%s AND id=%s",
            (self.ws, self.live["approval_id"]),
        ).fetchone()
        if not a or a["revoked_at"] is not None:
            raise CapReached(f"approval {self.live['approval_id']} is revoked")
        import datetime as dt

        if a["expires_at"] <= dt.datetime.now(dt.UTC):
            raise CapReached(f"approval {self.live['approval_id']} expired")
        return a

    def __call__(self, messages):
        est_in = sum(len(m["content"]) for m in messages) // 3 + 50  # conservative token estimate
        with system_scope(self.ws) as c:
            a = self._approval(c)
            worst = approvals.max_cost(a, est_in, self.max_out)
            if self.episode_cap and self.cost + worst > self.episode_cap:
                raise EpisodeCapReached(f"episode spend limit ${self.episode_cap} would be crossed")
            if not approvals.room(c, self.ws, a, self.run_id, worst):
                raise CapReached("the approval's per-run or total cap would be crossed")
        try:
            out = self.gateway.complete(
                self.model["provider"],
                self.model["model_id"],
                messages,
                max_output_tokens=self.max_out,
                temperature=self.params.get("temperature"),
                timeout_s=int(self.params.get("timeout_s") or 60),
                serving=self.live.get("serving"),
                hf_revision=self.live.get("hf_revision"),
            )
        except Ambiguous as exc:
            with system_scope(self.ws) as c:
                approvals.record(
                    c,
                    self.ws,
                    a,
                    self.use,
                    "ambiguous",
                    cost=worst,
                    run_id=self.run_id,
                    episode_id=self.episode_id,
                    note=exc.message,
                )
            self.cost += worst
            raise
        except GymError as exc:
            with system_scope(self.ws) as c:
                approvals.record(
                    c,
                    self.ws,
                    a,
                    self.use,
                    "error",
                    run_id=self.run_id,
                    episode_id=self.episode_id,
                    note=exc.message,
                )
            raise
        cost = out.cost(a["price_in_per_mtok_usd"], a["price_out_per_mtok_usd"])
        with system_scope(self.ws) as c:
            approvals.record(
                c,
                self.ws,
                a,
                self.use,
                "ok",
                completion=out,
                cost=cost,
                run_id=self.run_id,
                episode_id=self.episode_id,
            )
        self.tokens_in += out.tokens_in
        self.tokens_out += out.tokens_out
        self.cost += cost
        return out


def live_agent(
    call,
    assignment,
    operations,
    application_id=None,
    user_message=None,
    max_steps=40,
    log=None,
    max_observation_chars=MAX_OBS_CHARS,
):
    """The model's turns as a policy generator. `operations`: [{"operation_id", "input_schema"?}] or names."""
    ops = [
        {"operation_id": o}
        if isinstance(o, str)
        else {k: o[k] for k in ("operation_id", "input_schema") if k in o}
        for o in operations
    ]
    if not (assignment or "").strip():
        # D-007: never a generic fallback; the worker refuses a task without instructions before this point.
        raise GymError("TASK_NO_INSTRUCTIONS", "No task instructions for the live agent")
    task = assignment
    if application_id:
        task += f"\n\nApplication under review: {application_id}"
    if user_message:
        task += f"\n\n{user_message}"
    messages = [
        {"role": "system", "content": PROTOCOL + "\n\nOperations:\n" + json.dumps(ops)},
        {"role": "user", "content": task},
    ]
    # D-008: the conversation as sent and received, kept in the sealed bundle. The opening messages once, then each
    # turn's new messages only (the history is their concatenation), so the record grows linearly.
    if log is not None:
        log["messages"] = [dict(m) for m in messages]
        log["messages_sha256"] = hashlib.sha256(json.dumps(messages).encode()).hexdigest()
        log["max_observation_chars"] = max_observation_chars
        log["turns"] = []
    nudged = False
    for _ in range(max_steps):
        started = time.monotonic()
        out = call(messages)
        action = parse_json(out.text)
        messages.append({"role": "assistant", "content": out.text})
        turn = None
        if log is not None:
            turn = {
                "turn": len(log["turns"]) + 1,
                "raw": out.text,
                "finish_reason": getattr(out, "finish_reason", None),
                "tokens_in": getattr(out, "tokens_in", None),
                "tokens_out": getattr(out, "tokens_out", None),
                "request_id": getattr(out, "request_id", None),
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            log["turns"].append(turn)
        if not action or not ("final" in action or "tool" in action):
            if turn is not None:
                turn["parsed"] = "unreadable"
            if nudged:
                yield {"final": None}
                return
            nudged = True
            nudge = "Reply with one JSON object only, as described."
            messages.append({"role": "user", "content": nudge})
            if turn is not None:
                turn["nudge"] = nudge
            continue
        if "final" in action:
            if turn is not None:
                turn["parsed"] = "final"
            yield {"final": action["final"]}
            return
        if turn is not None:
            turn["parsed"] = "tool"
        obs = yield {"tool": str(action["tool"]), "args": action.get("args") or {}}
        shown, total = render_observation(obs, max_observation_chars)
        messages.append({"role": "user", "content": "Observation: " + shown})
        if turn is not None:
            turn["observation_shown"] = "Observation: " + shown
            turn["observation_chars"] = total
            turn["observation_cut"] = total > max_observation_chars
    yield {"final": None}
