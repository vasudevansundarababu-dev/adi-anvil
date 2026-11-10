"""Strict owned-resource admission and cleanup receipts for the approved QA host.

Pure functions: callers must read back exact IDs before any mutation. Names or
prefixes alone never authorize cleanup. No billing API delay is treated as a cap.
"""

from datetime import datetime, timedelta, timezone

PROJECT = "adi-anvil-mvp-2026"
NAME = "anvil-overnight-qa-20261110"
STOP = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
DELETE = STOP + timedelta(hours=48)


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    return parsed.astimezone(timezone.utc)


def validate_vm(vm, *, now):
    """Require actual Compute readback, not locally invented scheduling proof."""
    if now.tzinfo is None or now >= STOP:
        raise ValueError("QA execution window expired")
    prefix = f"https://www.googleapis.com/compute/v1/projects/{PROJECT}/"
    if (
        vm.get("name") != NAME
        or not str(vm.get("id", "")).isdecimal()
        or vm.get("selfLink") != prefix + "zones/us-west1-a/instances/" + NAME
        or vm.get("machineType") != prefix + "zones/us-west1-a/machineTypes/e2-standard-8"
        or vm.get("serviceAccounts")
        or vm.get("labels", {}).get("purpose") != "overnight-qa"
    ):
        raise ValueError("Unexpected QA host identity or authority")
    scheduling = vm.get("scheduling", {})
    if (
        scheduling.get("automaticRestart") is not False
        or scheduling.get("instanceTerminationAction") != "STOP"
        or timestamp(scheduling.get("terminationTime", "")) != STOP
    ):
        raise ValueError("Verified absolute automatic STOP is required")
    interfaces = vm.get("networkInterfaces", [])
    if (
        len(interfaces) != 1
        or interfaces[0].get("accessConfigs")
        or interfaces[0].get("network") != prefix + "global/networks/" + NAME + "-net"
        or interfaces[0].get("subnetwork") != prefix + "regions/us-west1/subnetworks/" + NAME + "-subnet"
    ):
        raise ValueError("QA host must have exactly one private interface")
    disks = vm.get("disks", [])
    if (
        len(disks) != 1
        or disks[0].get("source") != prefix + "zones/us-west1-a/disks/" + NAME + "-boot"
    ):
        raise ValueError("Unexpected QA disk attachment")
    return {
        "vm_id": str(vm["id"]),
        "vm_self_link": vm["selfLink"],
        "stop_at": STOP.isoformat(),
        "delete_not_before": DELETE.isoformat(),
    }


def cleanup_admission(ledger, readback, *, now):
    if now.tzinfo is None or now < DELETE:
        raise ValueError("QA retention period has not elapsed")
    if not ledger or len(ledger) > 12:
        raise ValueError("Exact bounded resource ledger required")
    if len({entry["selfLink"] for entry in ledger}) != len(ledger):
        raise ValueError("Duplicate resource identity")
    if set(readback) != {entry["selfLink"] for entry in ledger}:
        raise ValueError("Readback must cover exactly the owned resource ledger")
    for entry in ledger:
        link = entry["selfLink"]
        current = readback[link]
        if (
            not link.startswith(f"https://www.googleapis.com/compute/v1/projects/{PROJECT}/")
            or entry.get("name")
            not in {
                NAME + suffix
                for suffix in ("", "-boot", "-net", "-subnet", "-iap", "-router", "-nat-ip")
            }
            or link.rsplit("/", 1)[-1] != entry["name"]
            or not str(entry.get("id", "")).isdecimal()
            or current.get("id") != entry["id"]
            or current.get("selfLink") != link
        ):
            raise ValueError("Cleanup refused: resource identity changed or unowned")
    return tuple(entry["selfLink"] for entry in ledger)
