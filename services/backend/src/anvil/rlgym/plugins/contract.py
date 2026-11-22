"""The verifier plug-in contract (shared/VERIFIER-PLUGINS.md section 1; D22): manifest checks, the settings-schema
subset Studio's forms use, and RFC 8785 canonical JSON for file hashes."""

import hashlib
import json
import math
import re

from anvil.rlgym.common import GymError

MANIFEST = "adi.verifier-plugin.v1"
JOB = "adi.verifier-job.v1"
RESULT = "adi.verifier-result.v1"
READS = ("state", "tools", "output", "case", "case_reference", "slots")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
IMAGE = re.compile(r"^(sha256:[0-9a-f]{64}|[a-z0-9./_-]+(:[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64})$")
VERDICTS = ("pass", "fail", "blocked")


# --- RFC 8785 (JCS) ------------------------------------------------------------------------------------------------


def _number(x):
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if not math.isfinite(x):
        raise ValueError("JCS has no NaN or Infinity")
    if x == 0:
        return "0"
    if x.is_integer() and abs(x) < 1e21:
        return str(int(x))
    # ECMAScript Number.prototype.toString from the shortest round-trip digits.
    r = repr(abs(x))
    if "e" in r:
        digits, e = r.split("e")
        e = int(e)
    else:
        digits, e = r, None
    if "." in digits:
        whole, frac = digits.split(".")
    else:
        whole, frac = digits, ""
    if e is None:
        # place the decimal point: exponent of the first significant digit
        if whole != "0":
            e = len(whole) - 1
            sig = (whole + frac).rstrip("0")
        else:
            stripped = frac.lstrip("0")
            e = -(len(frac) - len(stripped) + 1)
            sig = stripped.rstrip("0")
    else:
        sig = (whole + frac).rstrip("0")
    sig = sig.lstrip("0") or "0"
    k, n = len(sig), e + 1
    sign = "-" if x < 0 else ""
    if k <= n <= 21:
        return sign + sig + "0" * (n - k)
    if 0 < n <= 21:
        return sign + sig[:n] + "." + sig[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + sig
    exp_s = f"{'+' if n - 1 >= 0 else '-'}{abs(n - 1)}"
    return sign + (sig[0] + ("." + sig[1:] if k > 1 else "")) + "e" + exp_s


def jcs(value):
    """RFC 8785 canonical JSON bytes (keys sorted by UTF-16 code units, ECMAScript numbers, minimal escapes)."""
    if value is None:
        return "null"
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(jcs(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        return (
            "{"
            + ",".join(json.dumps(k, ensure_ascii=False) + ":" + jcs(value[k]) for k in keys)
            + "}"
        )
    raise ValueError(f"not JSON: {type(value).__name__}")


def jcs_sha256(value):
    return hashlib.sha256(jcs(value).encode()).hexdigest()


# --- settings schema (the subset Studio's S7 forms use) -------------------------------------------------------------

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "null": type(None),
}


def schema_errors(schema, value, path="settings"):
    """Errors for `value` against a JSON Schema subset: type, enum, const, required, properties,
    additionalProperties (bool or schema), items, minItems, minLength, minimum, maximum. Other keywords are
    annotations (title, description, default, x-widget) and ignored."""
    errors = []
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        ok = any(
            isinstance(value, _TYPES[x])
            and not (x in ("integer", "number") and isinstance(value, bool))
            for x in types
            if x in _TYPES
        )
        if not ok:
            return [f"{path}: expected {'/'.join(types)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}")
    if isinstance(value, dict):
        for key in schema.get("required") or []:
            if key not in value:
                errors.append(f"{path}.{key}: required")
        props = schema.get("properties") or {}
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                errors += schema_errors(props[key], item, f"{path}.{key}")
            elif extra is False:
                errors.append(f"{path}.{key}: not allowed")
            elif isinstance(extra, dict):
                errors += schema_errors(extra, item, f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: at least {schema['minItems']} items")
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                errors += schema_errors(schema["items"], item, f"{path}[{i}]")
    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: at least {schema['minLength']} characters")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: at most {schema['maximum']}")
    return errors


# --- manifest ---------------------------------------------------------------------------------------------------


def check_manifest(m):
    problems = []
    if not isinstance(m, dict) or m.get("schema") != MANIFEST:
        raise GymError("VALIDATION_FAILED", f"schema must be {MANIFEST}")
    if not ID.match(str(m.get("id", ""))):
        problems.append("id: lower-case letters, digits and hyphens")
    if not SEMVER.match(str(m.get("version", ""))):
        problems.append("version: semantic version (x.y.z)")
    if not IMAGE.match(str(m.get("image", ""))):
        problems.append(
            "image: pinned by digest (sha256:<id> or name@sha256:<digest>), never a tag"
        )
    ep = m.get("entrypoint")
    if not (isinstance(ep, list) and ep and all(isinstance(x, str) and x for x in ep)):
        problems.append("entrypoint: a non-empty list of strings")
    if (
        not isinstance(m.get("settings_schema"), dict)
        or m["settings_schema"].get("type") != "object"
    ):
        problems.append("settings_schema: a JSON Schema for an object")
    reads = m.get("reads")
    if not (isinstance(reads, list) and reads and set(reads) <= set(READS)):
        problems.append(f"reads: some of {list(READS)}")
    if not isinstance(m.get("calls_model"), bool):
        problems.append("calls_model: true or false")
    t = m.get("timeout_seconds")
    if not (isinstance(t, int) and 1 <= t <= 120):
        problems.append("timeout_seconds: 1 to 120")
    cases = m.get("known_cases")
    if not (isinstance(cases, list) and len(cases) >= 3):
        problems.append("known_cases: three or more")
    else:
        expects = {c.get("expect") for c in cases}
        if not {"pass", "fail", "blocked"} <= expects:
            problems.append("known_cases: at least one pass, one fail and one blocked")
        for c in cases:
            if not isinstance(c.get("job"), dict) or c.get("expect") not in VERDICTS:
                problems.append(
                    f"known case {c.get('name')!r}: a job and an expect of pass, fail or blocked"
                )
    if problems:
        raise GymError(
            "VALIDATION_FAILED", "The plug-in manifest is not valid", {"problems": problems}
        )
    return m
