"""Explicit KYC input-preparation B0 to package-selecting Run binding B1.

This comparison never qualifies a project or changes an immutable binding.
Models/run controls still require their separate actual admission checks.
"""

from copy import deepcopy

from anvil.campaign_semantic_contract import bounded_json
from anvil.db import digest


def execution_projection(snapshot):
    bounded_json(snapshot, 1048576, max_nodes=100000, max_depth=24)
    if type(snapshot) is not dict or type(snapshot.get("workflow")) is not list:
        raise ValueError("Exact original KYC preparation binding required")
    value = deepcopy(snapshot)
    workflow = value["workflow"]
    if any(type(ref) is not dict or type(ref.get("kind")) is not str for ref in workflow):
        raise ValueError("Exact typed workflow references required")
    value["workflow"] = [ref for ref in workflow if ref["kind"] != "package"]
    return value


def verify_transition(original, current, package_refs):
    """Allow only exact package-reference additions over the complete projection.

    No selected-field match, latest-binding substitution or inherited review.
    Removing an old package, changing any source/data/environment/policy/evaluator/
    method/safety field, or selecting an unexpected package is rejected.
    """
    if type(package_refs) is not tuple or not 1 <= len(package_refs) <= 200:
        raise ValueError("Exact planned KYC package reference population required")
    expected = set()
    for ref in package_refs:
        if type(ref) is not dict or set(ref) != {"kind", "id", "sha256", "target"} or ref["kind"] != "package":
            raise ValueError("Exact original KYC package reference required")
        pin = digest(ref)
        if pin in expected:
            raise ValueError("Duplicate package binding")
        expected.add(pin)
    if execution_projection(original) != execution_projection(current):
        raise ValueError("KYC execution-relevant binding changed; prepare new input/packages")
    old = {digest(ref) for ref in original["workflow"] if ref["kind"] == "package"}
    new = {digest(ref) for ref in current["workflow"] if ref["kind"] == "package"}
    if (len(new) != sum(ref["kind"] == "package" for ref in current["workflow"])
            or not old <= new or new != old | expected):
        raise ValueError("Run binding must add only the exact planned KYC packages")
    return {"kind": "kyc_preparation_to_run_binding", "original_execution_sha256": digest(execution_projection(original)),
            "current_execution_sha256": digest(execution_projection(current)), "package_reference_additions_only": True,
            "ready": False, "run_authority": "not_granted"}


def verify_packages(connection, project, current, packages):
    """Read the actual immutable B0; never substitute a latest preparation."""
    from anvil.db import one

    bindings = [(package["manifest"].get("native_binding") or {}) for package in packages]
    product = [binding for binding in bindings if binding.get("task_mode") == "reusable_application_workflow"]
    if not product:
        return None
    if not 1 <= len(product) <= 4 or len(product) != len(bindings):
        raise ValueError("One to four exact product-task packages required")
    selectors = [binding.get("case_selector") or {} for binding in product]
    if (any(selector.get("field") != "product" or selector.get("value") not in
            {"individual", "adult_joint", "teen_joint", "custodial"} for selector in selectors)
            or len({selector["value"] for selector in selectors}) != len(selectors)
            or len({str(package["id"]) for package in packages}) != len(packages)):
        raise ValueError("Distinct product identities required")
    parents = {(binding.get("preparation_binding_id"), binding.get("preparation_binding_sha256")) for binding in product}
    inputs = {digest(binding.get("resolved_input")) for binding in product}
    if len(parents) != 1 or len(inputs) != 1:
        raise ValueError("Product packages must retain one original preparation/input")
    identifier, fingerprint = next(iter(parents))
    original = one(connection, "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND id=%s", (project, identifier))
    if (not original or original["snapshot_sha256"] != fingerprint or digest(original["snapshot"]) != fingerprint
            or original["task_group_id"] != current["task_group_id"]
            or digest(current["snapshot"]) != current["snapshot_sha256"]):
        raise ValueError("Exact immutable preparation ancestry changed")
    selected = {(str(package["id"]), package["package_sha256"]) for package in packages}
    refs = tuple(ref for ref in current["snapshot"]["workflow"] if ref["kind"] == "package"
                 and (str(ref["id"]), ref["sha256"]) in selected)
    if len(refs) != len(packages):
        raise ValueError("Current binding must explicitly select each product package")
    return verify_transition(original["snapshot"], current["snapshot"], refs)
