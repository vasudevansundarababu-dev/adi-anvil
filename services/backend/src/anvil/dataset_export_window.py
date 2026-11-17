"""Export-only testing access bounded by existing pilot authority; never extends it."""

from datetime import datetime, timezone

from anvil import pilot_environment

PILOT_STOP = datetime(2026, 12, 11, 5, 48, 4, tzinfo=timezone.utc)


def policy(c):
    try:
        environment = pilot_environment.current()
    except ValueError:
        return {"available": False, "reason": "pilot_namespace_binding_invalid"}
    if environment is None:
        return {"available": False, "reason": "approved_pilot_required"}
    row = c.execute(
        "SELECT end_at,status,start_at<=now() AND end_at>now() AS current FROM anvil.pilot_budget_policies WHERE environment=%s",
        (environment,),
    ).fetchone()
    if not row or row["status"] != "active" or not row["current"]:
        return {"available": False, "reason": "pilot_window_absent_expired_or_closed"}
    end = min(row["end_at"], PILOT_STOP)
    if not c.execute("SELECT now()<%s AS current", (end,)).fetchone()["current"]:
        return {"available": False, "reason": "pilot_window_expired"}
    return {
        "available": True,
        "environment": environment,
        "expires_at": end.isoformat(),
        "maximum_end_at": PILOT_STOP.isoformat(),
    }


def permits(c, client):
    if client["lifetime_mode"] == "hours":
        return True
    window = policy(c)
    return bool(
        window["available"]
        and window["environment"] == client["pilot_environment"]
        and client["pilot_end_at"] <= PILOT_STOP
    )
