"""Model artifact contract and deterministic compiler. Never execute generated code here."""

import ast
import hashlib
import io
import json
import zipfile

from pydantic import Field, model_validator

from anvil.db import digest
from anvil.praxis_executable import Fixture
from anvil.schemas import Strict

GENERATOR_VERSION = "anvil-prose-python-v1"
MAX_BUNDLE_BYTES = 524288


class Rule(Strict):
    source_id: str = Field(min_length=1, max_length=100)
    interpretation: str = Field(min_length=10, max_length=4000)
    check_type: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=1, max_length=1000)
    tests: list[str] = Field(min_length=1, max_length=30)


class GuardAssertion(Strict):
    action_index: int = Field(ge=0, le=99, strict=True)
    expected_checks: dict[str, bool]


class GeneratedFixture(Fixture):
    guard_assertions: list[GuardAssertion] = Field(default_factory=list, max_length=100)


class Bundle(Strict):
    schema_version: str = Field(pattern=r"^anvil.generated.python.v1$")
    code: str = Field(min_length=10, max_length=100000)
    rules: list[Rule] = Field(min_length=1, max_length=60)
    fixtures: list[GeneratedFixture] = Field(min_length=4, max_length=30)
    probe_mappings: dict[str, str]
    assumptions: list[str] = Field(max_length=30)
    unresolved: list[str] = Field(max_length=30)

    @model_validator(mode="after")
    def unique(self):
        if len({r.source_id for r in self.rules}) != len(self.rules):
            raise ValueError("Duplicate generated rule mapping")
        if len({f.id for f in self.fixtures}) != len(self.fixtures):
            raise ValueError("Duplicate generated fixture ID")
        return self


SAFE_BUILTINS = (
    "abs all any bool dict enumerate float int isinstance len list max min range reversed "
    "round set sorted str sum tuple type zip"
).split()
SAFE_METHODS = {
    "get",
    "items",
    "keys",
    "values",
    "append",
    "add",
    "update",
    "index",
    "count",
    "copy",
}


def inspect_code(code):
    """Defense in depth before isolated execution; this is not a host-Python sandbox."""
    try:
        tree = ast.parse(code, filename="rules.py")
    except SyntaxError as exc:
        raise ValueError("rules.py line " + str(exc.lineno) + ": " + exc.msg) from None
    if len(list(ast.walk(tree))) > 10000:
        raise ValueError("Generated code exceeds syntax limit")
    forbidden = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.AsyncFunctionDef,
        ast.Await,
        ast.With,
        ast.AsyncWith,
        ast.Global,
        ast.Nonlocal,
        ast.Delete,
        ast.Try,
        ast.Raise,
        ast.Yield,
        ast.YieldFrom,
    )
    functions = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    if not {"evaluate", "guard", "probe"} <= functions:
        raise ValueError(
            "rules.py requires evaluate(inputs, output, events), guard(tool, arguments, inputs, events), and probe(tool, result)"
        )
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.decorator_list or node.returns:
            raise ValueError("Only undecorated function declarations are allowed at module scope")
        if node.args.defaults or node.args.kw_defaults or any(a.annotation for a in node.args.args):
            raise ValueError("Function annotations/default expressions are not supported")
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise ValueError("Prohibited Python operation: " + type(node).__name__)
        if isinstance(node, (ast.Name, ast.arg)) and "__" in (
            node.id if isinstance(node, ast.Name) else node.arg
        ):
            raise ValueError("Dunder access is prohibited")
        if isinstance(node, ast.Attribute) and node.attr not in SAFE_METHODS:
            raise ValueError("Unsupported generated-code attribute: " + node.attr)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in {*SAFE_BUILTINS, *functions}:
                raise ValueError("Unsupported generated-code call: " + node.func.id)
            if not isinstance(node.func, (ast.Name, ast.Attribute)):
                raise ValueError("Indirect generated-code calls are prohibited")
    compile(tree, "rules.py", "exec")  # Compile only; no execution on the API/worker host.


def validate_bundle(task, value):
    raw = json.dumps(value, allow_nan=False).encode()
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError("Generated bundle exceeds 512 KiB")
    bundle = Bundle.model_validate(value)
    if bundle.unresolved:
        raise ValueError("Needs clarification: " + "; ".join(bundle.unresolved))
    inspect_code(bundle.code)
    rules = {r.id for r in [*task.criteria, *task.constraints]}
    if {r.source_id for r in bundle.rules} != rules:
        raise ValueError("Every source rule needs exactly one generated mapping")
    fixtures = {f.id: f for f in bundle.fixtures}
    kinds = {f.kind for f in bundle.fixtures}
    if not {"good", "bad", "empty", "guardrail"} <= kinds:
        raise ValueError("Generate good, bad, empty and guardrail fixtures")
    if not any(f.kind == "good" and f.expected_reward_bps == 10000 for f in bundle.fixtures):
        raise ValueError("A full-reward good fixture is required")
    tools = {t.id for s in task.mcp_servers for t in s.tools}
    if set(bundle.probe_mappings) != {
        t.id for s in task.mcp_servers for t in s.tools if t.effect != "prohibited"
    }:
        raise ValueError("Every safe probe requires a generated semantic assertion mapping")
    runtime_ids = {c.id for c in task.constraints if c.phase in ("runtime", "both")}
    guard_outcomes = {key: set() for key in runtime_ids}
    for fixture in bundle.fixtures:
        if not set(fixture.expected_checks) <= rules or not set(fixture.covers) <= rules:
            raise ValueError("Unknown generated fixture rule")
        if any(c.tool not in tools for c in fixture.observed_calls):
            raise ValueError("Unknown generated fixture tool")
        if len({a.action_index for a in fixture.guard_assertions}) != len(fixture.guard_assertions):
            raise ValueError("Duplicate action guard assertion")
        for assertion in fixture.guard_assertions:
            if (
                assertion.action_index >= len(fixture.observed_calls)
                or set(assertion.expected_checks) != runtime_ids
            ):
                raise ValueError("Guard assertions must map each runtime rule and a real action")
            for key, expected in assertion.expected_checks.items():
                guard_outcomes[key].add(expected)
    if any(outcomes != {True, False} for outcomes in guard_outcomes.values()):
        raise ValueError("Every runtime/both rule requires positive and denied-action assertions")
    for rule in bundle.rules:
        if any(f not in fixtures or rule.source_id not in fixtures[f].covers for f in rule.tests):
            raise ValueError("Rule test mapping is missing coverage: " + rule.source_id)
        outcomes = {
            f.expected_checks[rule.source_id]
            for f in bundle.fixtures
            if rule.source_id in f.expected_checks
        }
        if outcomes != {True, False}:
            raise ValueError("Each rule needs positive and negative assertions: " + rule.source_id)
    return bundle


def generation_prompt(task):
    # Private supplied QA oracle is withheld: generated consistency fixtures are independent.
    source = task.model_dump(exclude={"evaluation_private"})
    source["inputs"] = [
        a.model_dump() if a.visibility == "actor" else a.model_dump(exclude={"content"})
        for a in task.inputs
    ]
    return (
        "Generate a JSON object matching the following schema. Do not use markdown. "
        "Translate all written business rules into executable deterministic Python. "
        "Do not invent missing business facts: put them in unresolved. No imports, I/O, "
        "dependencies, exceptions, classes, decorators or dunder access. Functions only. "
        "evaluate(inputs, output, events) returns {source_rule_id: bool} for ALL rules, "
        "including constraints. inputs maps actor asset paths to parsed JSON/string. "
        "events is a list of {tool,arguments,status}; output is dict or None. "
        "guard(tool, arguments, inputs, events) returns {allowed: bool, violations: [rule_id]} "
        "and checks ALL runtime/both constraints before side effects. Prohibited tool attempts fail. "
        "probe(tool, result) returns a boolean that checks the tool probe's expected_description, not just response type. "
        "probe_mappings maps every non-prohibited tool ID to its readable semantic assertion. "
        "Fixtures must include guard_assertions with action_index and expected_checks for all runtime/both constraints; "
        "each runtime constraint needs at least one allowed/compliant and one denied/noncompliant action. "
        "Private input content is not provided for generation; final evaluate receives private inputs by declared path, "
        "guard and probes cannot access private references. Never embed private expected literals in code. "
        "Use only these builtins: "
        + ",".join(SAFE_BUILTINS)
        + ". Methods allowed: "
        + ",".join(sorted(SAFE_METHODS))
        + ". Numeric tolerance must be explicit. "
        "Generate positive AND negative assertions for every rule, empty output reward zero, "
        "and a prohibited-action hard-failure fixture. All criteria/constraint IDs exactly match source. "
        "Rules map to fixture IDs; do not return fixture expected checks as evaluator code. "
        "Scoring is computed by the server from checks and source weights, not by your code.\n"
        + json.dumps(Bundle.model_json_schema())
        + "\nSOURCE\n"
        + json.dumps(source, ensure_ascii=False)
    )


def score(task, checks, output, dense_credits=None):
    ids = {r.id for r in [*task.criteria, *task.constraints]}
    if (
        not isinstance(checks, dict)
        or set(checks) != ids
        or any(type(v) is not bool for v in checks.values())
    ):
        raise ValueError("Verifier must return exactly one boolean for every source rule")
    components = {
        r.id: r.weight_bps
        if (r.phase == "dense" and (checks[r.id] or r.id in (dense_credits or set())))
        or (checks[r.id] and output is not None)
        else 0
        for r in task.criteria
    }
    penalties = {r.id: r.penalty_bps for r in task.constraints if not checks[r.id]}
    hard = [r.id for r in task.constraints if r.hard_fail and not checks[r.id]]
    total = max(0, min(10000, sum(components.values()) - sum(penalties.values())))
    return {
        "checks": checks,
        "components_bps": components,
        "penalties_bps": penalties,
        "hard_failures": hard,
        "reward_bps": 0 if hard else total,
        "pass": not hard and total >= task.pass_threshold_bps,
        "origin": "generated_software_validation",
    }


def notebook(bundle, base_revision, source_sha, actor_inputs=None):
    """Explicit download only. No private fixtures, source inputs, tokens or saved outputs."""
    metadata = {
        "anvil": {
            "base_revision_id": str(base_revision),
            "source_sha256": source_sha,
            "format": "anvil.generated.python.v1",
        },
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
    }
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": metadata,
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Anvil generated rules\nEdit the rules cell, then upload this notebook in Anvil.\n",
                    "No private inputs or reference fixtures are exported. Notebook outputs are not certification.\n",
                    "Anvil reruns validation in a fresh supplied environment. Colab: File → Upload notebook; JupyterLab: open this file.\n",
                ],
            },
            {
                "cell_type": "code",
                "id": "anvil-rules",
                "metadata": {"anvil_module": "rules.py"},
                "source": bundle.code.splitlines(keepends=True),
                "execution_count": None,
                "outputs": [],
            },
            {
                "cell_type": "code",
                "id": "anvil-empty-smoke",
                "metadata": {},
                "source": [
                    "# Optional empty-output smoke using actor-visible synthetic inputs only.\n",
                    "# Full positive/bad/guardrail cases remain on the Anvil validation worker.\n",
                    "import json\n",
                    "inputs = json.loads(" + repr(json.dumps(actor_inputs or {})) + ")\n",
                    "checks = evaluate(inputs, None, [])\n",
                    "assert isinstance(checks, dict)\n",
                    "checks\n",
                ],
                "execution_count": None,
                "outputs": [],
            },
        ],
    }


def notebook_code(value, base_revision, source_sha):
    if not isinstance(value, dict) or value.get("nbformat") != 4:
        raise ValueError("Return a valid version4 Anvil notebook")
    if len(json.dumps(value, allow_nan=False).encode()) > MAX_BUNDLE_BYTES:
        raise ValueError("Notebook exceeds 512 KiB")
    metadata = value.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("anvil"), dict):
        raise ValueError("Notebook is missing its Anvil base-version metadata")
    binding = metadata["anvil"]
    if (
        binding.get("base_revision_id") != str(base_revision)
        or binding.get("source_sha256") != source_sha
    ):
        raise ValueError("Notebook base version does not match this task revision")
    source_cells = value.get("cells")
    if not isinstance(source_cells, list) or any(
        not isinstance(c, dict) or not isinstance(c.get("metadata", {}), dict) for c in source_cells
    ):
        raise ValueError("Notebook cells must have valid cell metadata")
    cells = [
        c
        for c in source_cells
        if c.get("cell_type") == "code" and c.get("metadata", {}).get("anvil_module") == "rules.py"
    ]
    if len(cells) != 1:
        raise ValueError("Notebook requires exactly one rules.py module cell")
    source = cells[0].get("source", [])
    if not isinstance(source, str) and not (
        isinstance(source, list) and all(isinstance(line, str) for line in source)
    ):
        raise ValueError("The rules.py cell must contain text")
    code = "".join(source) if isinstance(source, list) else source
    inspect_code(code)
    return code


def package(task, bundle, report, revision_id):
    """Pinned Harbor layout. Evaluation code/fixtures never enter instructions/image."""
    from anvil.praxis_executable import actor_view

    image = (
        task.environment.digest
        if task.environment.digest_kind == "docker_image_id"
        else task.environment.image_reference.split("@")[0] + "@" + task.environment.digest
    )
    files = {
        "task.toml": 'schema_version = "1.4"\n[metadata]\norigin = "generated_executable_import"\n[agent]\ntimeout_sec = '
        + str(float(task.timeout_seconds))
        + '\nuser = "10001"\n[verifier]\ntimeout_sec = 30.0\nuser = "root"\n[environment]\ndocker_image = '
        + json.dumps(image)
        + "\nbuild_timeout_sec = 60.0\ncpus = "
        + str(task.environment.cpus)
        + "\nmemory_mb = "
        + str(task.environment.memory_mb)
        + '\nstorage_mb = 1024\nnetwork_mode = "no-network"\n',
        "instruction.md": task.instructions + "\n" + json.dumps(actor_view(task), indent=2),
        "environment/Dockerfile": "FROM " + image + "\n",
        # Native trial collection is trusted worker-side: this minimal verifier records no grade.
        "tests/test.sh": "#!/bin/sh\nset -eu\npython3 /tests/emit_grade.py\n",
        "tests/emit_grade.py": "import json\nfrom pathlib import Path\np=Path('/tests/worker-result.json')\nvalue=json.loads(p.read_text()) if p.is_file() else {'reward':0}\nreward=value['reward']\nassert type(reward) in (int,float) and 0<=reward<=1\nPath('/logs/verifier/reward.txt').write_text(str(reward))\n",
        "evaluation/verifiers/rules.py": bundle.code,
        "evaluation/fixtures.json": json.dumps(
            [f.model_dump() for f in bundle.fixtures], sort_keys=True
        ),
        "evaluation/traceability.json": json.dumps(
            [r.model_dump() for r in bundle.rules], sort_keys=True
        ),
        "evaluation/rubric.json": json.dumps(
            {
                "criteria": [r.model_dump() for r in task.criteria],
                "constraints": [r.model_dump() for r in task.constraints],
                "pass_threshold_bps": task.pass_threshold_bps,
            },
            sort_keys=True,
        ),
    }
    volumes = []
    for asset in task.inputs:
        if asset.visibility == "actor":
            files["environment/public/" + asset.path] = asset.content
            volumes.append(
                "      - type: bind\n        source: "
                + json.dumps("./public/" + asset.path)
                + "\n        target: "
                + json.dumps("/workspace/inputs/" + asset.path)
                + "\n        read_only: true\n"
            )
    files["environment/docker-compose.yaml"] = (
        "services:\n  main:\n    network_mode: none\n    read_only: true\n    cap_drop: [ALL]\n    security_opt: [no-new-privileges:true]\n    pids_limit: 64\n    user: '10001:10001'\n"
        "    tmpfs:\n      - /tmp:rw,nosuid,nodev,noexec,size=32m,uid=10001,gid=10001\n"
        "      - /workspace/output:rw,nosuid,nodev,noexec,size=16m,uid=10001,gid=10001\n"
        "      - /tests:rw,nosuid,nodev,exec,size=4m,uid=0,gid=0,mode=0700\n"
        "    volumes:\n" + "".join(volumes)
    )
    files["anvil-agent/admission.json"] = json.dumps(actor_view(task))
    manifest = {
        "schema_version": "anvil.executable.package.v1",
        "generator_version": GENERATOR_VERSION,
        "binding": "mcp-tool-agent-v1",
        "harbor_version": "0.25.0",
        "base_image": image,
        "stage_order": ["step-" + str(i) for i in range(task.max_steps)],
        "revision_id": str(revision_id),
        "task_id": task.task_id,
        "task_version": task.task_version,
        "image_digest": task.environment.digest,
        "grading": "isolated_worker_capture",
        "harbor_grade_protocol": "isolated-worker-grade-v1",
        "validation": report,
        "model_performance": False,
        "files": {p: hashlib.sha256(v.encode()).hexdigest() for p, v in files.items()},
        "bundle_sha256": digest(bundle.model_dump()),
    }
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in files.items():
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
        archive.writestr("anvil-manifest.json", json.dumps(manifest, sort_keys=True))
    return manifest, target.getvalue()
