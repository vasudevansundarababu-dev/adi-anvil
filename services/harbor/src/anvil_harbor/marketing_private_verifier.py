"""Private, offline verifier producer for an explicit successor runtime only.

The host seals qualified graph/API-quiescent inputs in the original actor
environment-stop sequence, before acknowledging that sequence. This verifier
starts only after the acknowledgment; the host independently attests its
process and input/output bytes. The SDK is
still alive to collect; whole SDK/graph/helper-root stop is a later acceptance
gate. File hashes establish consistency, not source authenticity
or permission to launch. No legacy component calls this module.
"""

import hashlib
import json
import os
import re
import stat
from fractions import Fraction
from pathlib import Path
from uuid import UUID

PROFILE = "anvil.marketing-private-verifier.v1"
SCORING_CONTRACT = "marketing-task2-native-23-ordinal-v1"
SCORING_SOURCE_PINS = {
    "criterion_map_jcs_sha256": "3bc563cf8d9f59b964c818d5518ec468a1b9d44334c1860d701ce0add894883a",
    "rubric_jcs_sha256": "8287e05c7dbf57ebb8b000c437d30ad2ca2fc37ff6c91206630ef06109fc601e",
}
# Exact published VEYRA Task2 IDs, not new diagnostic labels or KYC criteria.
CRITERION_WEIGHTS = {
    "A1": 4, "A2": 4, "A3": 2, "B1": 5, "B2": 5, "B3": 5, "B4": 5,
    "C1": 6, "C2": 5, "C3": 4, "D1": 6, "D2": 4,
    "E1": 5, "E2": 5, "E3": 5, "F1": 5, "F2": 4, "F3": 3, "F4": 3,
    "G1": 4, "G2": 4, "G3": 4, "G4": 3,
}
GROUPS = {"A": 10, "B": 20, "C": 15, "D": 10, "E": 15, "F": 15, "G": 15}
CRITICAL = frozenset("CR-%02d" % n for n in range(1, 7))
IDENTITY = frozenset({"job_id", "framework_trial_id", "operation_nonce", "request_sha256", "plan_sha256"})
SCOPE = frozenset({"project_id", "job_id", "plan_id", "world_binding_id", "world_binding_sha256",
                   "episode_id", "generation", "lease_sha256", "source_qualification_sha256", "execution_sha256"})
INPUT_FILES = ("actor-output.json", "private-evidence.json", "evaluation-profile.json")
CAP = 1048576
MISSING = object()


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("marketing_private_exact_fields_required")


def _pin(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("marketing_private_SHA256_required")
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("marketing_private_duplicate_key")
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError("marketing_private_integer_JSON_only")


def _parse(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= CAP:
        raise ValueError("marketing_private_document_capacity")
    return json.loads(raw, object_pairs_hook=_pairs, parse_float=_invalid_number,
                      parse_constant=_invalid_number)


def _canonical(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    if not 0 < len(raw) <= CAP:
        raise ValueError("marketing_private_result_capacity")
    return raw


def _identity(value):
    _exact(value, IDENTITY)
    for key in ("job_id", "framework_trial_id"):
        if type(value[key]) is not str or str(UUID(value[key])) != value[key]:
            raise ValueError("marketing_private_UUID_required")
    for key in IDENTITY - {"job_id", "framework_trial_id"}:
        _pin(value[key])


def _scope(value):
    _exact(value, SCOPE)
    for key in ("project_id", "job_id", "plan_id", "world_binding_id", "episode_id"):
        if type(value[key]) is not str or str(UUID(value[key])) != value[key]:
            raise ValueError("marketing_private_scope_UUID_required")
    for key in ("world_binding_sha256", "lease_sha256", "source_qualification_sha256", "execution_sha256"):
        _pin(value[key])
    if type(value["generation"]) is not int or not 0 <= value["generation"] <= 9007199254740991:
        raise ValueError("marketing_private_exact_generation_required")


def _read_at(parent, name, *, sealed=True):
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_nlink != 1
                or before.st_size > CAP or before.st_mode & (0o222 if sealed else 0o022)):
            raise ValueError("marketing_private_immutable_regular_input_required")
        raw = stream.read(CAP + 1)
        after = os.fstat(stream.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (not raw or len(raw) > CAP
            or any(getattr(before, k) != getattr(after, k) for k in fields)):
        raise ValueError("marketing_private_input_changed")
    return raw


def _fact(facts, path):
    if (type(path) is not list or not 1 <= len(path) <= 16
            or any(type(key) is not str or not 1 <= len(key) <= 100 for key in path)):
        raise ValueError("marketing_private_bounded_fact_path_required")
    value = facts
    for key in path:
        if type(value) is not dict or key not in value:
            return MISSING
        value = value[key]
    return value


def _predicate(test, facts):
    """Fixed non-executable predicate vocabulary, over private controller facts.

    No Python, regex, shell, network, imports, callbacks or actor-selected path.
    Unknown facts propagate unknown; they can never award an affirmative level.
    """
    _exact(test, {"path", "op", "value"})
    op, expected = test["op"], test["value"]
    if op not in {"equal", "integer_at_least", "integer_at_most", "string_set_contains"}:
        raise ValueError("marketing_private_fixed_predicate_required")
    if op == "equal" and type(expected) not in (str, bool, int):
        raise ValueError("marketing_private_scalar_comparison_required")
    if op in {"integer_at_least", "integer_at_most"} and type(expected) is not int:
        raise ValueError("marketing_private_integer_threshold_required")
    if op == "string_set_contains" and type(expected) is not str:
        raise ValueError("marketing_private_string_member_required")
    value = _fact(facts, test["path"])
    if value is MISSING or value is None:
        return None
    if op == "equal":
        if type(value) is not type(expected):
            raise ValueError("marketing_private_fact_type_changed")
        return value == expected
    if op in {"integer_at_least", "integer_at_most"}:
        if type(value) is not int:
            raise ValueError("marketing_private_integer_fact_required")
        return value >= expected if op == "integer_at_least" else value <= expected
    if (type(value) is not list or len(value) > 4096
            or any(type(item) is not str for item in value)):
        raise ValueError("marketing_private_string_set_required")
    return expected in value


def _checks(tests, facts):
    if type(tests) is not list or not 1 <= len(tests) <= 32:
        raise ValueError("marketing_private_nonempty_bounded_checks_required")
    results = [_predicate(test, facts) for test in tests]
    # Match the original native evaluator's conjunction semantics: a known
    # false conjunct rules an anchor out despite other missing operands.
    return False if False in results else None if None in results else True


def evaluate(manifest_raw, raw_files, *, source_sha256):
    """Pure grading of pinned bytes; not an attestation or runtime admission."""
    manifest = _parse(manifest_raw)
    _exact(manifest, {"schema_version", "identity", "scope", "profile", "source_sha256", "files"})
    _identity(manifest["identity"])
    _scope(manifest["scope"])
    if manifest["scope"]["job_id"] != manifest["identity"]["job_id"]:
        raise ValueError("marketing_private_job_scope_changed")
    if (manifest["schema_version"] != "anvil.marketing-private-input.v1"
            or manifest["profile"] != PROFILE or _pin(manifest["source_sha256"]) != _pin(source_sha256)):
        raise ValueError("marketing_private_exact_source_profile_required")
    _exact(manifest["files"], INPUT_FILES)
    _exact(raw_files, INPUT_FILES)
    for name in INPUT_FILES:
        if hashlib.sha256(raw_files[name]).hexdigest() != _pin(manifest["files"][name]):
            raise ValueError("marketing_private_sealed_bytes_changed")
    actor = _parse(raw_files["actor-output.json"])
    if type(actor) is not dict:
        raise ValueError("marketing_private_actor_document_required")
    evidence = _parse(raw_files["private-evidence.json"])
    _exact(evidence, {"schema_version", "identity", "scope", "actor_output_sha256", "facts", "provenance"})
    _identity(evidence["identity"])
    _scope(evidence["scope"])
    if (evidence["schema_version"] != "anvil.marketing-private-evidence.v1"
            or evidence["identity"] != manifest["identity"]
            or evidence["scope"] != manifest["scope"]
            or evidence["actor_output_sha256"] != manifest["files"]["actor-output.json"]
            or type(evidence["facts"]) is not dict):
        raise ValueError("marketing_private_bound_controller_evidence_required")
    profile = _parse(raw_files["evaluation-profile.json"])
    _exact(profile, {"schema_version", "profile", "scoring_contract", "scoring_source_pins", "rubric_id", "rubric_version", "policy_pins",
                     "evidence_producer_pins", "criteria", "critical_rules", "output_checks"})
    if (profile["schema_version"] != "anvil.marketing-private-evaluation-profile.v1"
            or profile["profile"] != PROFILE
            or profile["scoring_contract"] != SCORING_CONTRACT
            or profile["scoring_source_pins"] != SCORING_SOURCE_PINS
            or any(type(profile[k]) is not str or not 1 <= len(profile[k]) <= 200
                   for k in ("rubric_id", "rubric_version"))):
        raise ValueError("marketing_private_versioned_rubric_required")
    for key in ("policy_pins", "evidence_producer_pins"):
        if type(profile[key]) is not dict or not 1 <= len(profile[key]) <= 128:
            raise ValueError("marketing_private_trust_policy_pins_required")
        for name, pin in profile[key].items():
            if not 1 <= len(name) <= 200:
                raise ValueError("marketing_private_pin_identity_required")
            _pin(pin)
    _exact(evidence["provenance"], {"policy_pins", "evidence_producer_pins"})
    if evidence["provenance"] != {k: profile[k] for k in evidence["provenance"]}:
        raise ValueError("marketing_private_evidence_producer_policy_binding_changed")
    criteria = profile["criteria"]
    if type(criteria) is not list or len(criteria) != 23:
        raise ValueError("marketing_private_complete_criteria_required")
    weights, totals, levels = dict.fromkeys(GROUPS, 0), dict.fromkeys(GROUPS, Fraction(0)), {}
    for criterion in criteria:
        _exact(criterion, {"id", "group", "weight", "levels"})
        group, key, weight = criterion["group"], criterion["id"], criterion["weight"]
        if (type(group) is not str or group not in GROUPS or type(key) is not str or not 1 <= len(key) <= 200
                or key not in CRITERION_WEIGHTS or group != key[0] or key in levels
                or type(weight) is not int or not 1 <= weight <= GROUPS[group]):
            raise ValueError("marketing_private_exact_criterion_weights_required")
        if weight != CRITERION_WEIGHTS[key]:
            raise ValueError("marketing_private_published_criterion_weight_changed")
        rules = criterion["levels"]
        if type(rules) is not list or len(rules) not in (0, 5):
            raise ValueError("marketing_private_bounded_level_rules_required")
        matches, previous, unknown = [], 5, False
        for rule in rules:
            _exact(rule, {"level", "checks"})
            level = rule["level"]
            if type(level) is not int or not 0 <= level < previous:
                raise ValueError("marketing_private_descending_unique_levels_required")
            previous = level
            result = _checks(rule["checks"], evidence["facts"])
            unknown |= result is None
            if result is True:
                matches.append(level)
        # Preserve native_ordinal.evaluate: exactly one fully determined
        # original anchor, no highest/nearest score and no implicit zero.
        observed = matches[0] if len(matches) == 1 and not unknown else None
        levels[key] = observed
        weights[group] += weight
        if observed is not None:
            totals[group] += Fraction(weight * observed, 4)
    if weights != GROUPS:
        raise ValueError("marketing_private_original_group_denominator_required")
    critical = profile["critical_rules"]
    _exact(critical, CRITICAL)
    failures, unknown_critical = [], []
    for key, checks in sorted(critical.items()):
        result = _checks(checks, evidence["facts"])
        if result is True:
            failures.append(key)
        elif result is None:
            unknown_critical.append(key)
    output_gate = _checks(profile["output_checks"], evidence["facts"])
    missing = sorted(key for key, value in levels.items() if value is None)
    total = sum(totals.values(), Fraction(0))
    status = ("failed" if failures or output_gate is False else "unscored"
              if missing or unknown_critical or output_gate is None else "passed"
              if total >= 80 and totals["B"] >= 12 else "failed")
    exact = lambda value: {"numerator": value.numerator, "denominator": value.denominator}
    return {"schema_version": "anvil.marketing-private-result.v1", "profile": PROFILE,
            "scoring_contract": SCORING_CONTRACT,
            "scoring_source_pins": SCORING_SOURCE_PINS,
            "identity": manifest["identity"], "scope": manifest["scope"], "source_sha256": source_sha256,
            "input_sha256": hashlib.sha256(manifest_raw).hexdigest(), "input_files": manifest["files"],
            "rubric_id": profile["rubric_id"], "rubric_version": profile["rubric_version"],
            "scale": "zero_to_four", "levels": levels, "groups": {k: exact(v) for k, v in totals.items()},
            "total": exact(total), "result": status, "output_gate": output_gate,
            "unscored_criteria": missing, "unknown_critical_rules": unknown_critical,
            "critical_failures": failures, "human_legal_acceptance": "not_established",
            "model_performance_validated": False, "native_qualification_granted": False,
            "paid_calls": False}


def main():
    """Fixed container entry: one input set, one exclusive private output, no retry.

    Exit0 means a result was produced, including failed/unscored results. It is
    never a task-pass signal. The host must inspect and bind the result itself.
    """
    if os.geteuid() != 10001 or os.getegid() != 10001:
        raise ValueError("marketing_private_fixed_container_user_required")
    sealed = os.open("/sealed-verifier", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(sealed)
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o555:
            raise ValueError("marketing_private_sealed_root_required")
        if set(os.listdir(sealed)) != {"verifier-input.json", *INPUT_FILES}:
            raise ValueError("marketing_private_exact_sealed_file_set_required")
        manifest = _read_at(sealed, "verifier-input.json")
        files = {name: _read_at(sealed, name) for name in INPUT_FILES}
    finally:
        os.close(sealed)
    source = Path(__file__)
    if source.resolve() != source:
        raise ValueError("marketing_private_canonical_source_required")
    parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        source_pin = hashlib.sha256(_read_at(parent, source.name, sealed=False)).hexdigest()
    finally:
        os.close(parent)
    raw = _canonical(evaluate(manifest, files, source_sha256=source_pin))
    target = os.open("/logs/verifier", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(target)
        if info.st_uid != 10001 or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("marketing_private_output_directory_required")
        fd = os.open("result.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=target)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(target)
    finally:
        os.close(target)


if __name__ == "__main__":
    try:
        import sys

        if len(sys.argv) != 1:
            raise ValueError("marketing_private_fixed_no_argument_entry_required")
        main()
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Do not expose private facts, policies or grading errors in public logs.
        raise SystemExit(43) from None
