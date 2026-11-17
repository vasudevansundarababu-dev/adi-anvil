"""Pure opening-program comparisons; no launch, qualification or task mutation."""

import json

from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical, _digest
from anvil.marketing_native_renderer import _schedule
from anvil.marketing_task2_contract import WIRE_ROLES


def validate_opening_program(request, program):
    if type(program) is not dict or type(program.get('role_ids')) is not list:
        raise ValueError('marketing_exact_opening_program_required')
    roles = program['role_ids']
    if (len(roles) != 5 or any(type(role) is not str for role in roles)
            or set(roles) != set(WIRE_ROLES)):
        raise ValueError('marketing_original_opening_roles_required')
    value = json.loads(request.canonical_bytes)
    expected = _schedule(value, {'roles': [{'id': role} for role in roles]}, opening=True)
    if (_bounded_canonical(program, DOCUMENT_CAP) != _bounded_canonical(expected, DOCUMENT_CAP)
            or _digest(program) != value['schedule_sha256']):
        raise ValueError('marketing_original_opening_program_hash_required')
    return value['schedule_sha256']
