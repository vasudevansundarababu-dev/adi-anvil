"""Public actionable validation diagnostics; never private registry/source rows."""

DETAILS = {
    'AV_TEMPLATE_NOT_REGISTERED': ('template_registration', 'The exact template version and hash are not registered in Gym.', 'Register the exact published template in this project.'),
    'AV_TEMPLATE_INTEGRITY_REQUIRED': ('template_registration', 'The stored template failed its integrity checks.', 'Repair the Gym registry integrity issue; do not rewrite approved task assets.'),
    'AV_TEMPLATE_NOT_QUALIFIED': ('template_qualification', 'The exact template has no current qualifying Gym receipt.', 'Gym must qualify this exact template against its currently installed runtime and project bindings.'),
    'AV_TEMPLATE_QUALIFICATION_REVOKED': ('template_qualification', 'The template qualification has been revoked.', 'Gym must resolve the revocation and produce a genuine current qualification.'),
    'AV_EXPORT_CONTRACT_UNSUPPORTED': ('contract_negotiation', 'Gym cannot evaluate this export under the selected template contract.', 'Negotiate a supported published contract; do not silently change the package.'),
    'AV_PRIVATE_STORAGE_ASSIGNMENT_REQUIRED': ('private_storage', 'The project lacks a protected benchmark-reference storage assignment.', 'Gym must assign protected storage before resolution.'),
    'AV_PRIVATE_STORAGE_UNAVAILABLE': ('private_storage', 'Protected reference storage is unavailable.', 'Gym must restore protected storage and reconcile any uncertain resolution before retrying.'),
}


def binding_assessment(connection, project, result):
    """Read existing Gym setup; never expose its dataset identities to Authoring."""
    if result.get('valid') is not True:
        return {'status': 'not_assessed', 'execution_setup_ready': False,
                'owner': 'anvil', 'reason': 'source_validation_must_complete_first',
                'paid_dispatch_authorized': False}
    package = result.get('package_sha256')
    if not package:
        return {'status': 'not_assessed', 'execution_setup_ready': False,
                'owner': 'anvil', 'reason': 'exact_package_identity_required',
                'paid_dispatch_authorized': False}
    rows = connection.execute(
        "SELECT id FROM anvil.benchmark_task_groups WHERE project_id=%s "
        "AND content#>>'{source_origin,kind}'='praxis_authored_batch' "
        "AND EXISTS (SELECT 1 FROM jsonb_array_elements("
        "coalesce(content#>'{source_origin,packages}','[]'::jsonb)) p "
        "WHERE p->>'sha256'=%s) ORDER BY created_at DESC,id LIMIT 2",
        (project, package),
    ).fetchall()
    if len(rows) != 1:
        return {'status': 'blocked', 'execution_setup_ready': False, 'owner': 'anvil',
                'reason': 'gym_import_and_bindings_required' if not rows else 'gym_binding_selection_required',
                'paid_dispatch_authorized': False}
    from fastapi import HTTPException

    from anvil.project_bindings import readiness

    try:
        current = readiness(connection, project, rows[0]['id'])
    except HTTPException as exc:
        if exc.status_code not in (404, 409, 422):
            raise
        return {'status': 'blocked', 'execution_setup_ready': False, 'owner': 'anvil',
                'reason': 'gym_binding_assessment_blocked', 'paid_dispatch_authorized': False}
    gaps = [{'code': gap['code'], 'section': gap.get('section'), 'owner': 'anvil'}
            for gap in current.get('gaps', [])[:100]]
    return {'status': 'ready_for_run_configuration' if current['ready'] else 'blocked',
            'execution_setup_ready': current['ready'], 'owner': 'anvil',
            'gaps': gaps, 'gaps_truncated': len(current.get('gaps', [])) > 100,
            'paid_dispatch_authorized': False}


def report(result, request_id, setup=None):
    """Additive response metadata; validity and admission semantics stay unchanged."""
    validity = result.get('valid')
    items = []
    for requirement in result.get('anvil_requirements', []):
        code = requirement['code']
        stage, message, fix = DETAILS.get(code, (
            'gym_preparation', 'A Gym-owned prerequisite is unresolved.',
            'Gym must resolve this requirement code; preserve the exact package for reconciliation.'))
        item = {key: requirement[key] for key in ('code', 'owner', 'status', 'task_id') if key in requirement}
        item.update(stage=stage, message=message, fix=fix, task_change_requested=False)
        qualification = requirement.get('qualification')
        if isinstance(qualification, dict):
            item['qualification'] = {key: qualification[key] for key in
                                    ('status', 'reason_codes', 'recorded_status', 'receipt_sha256')
                                    if key in qualification}
        items.append(item)
    return result | {
        'request_id': request_id,
        'validation_report': {
            'schema_version': 'anvil.validation-report.v1',
            'status': result['status'],
            'verdict': 'invalid' if validity is False else 'blocked' if validity is None else 'valid',
            'task_conformance': 'not_evaluated' if validity is None else 'failed' if validity is False else 'passed',
            'task_fix_required': True if validity is False else None if validity is None else False,
            'blocking_items': items,
            'review_gates': result.get('review_gates', []),
            'run_authority': result.get('run_authority', 'not_granted'),
            'paid_calls': False,
            'anvil_setup': setup or {'status': 'not_assessed', 'execution_setup_ready': False,
                                     'owner': 'anvil', 'paid_dispatch_authorized': False},
        },
    }
