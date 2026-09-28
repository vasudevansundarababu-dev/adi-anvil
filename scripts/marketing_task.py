"""Offline synthetic task authoring tool. No provider, network, or Anvil DB access.

Operator only: source includes future events and simulation parameters. Never give
this module or raw state to the candidate. It is not a security boundary.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "task-packs" / "marketing-12-week"
CHANNELS = ("search", "social", "webinar", "email")
CAPS = dict(zip(CHANNELS, (6000, 4000, 3000, 2000), strict=True))
THEMES = ("time_saving", "visibility", "reliability")


def conditions(week):
    caps = dict(CAPS)
    capacity = 60
    notice = "No new operational restrictions."
    if week in (4, 5):
        notice = "Search auction competition has increased. Monitor acquisition efficiency."
    if week in (6, 7):
        capacity = 30
        notice = "Sales coverage is reduced this week; only 30 qualified leads can be handled."
    if week == 8:
        caps["webinar"] = 0
        notice = "Webinar platform unavailable this week. No webinar spend allowed."
    if week >= 10:
        notice = "Quarter-end buyers report longer internal approval discussions."
    return {"channel_caps_usd": caps, "sales_capacity": capacity, "notice": notice}


def reset():
    return {
        "version": "MKT-LH-001/1.0",
        "week": 1,
        "remaining_usd": 120000,
        "customers": 0,
        "pipeline": [],
        "history": [],
        "theme": None,
        "streak": 0,
    }


def observe(state):
    done = state["week"] == 13
    spent = 120000 - state["remaining_usd"]
    return {
        "task_version": state["version"],
        "week": state["week"],
        "done": done,
        "remaining_budget_usd": state["remaining_usd"],
        "total_spent_usd": spent,
        "customers": state["customers"],
        "cac_usd": round(spent / state["customers"], 2) if state["customers"] else None,
        "acquired_arr_usd": state["customers"] * 6000,
        "annual_gross_margin_value_usd": state["customers"] * 4800,
        "pending_qualified_leads": sum(p["qualified"] for p in state["pipeline"]),
        "last_receipt": copy.deepcopy(state["history"][-1]) if state["history"] else None,
        "current_conditions": None if done else conditions(state["week"]),
    }


def step(state, action):
    week = state["week"]
    if week > 12:
        raise ValueError("episode_complete")
    keys = {"week", "spend_usd", "message", "refresh_creative", "rationale"}
    if not isinstance(action, dict) or set(action) != keys:
        raise ValueError("action_fields")
    if type(action["week"]) is not int or action["week"] != week:
        raise ValueError("stale_or_invalid_week")
    spend = action["spend_usd"]
    if not isinstance(spend, dict) or set(spend) != set(CHANNELS):
        raise ValueError("channel_fields")
    if not isinstance(action["message"], str) or action["message"] not in THEMES:
        raise ValueError("message")
    if type(action["refresh_creative"]) is not bool:
        raise ValueError("refresh_creative")
    if (
        not isinstance(action["rationale"], str)
        or not 1 <= len(action["rationale"].strip()) <= 4000
    ):
        raise ValueError("rationale")
    current = conditions(week)
    for channel, amount in spend.items():
        if type(amount) is not int or not 0 <= amount <= current["channel_caps_usd"][channel]:
            raise ValueError("channel_spend_limit")
    creative = 1000 if action["refresh_creative"] else 0
    total = sum(spend.values()) + creative
    if total > min(15000, state["remaining_usd"]):
        raise ValueError("budget_limit")

    result = copy.deepcopy(state)
    result["remaining_usd"] -= total
    same = action["message"] == result["theme"] and not action["refresh_creative"]
    result["streak"] = result["streak"] + 1 if same else 1
    result["theme"] = action["message"]
    fatigue_bps = 7500 if result["streak"] >= 3 else 10000
    matured = [p for p in result["pipeline"] if p["due"] == week]
    new_customers = sum(p["customers"] for p in matured)
    result["pipeline"] = [p for p in result["pipeline"] if p["due"] > week]
    result["customers"] += new_customers
    rows = []
    capacity = current["sales_capacity"]
    for channel, cpl, qualify_bps, close_bps in zip(
        CHANNELS,
        (100, 125, 80, 60),
        (6000, 4500, 2500, 3500),
        (2000, 2500, 1500, 1500),
        strict=True,
    ):
        if channel == "search" and week in (4, 5):
            cpl = 150
        if week >= 10:
            close_bps = close_bps * 3 // 4
        leads = spend[channel] * fatigue_bps // (cpl * 10000)
        qualified = leads * qualify_bps // 10000
        accepted = min(qualified, capacity)
        capacity -= accepted
        result["pipeline"].append(
            {
                "due": week + 2,
                "qualified": accepted,
                "customers": accepted * close_bps // 10000,
            }
        )
        rows.append(
            {
                "channel": channel,
                "spend_usd": spend[channel],
                "leads": leads,
                "qualified_leads": qualified,
                "accepted_qualified_leads": accepted,
                "lost_overflow": qualified - accepted,
            }
        )
    receipt = {
        "week": week,
        "action": copy.deepcopy(action),
        "channels": rows,
        "creative_cost_usd": creative,
        "week_cost_usd": total,
        "new_customers": new_customers,
        "cumulative_customers": result["customers"],
        "remaining_budget_usd": result["remaining_usd"],
    }
    result["history"].append(receipt)
    result["week"] += 1
    return result


def initial_input():
    history = []
    for week in range(-16, 0):
        for index, channel in enumerate(CHANNELS):
            spend = (2000, 1500, 2400, 900)[index] + ((week + 16) % 4) * 100
            leads = spend // ((105, 130, 85, 65)[index] + (week % 3) * 5)
            qualified = leads * (58, 42, 30, 36)[index] // 100
            history.append(
                {
                    "cohort_week": week,
                    "channel": channel,
                    "spend_usd": spend,
                    "leads": leads,
                    "qualified_leads": qualified,
                    "eventual_customers": qualified * (22, 24, 18, 17)[index] // 100,
                    "fully_matured": True,
                }
            )
    return {
        "task_id": "MKT-LH-001",
        "version": "1.0",
        "origin": "original_synthetic",
        "company": "Northstar Flow (fictional)",
        "currency": "USD",
        "product_facts": [
            "Shared workflow boards, task owners and due-date reminders.",
            "CSV import and export; browser application; email support on business days.",
            "Annual contract price $6,000; modeled gross margin 80%.",
            "No supplied certification, guaranteed time-saving or customer proof claims.",
        ],
        "segments": [
            {"name": "Operations teams", "employees": "20–100", "need": "Ownership and handoffs"},
            {"name": "Agencies", "employees": "10–50", "need": "Visibility across client work"},
        ],
        "synthetic_interviews": [
            {
                "id": f"I{i + 1:02}",
                "segment": "Operations teams" if i < 4 else "Agencies",
                "quote": quote,
            }
            for i, quote in enumerate(
                [
                    "Work disappears between handoffs.",
                    "I need to see who owns the next step.",
                    "Our team will not tolerate a long setup.",
                    "Show the workflow before asking for a call.",
                    "We already have tools but reporting is fragmented.",
                    "A clear view of overdue work would help.",
                    "Annual commitments need approval from our finance lead.",
                    "We want a simple export if we decide to leave.",
                ]
            )
        ],
        "definitions": {
            "lead": "A synthetic response attributed to exactly one channel; no cross-channel duplicates.",
            "qualified_lead": "A lead meeting the modeled fit threshold; not yet a customer.",
            "eventual_customers": "Matured customers attributed to their acquisition cohort, not close week.",
            "historical_cost": "Media only; no creative overhead is modeled in the historical rows.",
            "cac": "All current campaign media and creative cost divided by acquired customers.",
        },
        "historical_channel_weeks": history,
        "opening_observation": observe(reset()),
    }


def generate():
    target = PACK / "actor" / "initial-input.json"
    target.write_text(json.dumps(initial_input(), indent=2) + "\n")
    files = [PACK / "actor" / "task.md", target]
    manifest = {
        "task_version": "MKT-LH-001/1.0",
        "classification": "actor_input",
        "files": [
            {"path": str(p.relative_to(PACK)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in files
        ],
    }
    (PACK / "actor-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Generated 64 synthetic channel-week records and 8 fictional interviews; no API calls.")


def rehearse():
    state = reset()
    for week in range(1, 13):
        state = step(
            state,
            {
                "week": week,
                "spend_usd": {
                    "search": 4000,
                    "social": 2000,
                    "webinar": 0 if week == 8 else 2000,
                    "email": 1000,
                },
                "message": THEMES[(week - 1) % 3],
                "refresh_creative": False,
                "rationale": "Scripted software rehearsal; not a model answer or recommended policy.",
            },
        )
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "rehearse"))
    args = parser.parse_args()
    if args.command == "generate":
        generate()
    else:
        print(
            json.dumps({"origin": "scripted_software_rehearsal", **observe(rehearse())}, indent=2)
        )
