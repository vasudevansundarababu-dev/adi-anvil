"""Atomic integer micro-USD ledger. Reservation alone never grants dispatch authority."""

from fastapi import HTTPException

from anvil.db import audit, one, uid


def reserve(c, project, window_id, run_id, amount, operation_key):
    if type(amount) is not int or amount <= 0:
        raise HTTPException(409, "Known positive conservative cost bound required")
    window = one(
        c, "SELECT * FROM anvil.evaluation_spend_windows WHERE id=%s FOR UPDATE", (window_id,)
    )
    run = one(
        c,
        "SELECT * FROM anvil.run_budgets WHERE run_id=%s AND window_id=%s FOR UPDATE",
        (run_id, window_id),
    )
    if not window or not run:
        raise HTTPException(404, "Scoped spend window/run budget missing")
    old = one(c, "SELECT * FROM anvil.budget_reservations WHERE operation_key=%s", (operation_key,))
    if old:
        if str(old["run_id"]) != str(run_id) or old["amount_micro_usd"] != amount:
            raise HTTPException(409, "Reservation replay differs")
        return old
    active = one(
        c,
        "SELECT 1 FROM anvil.evaluation_spend_windows WHERE id=%s AND status='active' AND start_at<=now() AND end_at>now()",
        (window_id,),
    )
    if not active or any(
        r["reserved_micro_usd"] + r["settled_micro_usd"] + amount > r["cap_micro_usd"]
        for r in (window, run)
    ):
        raise HTTPException(409, "Spend ceiling exhausted or window expired")
    rid = uid()
    c.execute(
        "UPDATE anvil.evaluation_spend_windows SET reserved_micro_usd=reserved_micro_usd+%s,row_version=row_version+1 WHERE id=%s",
        (amount, window_id),
    )
    c.execute(
        "UPDATE anvil.run_budgets SET reserved_micro_usd=reserved_micro_usd+%s WHERE run_id=%s",
        (amount, run_id),
    )
    c.execute(
        "INSERT INTO anvil.budget_reservations(id,project_id,window_id,run_id,operation_key,amount_micro_usd,status) VALUES(%s,%s,%s,%s,%s,%s,'reserved')",
        (rid, project, window_id, run_id, operation_key, amount),
    )
    audit(c, project, None, "budget.reserved", rid, {"micro_usd": amount})
    return one(c, "SELECT * FROM anvil.budget_reservations WHERE id=%s", (rid,))


def reconcile(c, project, reservation_id, actual=None, known_not_dispatched=False):
    row = one(c, "SELECT * FROM anvil.budget_reservations WHERE id=%s", (reservation_id,))
    if not row:
        raise HTTPException(404, "Reservation not found")
    # Same fixed lock order as reserve: global window, then run, then reservation.
    c.execute(
        "SELECT id FROM anvil.evaluation_spend_windows WHERE id=%s FOR UPDATE", (row["window_id"],)
    )
    c.execute("SELECT run_id FROM anvil.run_budgets WHERE run_id=%s FOR UPDATE", (row["run_id"],))
    row = one(
        c, "SELECT * FROM anvil.budget_reservations WHERE id=%s FOR UPDATE", (reservation_id,)
    )
    if row["status"] in ("settled", "released"):
        return row
    if actual is None and not known_not_dispatched:
        c.execute(
            "UPDATE anvil.budget_reservations SET status='unknown' WHERE id=%s", (reservation_id,)
        )
        return one(c, "SELECT * FROM anvil.budget_reservations WHERE id=%s", (reservation_id,))
    cost = 0 if known_not_dispatched else actual
    if type(cost) is not int or not 0 <= cost <= row["amount_micro_usd"]:
        raise HTTPException(
            409, "Reconciliation exceeds conservative reservation; manual incident required"
        )
    for table, key, value in [
        ("evaluation_spend_windows", "id", row["window_id"]),
        ("run_budgets", "run_id", row["run_id"]),
    ]:
        c.execute(
            f"UPDATE anvil.{table} SET reserved_micro_usd=reserved_micro_usd-%s,settled_micro_usd=settled_micro_usd+%s WHERE {key}=%s",
            (row["amount_micro_usd"], cost, value),
        )
    c.execute(
        "UPDATE anvil.budget_reservations SET status=%s,actual_micro_usd=%s WHERE id=%s",
        ("released" if known_not_dispatched else "settled", cost, reservation_id),
    )
    audit(c, project, None, "budget.reconciled", reservation_id, {"actual_micro_usd": cost})
    return one(c, "SELECT * FROM anvil.budget_reservations WHERE id=%s", (reservation_id,))
