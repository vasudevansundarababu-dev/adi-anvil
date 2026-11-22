"""A live model as the agent (behind an approval). Same protocol as the mock agents: a generator that yields
{"tool", "args"} or {"final": {...}} and is sent each observation.

The model sees only what a candidate sees: the task's assignment, the application it reviews (Studio's images), the
declared operations and the observations. It answers with one JSON action per turn. Each model call goes through
`LiveCaller`, which checks the caps before the call (its maximum cost), records the call with its tokens and cost,
and stops the episode at a cap or on an ambiguous dispatch (never retried).
"""

import json
from decimal import Decimal

from anvil.rlgym.common import GymError, system_scope
from anvil.rlgym.live import approvals
from anvil.rlgym.live.gateway import Ambiguous, parse_json

PROTOCOL = (
    "You are the agent under evaluation. Work only through the operations listed below. Reply with exactly one JSON "
    'object per turn and nothing else: {"tool": "<operation id>", "args": {...}} to call an operation, or '
    '{"final": {...}} when you are done (include "decision" and your findings). Observations come back as JSON.'
)
MAX_OBS_CHARS = 12000


class CapReached(GymError):
    def __init__(self, message):
        super().__init__("LIVE_CAP", message)


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
                raise CapReached(f"episode spend limit ${self.episode_cap} would be crossed")
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


def live_agent(call, assignment, operations, application_id=None, user_message=None, max_steps=40):
    """The model's turns as a policy generator. `operations`: [{"operation_id", "input_schema"?}] or names."""
    ops = [
        {"operation_id": o}
        if isinstance(o, str)
        else {k: o[k] for k in ("operation_id", "input_schema") if k in o}
        for o in operations
    ]
    task = assignment or "Review the application and return a decision with findings."
    if application_id:
        task += f"\n\nApplication under review: {application_id}"
    if user_message:
        task += f"\n\n{user_message}"
    messages = [
        {"role": "system", "content": PROTOCOL + "\n\nOperations:\n" + json.dumps(ops)},
        {"role": "user", "content": task},
    ]
    nudged = False
    for _ in range(max_steps):
        out = call(messages)
        action = parse_json(out.text)
        messages.append({"role": "assistant", "content": out.text})
        if not action or not ("final" in action or "tool" in action):
            if nudged:
                yield {"final": None}
                return
            nudged = True
            messages.append(
                {"role": "user", "content": "Reply with one JSON object only, as described."}
            )
            continue
        if "final" in action:
            yield {"final": action["final"]}
            return
        obs = yield {"tool": str(action["tool"]), "args": action.get("args") or {}}
        messages.append(
            {
                "role": "user",
                "content": "Observation: " + json.dumps(obs, default=str)[:MAX_OBS_CHARS],
            }
        )
    yield {"final": None}
