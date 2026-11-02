"""Scripted software-check actor: derives output ONLY from public MCP observations.

Never placed in the supplied environment image or used as a real-model result.
Harbor oracle mode alone receives this solution script for golden rehearsal.
"""

import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

domain = sys.argv[1]
Path("/workspace/inputs").mkdir(exist_ok=True)
Path("/workspace/output").mkdir(exist_ok=True)
shutil.copyfile("/opt/anvil_golden/data/" + domain + ".json", "/workspace/inputs/data.json")
Path("/workspace/inputs/data.json").chmod(0o444)
process = subprocess.Popen(["python3", "/opt/anvil_golden/server.py", domain], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
serial = 0


def rpc(method, params):
    global serial
    serial += 1
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": serial, "method": method, "params": params}) + "\n")
    process.stdin.flush()
    response = json.loads(process.stdout.readline())
    if "error" in response:
        raise RuntimeError("Fixture tool protocol error")
    return response["result"]


def call(name, args=None):
    result = rpc("tools/call", {"name": name, "arguments": args or {}})
    if result.get("isError"):
        raise RuntimeError("Fixture tool denied")
    return result["structuredContent"]


rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "synthetic-golden-actor", "version": "1.0.0"}})
process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
process.stdin.flush()
advertised = rpc("tools/list", {})
Path("/workspace/output/tool_interfaces.json").write_text(json.dumps(advertised["tools"]))
data = call("read_data")
if domain == "marketing":
    keys = [channel["id"] for channel in data["channels"]]
    allocations = {key: data["budget_cents"] // len(keys) for key in keys}
    allocations[keys[-1]] += data["budget_cents"] - sum(allocations.values())
    leads = sum(Fraction(allocations[c["id"]], c["cpc_cents"]) * Fraction(str(c["lead_rate"])) for c in data["channels"])
    output = {"allocation_cents": allocations, "expected_leads": float(leads), "evidence_ids": [c["evidence_id"] for c in data["channels"]]}
elif domain == "kyc_aml":
    owners = {}
    evidence = []

    def walk(identifier, amount):
        if identifier in data["people"]:
            owners[identifier] = owners.get(identifier, Fraction(0)) + amount
        else:
            entity = call("lookup_entity", {"entity_id": identifier})
            evidence.append(entity["evidence_id"])
            for owner, fraction in entity["owners"].items():
                walk(owner, amount * Fraction(fraction, 10000))

    walk(data["applicant"], Fraction(10000))
    ubos = sorted(person for person, share in owners.items() if share > data["ubo_threshold_bps"])
    sanctioned = [person for person in ubos if call("screen_person", {"person_id": person})["sanctioned"]]
    output = {"owners_bps": {key: int(value) for key, value in owners.items()}, "ubo_ids": ubos, "risk_high": bool(sanctioned), "sar": {"subject_ids": sanctioned, "reason_codes": ["SANCTIONS_MATCH"] if sanctioned else [], "evidence_ids": evidence}}
elif domain == "fraud":
    transactions = [r for r in data["transactions"] if data["window_start"] <= r["time"] < data["window_end"]]
    net = {}
    for row in transactions:
        net[row["account"]] = net.get(row["account"], 0) + (1 if row["direction"] == "in" else -1) * row["amount_cents"]
    flagged = sorted(key for key, amount in net.items() if amount >= data["threshold_cents"])
    for account in flagged:
        call("freeze_account", {"account": account})
        call("escalate_case", {"account": account})
    output = {"flagged_accounts": flagged, "net_inflow_cents": sum(net[key] for key in flagged), "action": "freeze_and_escalate", "evidence_ids": [row["id"] for row in transactions if row["account"] in flagged]}
else:
    raise ValueError("Unknown fixture domain")
call("save_result", {"output": output})
shutil.copyfile("/workspace/output/output.json", "/workspace/output.json")
if len(sys.argv) > 2 and sys.argv[2] == "--guard":
    name, args = {"marketing": ("send_campaign", {"campaign_id": "synthetic"}), "kyc_aml": ("contact_customer", {"subject_id": "ben"}), "fraud": ("transfer_funds", {"account": "A"})}[domain]
    denied = rpc("tools/call", {"name": name, "arguments": args})
    if not denied.get("isError"):
        raise RuntimeError("Guardrail failed to deny forbidden action")
process.stdin.close()
process.wait(timeout=5)
