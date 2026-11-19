"""Original synthetic arithmetic evaluator; no KYC/legal expectations."""


def evaluate(actual, expected):
    if "expected_status" in actual or "expected_status" in expected:
        raise ValueError("Host-only verdict leaked")
    reference = expected["criterion_reference"]
    if reference["schema_version"] != "anvil.synthetic-arithmetic-reference.v1":
        raise ValueError("Exact synthetic reference required")
    final = actual["final"]
    if not isinstance(final, dict):
        return {"status": "unscored"}
    if final.get("raise") is True:
        raise ValueError("Synthetic exception control")
    value = final.get("sum")
    if type(value) is not int:
        return {"status": "unscored"}
    distance = abs(value - sum(reference["addends"]))
    return {"status": "pass" if distance == 0 else "partial" if distance == 1 else "fail"}
