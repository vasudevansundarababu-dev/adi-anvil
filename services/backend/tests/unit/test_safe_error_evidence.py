"""Error diagnostics must never disclose private exception data or affect500s."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from anvil.request_limits import safe_error_evidence

ROOT = Path('/public/first_party')


def raised(error, filename=str(ROOT / 'public_module.py')):
    namespace = {}
    exec(compile('def raise_internal(error):\n    raise error\n', filename, 'exec'), namespace)
    try:
        namespace['raise_internal'](error)
    except BaseException as caught:
        return caught


def test_secret_messages_and_external_class_names_are_never_projected():
    private_type = type('PRIVATE_CUSTOMER_IDENTIFIER', (Exception,), {})
    error = raised(private_type('token=PRIVATE_TOKEN; sql=PRIVATE_SQL'))
    result = safe_error_evidence(error, ROOT)
    raw = json.dumps(result)
    assert 'PRIVATE' not in raw and str(ROOT) not in raw
    assert result['exception_types'] == ['external_exception']
    assert result['locations'][-1]['file'] == 'public_module.py'


def test_only_exact_known_runtime_guard_is_classified():
    known = raised(RuntimeError('Software resource closure changed before commit'))
    assert safe_error_evidence(known, ROOT)['guards'] == ['software_resource_closure_changed']
    unknown = raised(RuntimeError('database password=PRIVATE_TOKEN'))
    assert safe_error_evidence(unknown, ROOT)['guards'] == ['unclassified']


def test_external_paths_and_functions_are_not_reported():
    error = raised(RuntimeError('PRIVATE_TOKEN'), '/private/customers/PRIVATE_ACCOUNT/secret.py')
    result = safe_error_evidence(error, ROOT)
    assert result['locations'] == []
    assert 'PRIVATE' not in json.dumps(result)
    traversal = raised(RuntimeError('PRIVATE_TOKEN'), str(ROOT / '..' / 'private_module.py'))
    assert safe_error_evidence(traversal, ROOT)['locations'] == []


def test_custom_exception_stringification_is_never_called():
    class PrivateError(Exception):
        def __str__(self):
            raise AssertionError('private stringification must not execute')

    result = safe_error_evidence(raised(PrivateError('PRIVATE_TOKEN')), ROOT)
    assert result['exception_types'] == ['external_exception']


def test_runtime_error_with_nontext_private_argument_is_not_stringified():
    class PrivateArgument:
        def __str__(self):
            raise AssertionError('private argument stringification must not execute')

    result = safe_error_evidence(raised(RuntimeError(PrivateArgument())), ROOT)
    assert result['guards'] == ['unclassified']


def test_nested_groups_cycles_depth_and_encoded_output_are_bounded():
    error = raised(RuntimeError('PRIVATE_TOKEN'))
    for _ in range(20):
        parent = raised(ExceptionGroup('PRIVATE_GROUP', [error, error, ValueError('PRIVATE_SQL')]))
        parent.__cause__ = error
        error = parent
    error.__context__ = error
    result = safe_error_evidence(error, ROOT)
    assert len(result['exception_types']) <= 4
    assert len(result['locations']) <= 8
    assert len(json.dumps(result, separators=(',', ':')).encode()) <= 2048
    assert 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('failure', ['projection', 'logger'])
def test_logging_or_projection_failure_preserves_original_generic_response(monkeypatch, failure):
    from anvil import api

    def broken(*args, **kwargs):
        raise RuntimeError('PRIVATE_LOGGER_TOKEN')

    if failure == 'projection':
        monkeypatch.setattr(api, 'safe_error_evidence', broken)
    else:
        monkeypatch.setattr(api.logging.getLogger('anvil.api'), 'error', broken)

    async def endpoint(request):
        raise RuntimeError('PRIVATE_ENDPOINT_TOKEN')

    response = asyncio.run(api.security_headers(SimpleNamespace(state=SimpleNamespace()), endpoint))
    assert response.status_code == 500
    body = json.loads(response.body)
    assert body['error']['code'] == 'internal_error'
    assert body['error']['retryable'] is False
    assert body['error']['request_id'] == response.headers['X-Request-ID']
    assert 'PRIVATE' not in response.body.decode()


def test_actual_error_log_keeps_only_safe_metadata_and_request_correlation(caplog):
    from anvil import api

    async def endpoint(request):
        raise RuntimeError('PRIVATE_ENDPOINT_TOKEN and PRIVATE_SQL')

    response = asyncio.run(api.security_headers(SimpleNamespace(state=SimpleNamespace()), endpoint))
    record = next(item for item in caplog.records if item.name == 'anvil.api')
    assert record.exc_info is None and record.stack_info is None
    assert 'PRIVATE' not in record.getMessage()
    assert response.headers['X-Request-ID'] in record.getMessage()
    evidence = json.loads(record.args[-1])
    assert evidence['locations'][0]['file'] == 'api.py'
    assert len(json.dumps(evidence).encode()) <= 2048
