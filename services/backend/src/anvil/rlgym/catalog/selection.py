"""Selection rules (SPEC 07.0a, REGISTRY.md §3-4, D20).

Environment aliases: Pinned · version, Same data · seed family, Latest. Criteria: Latest qualified or Pinned.
A version is selectable only when the registry says qualified AND the RL Gym's own latest qualification of it did
not fail (a failed re-qualification stops selection at once, before the registry reacts).
"""


def selectable_environments(c, contract_id, allow_test=False):
    """Qualified versions of the contract. `allow_test` (a test-only project only): also Studio's test-channel
    candidates (registry channel "test", never qualified) under the contract's key or its `-test` key."""
    test_part = (
        """ OR (v.channel='test' AND v.contract_id IN (%s, %s)
                AND v.state NOT IN ('revoked','deleted','failed'))"""
        if allow_test
        else ""
    )
    return c.execute(
        """SELECT v.*, r.result AS last_qualification, r.failure_class AS last_failure_class, r.receipt_id AS last_receipt_id
           FROM catalog.environment_versions v
           LEFT JOIN LATERAL (SELECT result, failure_class, receipt_id FROM catalog.qualification_receipts q
                              WHERE q.subject_kind='environment_version' AND q.subject_id=v.id
                              ORDER BY issued_at DESC LIMIT 1) r ON true
           WHERE ((v.contract_id=%s AND v.state='qualified' AND coalesce(r.result,'qualified')='qualified'
                   AND v.channel IS NULL AND v.contract_id NOT LIKE '%%-test')"""
        + test_part
        + """)
           ORDER BY v.version DESC, v.mirrored_at DESC""",
        (contract_id, contract_id, f"{contract_id}-test") if allow_test else (contract_id,),
    ).fetchall()


def project_allows_test(c, rule):
    """A project's selection rule may bind Studio's test channel only when its project is test_only."""
    if not (rule.get("project_id") and rule.get("workspace_id")):
        return False
    row = c.execute(
        "SELECT test_only FROM projects.projects WHERE workspace_id=%s AND project_id=%s",
        (rule["workspace_id"], rule["project_id"]),
    ).fetchone()
    return bool(row and row["test_only"])


def resolve_environment(c, rule, allow_test=None):
    """→ (version row or None, condition code or None, reason). `allow_test`: a test-only project's rule; when not
    given, a project's rule follows its project's test_only flag (import binding, reselection, project state)."""
    if allow_test is None:
        allow_test = project_allows_test(c, rule)
    versions = selectable_environments(c, rule["contract_id"], allow_test)
    if not versions:
        return None, "B2", f"No qualified version of {rule['contract_id']}"
    kind = rule["kind"]
    if kind == "pinned":
        pick = next((v for v in versions if v["id"] == rule["pinned_version_id"]), None)
        if pick:
            return pick, None, "pinned"
        return (
            None,
            "B1",
            f"Pinned {rule['pinned_version_id']} is not qualified (revoked, failed or deprecated)",
        )
    if kind == "same_data":
        pick = next((v for v in versions if v["seed_family"] == rule["seed_family"]), None)
        if pick:
            return pick, None, "same data"
        return None, "B3", f"No qualified version in seed family {rule['seed_family']}"
    return versions[0], None, "latest"


def rule_label(rule):
    if rule["kind"] == "pinned":
        return f"Pinned · {short(rule['pinned_version_id'])}"
    if rule["kind"] == "same_data":
        return f"Same data · {rule['seed_family']}"
    if rule["kind"] == "latest_qualified":
        return "Latest qualified"
    return "Latest"


def short(version_id):
    if not version_id:
        return "nothing"
    return version_id.replace("@", " ")


def selectable_configurations(c, ws, configuration_id):
    return c.execute(
        """SELECT e.*, f.state AS framework_state FROM catalog.evaluator_configurations e
           JOIN catalog.framework_versions f ON f.id=e.framework_version_id
           WHERE e.workspace_id=%s AND e.id=%s AND e.state='qualified' AND f.state NOT IN ('revoked')
           ORDER BY e.version DESC""",
        (ws, configuration_id),
    ).fetchall()


def resolve_evaluator(c, ws, rule):
    versions = selectable_configurations(c, ws, rule["configuration_id"])
    if rule["kind"] == "pinned":
        pick = next((v for v in versions if v["version"] == rule["pinned_version"]), None)
        if pick:
            return pick, None, "pinned"
        return (
            None,
            "B4",
            f"Pinned {rule['configuration_id']} v{rule['pinned_version']} is not qualified",
        )
    if not versions:
        return None, "B4", f"No qualified version of {rule['configuration_id']}"
    return versions[0], None, "latest qualified"
