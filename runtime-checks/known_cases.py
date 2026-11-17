"""Run real bounded installed adapters; never a model request or release approval."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

if sys.flags.optimize:
    raise RuntimeError('Optimized qualification interpreter is forbidden')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('/app'))
    parser.add_argument('--worker-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    os.environ.update(ANVIL_ENV='local', WEB_ORIGIN='http://127.0.0.1:3202', ANVIL_ROOT=str(root),
                      LANGSMITH_TRACING='false', DO_NOT_TRACK='1', OTEL_SDK_DISABLED='true')
    sys.path.insert(0, str(root / 'services/backend/src'))
    from anvil.policy_rules import Rule, evaluate_zen, evaluate_opa
    from anvil import evaluator_runtimes
    if args.worker_root:
        # Local smoke may reuse existing installs ONLY after verifying worker bytes.
        # Image qualification never supplies this override.
        other = args.worker_root.resolve()
        for name in ('local_worker.py', 'promptfoo/worker.mjs', 'promptfoo/package-lock.json'):
            relative = Path('integrations/evaluators') / name
            assert hashlib.sha256((root / relative).read_bytes()).digest() == hashlib.sha256((other / relative).read_bytes()).digest()
        evaluator_runtimes.ROOT = other
    rows = []
    versions = {'zen': importlib.metadata.version('zen-engine')}
    assert versions['zen'] == '2.1.3'
    for engine in ('opa-local', 'nemo', 'promptfoo'):
        versions[engine] = evaluator_runtimes.runtime_version(engine)
    for engine in ('zen', 'opa-local', 'nemo', 'promptfoo'):
        rule = Rule(kind='number_max', field='amount', value=100) if engine in ('zen', 'opa-local') else Rule(kind='forbidden_text', field='text', value='FORBIDDEN_LITERAL')
        cases = [('allow', {'amount': 90}, 'pass'), ('deny', {'amount': 110}, 'fail'), ('missing', {}, 'unknown')] if engine in ('zen', 'opa-local') else [('allow', {'text': 'ordinary captured output'}, 'pass'), ('deny', {'text': 'contains FORBIDDEN_LITERAL'}, 'fail'), ('missing', {}, 'unknown')]
        for name, facts, expected in cases:
            if engine == 'zen':
                result = evaluate_zen(rule, facts)
            elif engine == 'opa-local':
                result = evaluate_opa(rule, facts, os.environ['ANVIL_OPA_BINARY'],
                                      expected_sha256=os.environ['ANVIL_OPA_SHA256'])
            else:
                result = evaluator_runtimes.evaluate_library(engine, rule, facts)
            assert result['outcome'] == expected, (engine, name, result['outcome'])
            rows.append({'adapter': engine, 'case': name, 'outcome': result['outcome']})
    # Exercise the actual installed Promptfoo boundary, not just its schema.
    worker = (args.worker_root or root) / 'integrations/evaluators/promptfoo/worker.mjs'
    for name, expected in (('forbidden_file_reference', 'file:///etc/passwd'), ('forbidden_template_reference', '{{danger}}')):
        result = subprocess.run([os.environ['ANVIL_EVALUATOR_NODE'], str(worker)],
                                input=json.dumps({'kind': 'equals', 'output': 'safe', 'expected': expected}).encode(),
                                capture_output=True, timeout=30,
                                env={'PATH': '/usr/bin:/bin', 'PROMPTFOO_DISABLE_TELEMETRY': '1', 'PROMPTFOO_DISABLE_UPDATE': '1', 'PROMPTFOO_SAFE_MODE': 'true'})
        assert result.returncode != 0, 'Unsafe Promptfoo assertion unexpectedly accepted'
        rows.append({'adapter': 'promptfoo', 'case': name, 'outcome': 'rejected'})
    report = {'status': 'passed', 'versions': versions, 'checks': rows,
              'provider_calls': 0, 'scope': 'actual deterministic adapter known cases only',
              'host_worker_override': bool(args.worker_root), 'release_ready': False,
              'not_proven': ['task applicability', 'live MCP/OpenEnv persisted effects', 'native Harbor trial', 'five safety attack categories', 'model performance', 'QA image qualification']}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'checks': len(rows), 'versions': versions, 'release_ready': False}))


if __name__ == '__main__':
    main()
