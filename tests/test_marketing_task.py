"""Network-free behavioral checks for the original marketing task pack."""

import copy
import importlib.util
import json
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "marketing_task", Path(__file__).resolve().parents[1] / "scripts" / "marketing_task.py"
)
env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(env)


def action(week, search=0):
    return {
        "week": week,
        "spend_usd": {"search": search, "social": 0, "webinar": 0, "email": 0},
        "message": "visibility",
        "refresh_creative": False,
        "rationale": "Test hypothesis.",
    }


class MarketingTaskTests(unittest.TestCase):
    def test_delayed_customers_and_budget_carryover(self):
        state = env.step(env.reset(), action(1, 5000))
        self.assertEqual(state["customers"], 0)
        self.assertEqual(state["remaining_usd"], 115000)
        state = env.step(state, action(2))
        self.assertEqual(state["customers"], 0)
        state = env.step(state, action(3))
        self.assertEqual(state["customers"], 6)
        self.assertEqual(state["remaining_usd"], 115000)

    def test_rejected_action_does_not_mutate_and_stale_week_rejected(self):
        state = env.reset()
        original = copy.deepcopy(state)
        for spend in (-1, True, 1.5, 6001):
            with self.assertRaises(ValueError):
                env.step(state, action(1, spend))
            self.assertEqual(state, original)
        with self.assertRaises(ValueError):
            env.step(env.step(state, action(1)), action(1))

    def test_remaining_budget_and_refresh_cost_enforced(self):
        state = env.reset()
        state["remaining_usd"] = 999
        attempted = action(1)
        attempted["refresh_creative"] = True
        with self.assertRaisesRegex(ValueError, "budget_limit"):
            env.step(state, attempted)
        state["remaining_usd"] = 1000
        result = env.step(state, attempted)
        self.assertEqual(result["remaining_usd"], 0)

    def test_weekly_total_cap(self):
        attempted = action(1)
        attempted["spend_usd"] = dict(env.CAPS)
        attempted["refresh_creative"] = True
        with self.assertRaisesRegex(ValueError, "budget_limit"):
            env.step(env.reset(), attempted)

    def test_future_outcomes_and_events_absent_from_observation(self):
        state = env.step(env.reset(), action(1, 5000))
        observed = env.observe(state)
        self.assertNotIn("pipeline", observed)
        self.assertNotIn("due", json.dumps(observed))
        self.assertNotIn("Webinar platform unavailable", json.dumps(observed))
        observed["last_receipt"]["action"]["message"] = "tampered"
        self.assertEqual(state["history"][0]["action"]["message"], "visibility")

    def test_capacity_and_outage(self):
        state = env.reset()
        for week in range(1, 6):
            state = env.step(state, action(week))
        attempted = action(6)
        attempted["spend_usd"] = dict(env.CAPS)
        result = env.step(state, attempted)
        rows = result["history"][-1]["channels"]
        self.assertEqual(sum(r["accepted_qualified_leads"] for r in rows), 30)
        self.assertGreater(sum(r["lost_overflow"] for r in rows), 0)
        result = env.step(result, action(7))
        attempted = action(8)
        attempted["spend_usd"]["webinar"] = 1
        with self.assertRaisesRegex(ValueError, "channel_spend_limit"):
            env.step(result, attempted)

    def test_fatigue_and_refresh(self):
        state = env.step(env.reset(), action(1, 5000))
        state = env.step(state, action(2, 5000))
        tired = env.step(state, action(3, 5000))
        refreshed_action = action(3, 5000)
        refreshed_action["refresh_creative"] = True
        fresh = env.step(state, refreshed_action)
        tired_leads = tired["history"][-1]["channels"][0]["leads"]
        fresh_leads = fresh["history"][-1]["channels"][0]["leads"]
        self.assertGreater(fresh_leads, tired_leads)
        self.assertEqual(tired["remaining_usd"] - fresh["remaining_usd"], 1000)

    def test_full_rehearsal_replay_accounting_and_terminal(self):
        state = env.rehearse()
        self.assertEqual(state, env.rehearse())
        self.assertEqual(len(state["history"]), 12)
        total = sum(r["week_cost_usd"] for r in state["history"])
        self.assertEqual(total + state["remaining_usd"], 120000)
        self.assertEqual(sum(r["new_customers"] for r in state["history"]), state["customers"])
        self.assertTrue(env.observe(state)["done"])
        self.assertGreater(env.observe(state)["pending_qualified_leads"], 0)
        self.assertGreaterEqual(state["customers"], 45)
        self.assertLessEqual(env.observe(state)["cac_usd"], 2700)
        with self.assertRaisesRegex(ValueError, "episode_complete"):
            env.step(state, action(13))
        self.assertEqual(env.reset()["history"], [])

    def test_generated_input_is_reproducible_and_consistent(self):
        payload = env.initial_input()
        self.assertEqual(payload, env.initial_input())
        rows = payload["historical_channel_weeks"]
        self.assertEqual(len(rows), 64)
        self.assertEqual(len({(r["cohort_week"], r["channel"]) for r in rows}), 64)
        for row in rows:
            self.assertLessEqual(row["eventual_customers"], row["qualified_leads"])
            self.assertLessEqual(row["qualified_leads"], row["leads"])


if __name__ == "__main__":
    unittest.main()
