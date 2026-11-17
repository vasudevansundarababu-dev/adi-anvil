"""Local five-role Task2 controller. No provider, vendor connection or media generation.

All construction/controller methods belong to the trusted host. The candidate
interface is call(role_token, generation, operation, body), never this object.
HTTP/SQL admission is separate; this module alone grants no Anvil Run authority.
"""

import secrets
from copy import deepcopy
from datetime import datetime
from uuid import uuid4

from anvil.marketing_task2_contract import CASES, ROLES, VERSION
from anvil.praxis_generic_contract import digest

WRITERS = {
    "intent-assessments": "intent_analyst",
    "investigations": "intent_analyst",
    "plans": "campaign_orchestrator",
    "experiments": "performance_budget_analyst",
    "weekly-reviews": "campaign_orchestrator",
    "production-requests": "brief_delivery_coordinator",
    "creative-briefs": "brief_delivery_coordinator",
    "delivery-manifests": "brief_delivery_coordinator",
    "campaign-findings": "campaign_policy_reviewer",
    "readiness-assessments": "campaign_policy_reviewer",
    "readiness-requests": "campaign_orchestrator",
    "budget-proposals": "performance_budget_analyst",
    "forecast-requests": "performance_budget_analyst",
    "approval-requests": "campaign_orchestrator",
    "handoffs": "campaign_orchestrator",
    "disagreements": None,
}


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone-aware simulation time required")
    return parsed


class Task2Controller:
    def __init__(self, case_id, *, records, start, outcome, budget_minor):
        if case_id not in CASES or outcome not in {"positive", "null", "negative"}:
            raise ValueError("Explicit supported case and host-selected private outcome required")
        if type(budget_minor) is not int or budget_minor < 0:
            raise ValueError("Integer budget minor units required")
        timestamp(start)
        self._initial = deepcopy(records)
        self._start, self._outcome, self._budget = start, outcome, budget_minor
        self.case_id = case_id
        self.audit = []
        self.history = []
        self.generation = -1
        self.reset()

    def reset(self):
        if self.generation >= 0:
            self.history.append(self.capture())
        self.generation += 1
        self.trial_id = str(uuid4())
        self._tokens = {role: secrets.token_urlsafe(32) for role in ROLES}
        self._clock = self._start
        self._objects = {}
        self._keys = {}
        self._controller_keys = {}
        self._controller_token = secrets.token_urlsafe(32)
        self._approval_bounds = {}
        self._approvals = {}
        self._reservations = {}
        self._committed = 0
        self._settled = 0
        self._events = []
        self._transitions = 0
        self._revisions = {}
        return {"trial_id": self.trial_id, "generation": self.generation}

    def credential(self, role):
        if role not in ROLES:
            raise ValueError("Unknown role")
        return self._tokens[role]

    def _event(self, operation, role, status):
        event = {
            "trial_id": self.trial_id,
            "generation": self.generation,
            "index": len(self._events),
            "operation": operation,
            "role": role,
            "status": status,
            "simulation_time": self._clock,
        }
        self._events.append(event)
        self.audit.append(deepcopy(event))

    def _deny(self, operation, role, code):
        self._event(operation, role, code)
        return {"status": "denied", "code": code, "paid_calls": False}

    def call(self, role_token, generation, operation, body):
        role = (
            next(
                (r for r, t in self._tokens.items() if secrets.compare_digest(t, role_token)), None
            )
            if type(role_token) is str
            else None
        )
        if role is None or generation != self.generation or type(generation) is not int:
            return self._deny(
                operation if type(operation) is str else "invalid",
                role,
                "wrong_trial_or_generation",
            )
        if type(body) is not dict or type(operation) is not str or len(str(body)) > 65536:
            return self._deny("invalid", role, "invalid_request")
        self._transitions += 1
        if self._transitions > 1000:
            return self._deny(operation, role, "transition_limit")
        if operation == "context":
            return {
                "profile": VERSION,
                "trial_id": self.trial_id,
                "generation": self.generation,
                "role": role,
                "clock": self._clock,
                "locale": "en-US",
                "paid_calls": False,
            }
        if operation == "evidence":
            allowed = {
                "questions",
                "documents",
                "search",
                "reports",
                "campaigns",
                "content",
                "work",
                "budget-envelopes",
                "ledger",
            }
            collection = body.get("collection")
            if type(collection) is not str or collection not in allowed:
                return self._deny(operation, role, "prohibited_collection")
            # Only loader-created, explicitly public projections may enter this map.
            visible = []
            for record in self._initial.get(collection, []):
                if (
                    record.get("actor_visible") is True
                    and timestamp(record["released_at"]) <= timestamp(self._clock)
                    and record.get("outcome_binding") in (None, self._outcome)
                ):
                    visible.append(deepcopy(record["public"]))
            self._event(operation, role, "read")
            return {"records": visible, "status": "released_evidence_only"}
        if operation == "get":
            key = body.get("id")
            if type(key) is not str or key not in self._objects:
                return self._deny(operation, role, "object_not_found")
            from anvil.marketing_task2_contract import WIRE_ROLES

            owned = self._objects[key]["created_by_role"] == role
            assigned = any(
                h["kind"] == "handoffs"
                and WIRE_ROLES.get(h["content"].get("recipient_role")) == role
                and any(
                    r.get("id") == key
                    and r.get("version") == self._objects[key]["version"]
                    and r.get("sha256") == digest(self._objects[key])
                    for r in h["content"].get("artifact_refs", [])
                    if isinstance(r, dict)
                )
                for h in self._objects.values()
            )
            if not owned and not assigned:
                return self._deny(operation, role, "unassigned_object")
            return deepcopy(self._objects[key])
        if operation not in WRITERS:
            return self._deny(operation, role, "controller_or_private_operation")
        if WRITERS[operation] is not None and WRITERS[operation] != role:
            return self._deny(operation, role, "role_scope")
        if set(body) != {"id", "expected_version", "idempotency_key", "content"}:
            return self._deny(operation, role, "typed_versioned_write_required")
        key, version, idem, content = (
            body[k] for k in ("id", "expected_version", "idempotency_key", "content")
        )
        if (
            type(key) is not str
            or not 1 <= len(key) <= 100
            or type(version) is not int
            or type(idem) is not str
            or not 1 <= len(idem) <= 200
            or type(content) is not dict
        ):
            return self._deny(operation, role, "invalid_write")
        fingerprint = digest({"operation": operation, "body": body})
        cached = self._keys.get((role, idem))
        if cached:
            return (
                deepcopy(cached[1])
                if cached[0] == fingerprint
                else self._deny(operation, role, "idempotency_conflict")
            )
        old = self._objects.get(key)
        if old and (old["kind"] != operation or old["created_by_role"] != role):
            return self._deny(operation, role, "object_scope")
        if version != (old["version"] if old else 0):
            return self._deny(operation, role, "stale_version")
        if old and self._revisions.get(key, 0) >= 2:
            return self._deny(operation, role, "revision_limit_escalate")
        result = {
            "id": key,
            "version": version + 1,
            "kind": operation,
            "content": deepcopy(content),
            "created_by_role": role,
            "simulation_only": True,
        }
        self._objects[key] = result
        if old:
            self._revisions[key] = self._revisions.get(key, 0) + 1
        self._keys[(role, idem)] = (fingerprint, deepcopy(result))
        self._event(operation, role, "recorded")
        return deepcopy(result)

    def advance(self, instant):
        if timestamp(instant) < timestamp(self._clock):
            raise ValueError("Clock cannot go backwards")
        self._clock = instant

    def decide(self, request_id, version, *, approved, amount_bound):
        if type(approved) is not bool:
            raise ValueError("Explicit simulated decision required")
        request = self._objects.get(request_id)
        if not request or request["kind"] != "approval-requests" or request["version"] != version:
            raise ValueError("Exact approval request version required")
        if type(amount_bound) is not int or not 0 <= amount_bound <= self._budget:
            raise ValueError("Explicit simulated approval budget bound required")
        self._approvals[(request_id, version)] = approved
        self._approval_bounds[(request_id, version)] = amount_bound
        self._event("simulated_approval", None, "approved" if approved else "rejected")

    def reserve(self, request_id, version, amount):
        if self._approvals.get((request_id, version)) is not True:
            raise ValueError("Exact simulated approval required")
        if self._objects[request_id]["version"] != version:
            raise ValueError("Approval invalidated by revision")
        if type(amount) is not int or amount <= 0:
            raise ValueError("Positive integer minor units required")
        if amount > self._approval_bounds[(request_id, version)]:
            raise ValueError("Reservation exceeds approved request scope")
        key = (request_id, version)
        if key in self._reservations:
            if self._reservations[key] != amount:
                raise ValueError("Reservation conflict")
            return
        if amount > self._budget - self._committed - self._settled - sum(
            self._reservations.values()
        ):
            raise ValueError("Insufficient available authority")
        self._reservations[key] = amount

    def convert(self, request_id, version, amount):
        key = (request_id, version)
        if type(amount) is not int or amount <= 0 or amount > self._reservations.get(key, 0):
            raise ValueError("Cannot convert more than reserved")
        self._reservations[key] -= amount
        self._committed += amount

    def settle(self, amount):
        if type(amount) is not int or not 0 < amount <= self._committed:
            raise ValueError("Settlement exceeds commitment")
        self._committed -= amount
        self._settled += amount

    def release(self, request_id, version):
        self._reservations.pop((request_id, version), None)

    def controller_credential(self):
        """Trusted host only; never part of context, role credentials or capture."""
        return self._controller_token

    def complete_forecast(self, request_id, version, source_ref):
        """Host completion from an actually released, exact-request fixture.

        This is a simulated forecast service. Missing/unreleased/unmatched
        fixtures cannot become an empty successful prediction.
        """
        request = self._objects.get(request_id)
        if not request or request["kind"] != "forecast-requests" or request["version"] != version:
            raise ValueError("Exact current forecast request version required")
        source = next(
            (
                entry
                for entry in self._initial.get("forecasts", [])
                if entry.get("actor_visible") is True
                and entry.get("outcome_binding") in (None, self._outcome)
                and timestamp(entry["released_at"]) <= timestamp(self._clock)
                and entry["public"].get("id") == source_ref
                and entry["public"].get("request_sha256") == digest(request)
            ),
            None,
        )
        if source is None or not isinstance(source["public"].get("forecast"), dict):
            raise ValueError("Released forecast fixture bound to this exact request required")
        key = "anvil-forecast-result:" + digest({"id": request_id, "version": version})
        value = {
            "id": key,
            "version": 1,
            "kind": "forecast-results",
            "created_by_role": None,
            "content": {
                "request_id": request_id,
                "request_version": version,
                "request_sha256": digest(request),
                "source_ref": source_ref,
                "forecast": deepcopy(source["public"]["forecast"]),
            },
            "simulation_only": True,
        }
        if key in self._objects and self._objects[key] != value:
            raise ValueError("Immutable forecast completion differs")
        self._objects[key] = value

    def control(self, token, generation, operation, body, *, idempotency_key):
        if (
            type(token) is not str
            or not secrets.compare_digest(token, self._controller_token)
            or type(generation) is not int
            or generation != self.generation
        ):
            return self._deny("controller", None, "controller_auth_failed")
        if (
            type(body) is not dict
            or type(idempotency_key) is not str
            or not 1 <= len(idempotency_key) <= 200
        ):
            raise ValueError("Bounded controller body and idempotency key required")
        fields = {
            "advance": {"instant"},
            "decide": {"request_id", "version", "approved", "amount_bound"},
            "reserve": {"request_id", "version", "amount"},
            "convert": {"request_id", "version", "amount"},
            "settle": {"amount"},
            "release": {"request_id", "version"},
            "complete_forecast": {"request_id", "version", "source_ref"},
        }
        if operation not in fields or set(body) != fields[operation]:
            raise ValueError("Exact controller operation schema required")
        fingerprint = digest({"operation": operation, "body": body})
        prior = self._controller_keys.get(idempotency_key)
        if prior:
            if prior[0] != fingerprint:
                raise ValueError("Controller idempotency conflict")
            return deepcopy(prior[1])
        getattr(self, operation)(**body)
        self._event("controller_" + operation, None, "applied")
        result = {"status": "applied", "generation": self.generation, "simulation_only": True}
        self._controller_keys[idempotency_key] = (fingerprint, deepcopy(result))
        return result

    def capture(self):
        # Controller-only private evaluation capture, not a public actor response.
        return {
            "trial_id": self.trial_id,
            "generation": self.generation,
            "clock": self._clock,
            "objects": deepcopy(self._objects),
            "events": deepcopy(self._events),
            "finance": {
                "reserved": sum(self._reservations.values()),
                "committed": self._committed,
                "settled": self._settled,
            },
            "origin": "synthetic_software",
            "paid_calls": False,
        }
