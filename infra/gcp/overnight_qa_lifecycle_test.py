from copy import deepcopy
from datetime import timedelta

import pytest
from overnight_qa_lifecycle import DELETE, NAME, PROJECT, STOP, cleanup_admission, validate_vm


def vm():
    prefix = f"https://www.googleapis.com/compute/v1/projects/{PROJECT}/zones/us-west1-a/"
    return {
        "name": NAME,
        "id": "123",
        "selfLink": prefix + "instances/" + NAME,
        "machineType": prefix + "machineTypes/e2-standard-8",
        "labels": {"purpose": "overnight-qa"},
        "scheduling": {
            "automaticRestart": False,
            "instanceTerminationAction": "STOP",
            "terminationTime": STOP.isoformat(),
        },
        "networkInterfaces": [{"networkIP": "10.0.0.2", "network": f"https://www.googleapis.com/compute/v1/projects/{PROJECT}/global/networks/{NAME}-net", "subnetwork": f"https://www.googleapis.com/compute/v1/projects/{PROJECT}/regions/us-west1/subnetworks/{NAME}-subnet"}],
        "disks": [{"source": prefix + "disks/" + NAME + "-boot"}],
    }


def test_readback_is_required_before_host_execution():
    assert validate_vm(vm(), now=STOP - timedelta(hours=1))["vm_id"] == "123"
    for field, value in (
        ("name", "anvil-mvp-v1"),
        ("serviceAccounts", [{"email": "owner"}]),
        ("networkInterfaces", [{"accessConfigs": [{}]}]),
        ("scheduling", {}),
        ("disks", []),
    ):
        changed = deepcopy(vm())
        changed[field] = value
        with pytest.raises(ValueError):
            validate_vm(changed, now=STOP - timedelta(hours=1))
    with pytest.raises(ValueError):
        validate_vm(vm(), now=STOP)


def test_cleanup_requires_retention_and_exact_ids_not_names():
    original = vm()
    entry = {key: original[key] for key in ("id", "name", "selfLink")}
    readback = {entry["selfLink"]: original}
    assert cleanup_admission([entry], readback, now=DELETE) == (entry["selfLink"],)
    with pytest.raises(ValueError):
        cleanup_admission([entry], readback, now=DELETE - timedelta(seconds=1))
    changed = deepcopy(readback)
    changed[entry["selfLink"]]["id"] = "456"
    with pytest.raises(ValueError):
        cleanup_admission([entry], changed, now=DELETE)
    with pytest.raises(ValueError):
        cleanup_admission([entry], {}, now=DELETE)
