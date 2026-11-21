"""Exercise FastAPI's JSON-to-Python boundary, not model_validate_json alone."""

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from anvil.golden_kyc_policy_registry import ReceiptReference
from anvil.project_bindings import NativePreparation


def client():
    app = FastAPI()

    @app.post('/prepare')
    def prepare(body: NativePreparation):
        return body.model_dump(mode='json')

    return TestClient(app)


BODY = {'max_model_calls': 3, 'resolved_input': {
    'id': '00000000-0000-4000-8000-000000000001', 'sha256': 'a' * 64}}


def test_json_reference_reaches_preparation_with_exact_identity_and_hash():
    response = client().post('/prepare', json=BODY)
    assert response.status_code == 200
    assert response.json() == BODY
    # The strict registry object has not been relaxed to accept transport types.
    with pytest.raises(ValidationError):
        ReceiptReference.model_validate(BODY['resolved_input'])


@pytest.mark.parametrize(('field', 'value'), [
    ('id', 'not-a-uuid'), ('id', 123), ('sha256', 'a' * 63),
    ('sha256', 'A' * 64), ('authority', 'approved'),
])
def test_invalid_or_authority_bearing_references_never_reach_preparation(field, value):
    body = deepcopy(BODY)
    body['resolved_input'][field] = value
    assert client().post('/prepare', json=body).status_code == 422


@pytest.mark.parametrize('turns', [True, '3', 0, 101, 3.5])
def test_turn_limit_remains_a_strict_bounded_integer(turns):
    body = deepcopy(BODY)
    body['max_model_calls'] = turns
    assert client().post('/prepare', json=body).status_code == 422
