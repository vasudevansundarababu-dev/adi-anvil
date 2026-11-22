"""Live approvals: the owner's written permission for one provider and model, with caps (migration 052).

An approval names the exact provider, model id (and, for Hugging Face, the pinned revision), what it may be used for
(agent, judge, generator, probe, key_test), a per-run cap and a total cap in USD, the input and output prices per
million tokens the approver verified, who approved, and when it expires. It is final; it can only be revoked.

- Only an Admin, as a person, records one. The person who starts a live run must not be the approver (two people).
- Admission refuses a live run without a matching, unexpired, unrevoked approval, or when its worst-case estimate
  exceeds the per-run cap or what is left of the total cap.
- Every live call is written to `systems.live_calls` with its tokens and cost (an ambiguous call at its maximum cost).
  A run stops before a call whose maximum cost would cross either cap.
"""

import datetime as dt
from decimal import Decimal

from anvil.rlgym.common import GymError, audit, new_id, require
from anvil.rlgym.live.gateway import PROVIDERS

USES = ("agent", "judge", "generator", "probe", "key_test")
MAX_DAYS = 31


def _now():
    return dt.datetime.now(dt.UTC)


def create(ctx, body):
    ctx.actor.require_person()
    require(ctx.actor.profile == "admin", "FORBIDDEN", "Only an Admin records a live approval")
    provider = body.get("provider")
    require(provider in PROVIDERS, "VALIDATION_FAILED", "Unknown live provider", field="provider")
    model_id = (body.get("model_id") or "").strip()
    require(model_id, "VALIDATION_FAILED", "The exact model id is required", field="model_id")
    uses = body.get("uses") or ["agent"]
    require(
        isinstance(uses, list) and uses and all(u in USES for u in uses),
        "VALIDATION_FAILED",
        f"uses must be some of {list(USES)}",
        field="uses",
    )
    nums = {}
    for name in (
        "per_run_cap_usd",
        "total_cap_usd",
        "price_in_per_mtok_usd",
        "price_out_per_mtok_usd",
    ):
        try:
            nums[name] = Decimal(str(body.get(name)))
        except Exception:
            raise GymError(
                "VALIDATION_FAILED", f"{name} must be a number", {"field": name}
            ) from None
        require(nums[name] >= 0, "VALIDATION_FAILED", f"{name} must not be negative", field=name)
    require(
        nums["per_run_cap_usd"] > 0,
        "VALIDATION_FAILED",
        "The per-run cap must be above 0",
        field="per_run_cap_usd",
    )
    require(
        nums["total_cap_usd"] >= nums["per_run_cap_usd"],
        "VALIDATION_FAILED",
        "The total cap must be at least the per-run cap",
        field="total_cap_usd",
    )
    note = (body.get("prices_note") or "").strip()
    require(
        note,
        "VALIDATION_FAILED",
        "Say where and when the prices were verified (prices change)",
        field="prices_note",
    )
    try:
        expires = dt.datetime.fromisoformat(body.get("expires_at"))
    except (TypeError, ValueError):
        raise GymError(
            "VALIDATION_FAILED", "expires_at must be an ISO date-time", {"field": "expires_at"}
        ) from None
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.UTC)
    require(
        _now() < expires <= _now() + dt.timedelta(days=MAX_DAYS),
        "VALIDATION_FAILED",
        f"An approval expires in the future and within {MAX_DAYS} days",
        field="expires_at",
    )
    revision = body.get("hf_revision")
    if provider == "huggingface":
        require(
            isinstance(revision, str) and len(revision) == 40,
            "VALIDATION_FAILED",
            "Pin the Hugging Face revision (40-character commit hash)",
            field="hf_revision",
        )
    aid = new_id("la-")
    row = ctx.c.execute(
        """INSERT INTO systems.live_approvals(id,workspace_id,provider,model_id,hf_revision,uses,per_run_cap_usd,total_cap_usd,
             price_in_per_mtok_usd,price_out_per_mtok_usd,prices_note,approved_by,expires_at)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            aid,
            ctx.ws,
            provider,
            model_id,
            revision if provider == "huggingface" else None,
            uses,
            nums["per_run_cap_usd"],
            nums["total_cap_usd"],
            nums["price_in_per_mtok_usd"],
            nums["price_out_per_mtok_usd"],
            note,
            ctx.actor.id,
            expires,
        ),
    ).fetchone()
    audit(
        ctx.c,
        ctx.ws,
        ctx.actor,
        "live_approval.recorded",
        aid,
        details={"provider": provider, "model_id": model_id},
    )
    return view(ctx.c, ctx.ws, row)


def revoke(ctx, aid, body):
    ctx.actor.require_person()
    require(ctx.actor.profile == "admin", "FORBIDDEN", "Only an Admin revokes a live approval")
    reason = (body.get("reason") or "").strip()
    require(reason, "VALIDATION_FAILED", "A reason is required", field="reason")
    row = ctx.c.execute(
        """UPDATE systems.live_approvals SET revoked_at=now(), revoked_by=%s, revoke_reason=%s
           WHERE workspace_id=%s AND id=%s AND revoked_at IS NULL RETURNING *""",
        (ctx.actor.id, reason, ctx.ws, aid),
    ).fetchone()
    require(row, "NOT_FOUND", "No active approval with that id")
    audit(ctx.c, ctx.ws, ctx.actor, "live_approval.revoked", aid, details={"reason": reason})
    return view(ctx.c, ctx.ws, row)


def spent(c, ws, aid, run_id=None):
    sql = "SELECT coalesce(sum(cost_usd),0) s FROM systems.live_calls WHERE workspace_id=%s AND approval_id=%s"
    params = [ws, aid]
    if run_id:
        sql += " AND run_id=%s"
        params.append(run_id)
    return Decimal(str(c.execute(sql, params).fetchone()["s"]))


def view(c, ws, row):
    used = spent(c, ws, row["id"])
    active = row["revoked_at"] is None and row["expires_at"] > _now()
    return {
        **row,
        "spent_usd": used,
        "remaining_usd": max(Decimal(0), Decimal(str(row["total_cap_usd"])) - used),
        "state": "revoked" if row["revoked_at"] else ("active" if active else "expired"),
    }


def list_all(c, ws):
    rows = c.execute(
        "SELECT * FROM systems.live_approvals WHERE workspace_id=%s ORDER BY approved_at DESC",
        (ws,),
    ).fetchall()
    return [view(c, ws, r) for r in rows]


def find(c, ws, provider, model_id, use, hf_revision=None):
    """The newest active approval matching exactly, or None."""
    rows = c.execute(
        """SELECT * FROM systems.live_approvals WHERE workspace_id=%s AND provider=%s AND model_id=%s
             AND %s = ANY(uses) AND revoked_at IS NULL AND expires_at > now()
             AND (provider <> 'huggingface' OR hf_revision=%s)
           ORDER BY approved_at DESC""",
        (ws, provider, model_id, use, hf_revision),
    ).fetchall()
    return rows[0] if rows else None


def require_for(
    c,
    ws,
    provider,
    model_id,
    use,
    *,
    hf_revision=None,
    requested_by=None,
    estimate_usd=None,
    run_id=None,
):
    """The approval a live action uses, or ADMISSION_REFUSED with the reason."""
    a = find(c, ws, provider, model_id, use, hf_revision)
    if not a:
        raise GymError(
            "ADMISSION_REFUSED",
            f"No active live approval for {provider} {model_id} ({use})",
            {"provider": provider, "model_id": model_id, "use": use},
        )
    if requested_by is not None and str(requested_by) == str(a["approved_by"]):
        raise GymError(
            "ADMISSION_REFUSED",
            "The approver cannot also start this live run; another person starts it",
            {"approval": a["id"]},
        )
    if estimate_usd is not None:
        left = Decimal(str(a["total_cap_usd"])) - spent(c, ws, a["id"])
        if Decimal(str(estimate_usd)) > Decimal(str(a["per_run_cap_usd"])):
            raise GymError(
                "ADMISSION_REFUSED",
                f"Estimated ${estimate_usd} is above the per-run cap ${a['per_run_cap_usd']}",
                {"approval": a["id"]},
            )
        if Decimal(str(estimate_usd)) > left:
            raise GymError(
                "ADMISSION_REFUSED",
                f"Estimated ${estimate_usd} is above what is left of the total cap (${left})",
                {"approval": a["id"]},
            )
    return a


def max_cost(a, tokens_in, max_out):
    return (
        Decimal(tokens_in) * Decimal(str(a["price_in_per_mtok_usd"]))
        + Decimal(max_out) * Decimal(str(a["price_out_per_mtok_usd"]))
    ) / Decimal(1_000_000)


def room(c, ws, a, run_id, next_max):
    """Whether one more call (its maximum cost) stays within the run cap and the total cap."""
    run_left = Decimal(str(a["per_run_cap_usd"])) - (
        spent(c, ws, a["id"], run_id) if run_id else Decimal(0)
    )
    total_left = Decimal(str(a["total_cap_usd"])) - spent(c, ws, a["id"])
    return next_max <= run_left and next_max <= total_left


def record(
    c, ws, a, use, status, *, completion=None, cost=None, run_id=None, episode_id=None, note=None
):
    c.execute(
        """INSERT INTO systems.live_calls(workspace_id,approval_id,use,run_id,episode_id,provider,model_id,request_id,status,
             tokens_in,tokens_out,cost_usd,note) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            ws,
            a["id"],
            use,
            run_id,
            episode_id,
            a["provider"],
            a["model_id"],
            completion.request_id if completion else None,
            status,
            completion.tokens_in if completion else 0,
            completion.tokens_out if completion else 0,
            cost or 0,
            (note or "")[:300] or None,
        ),
    )
