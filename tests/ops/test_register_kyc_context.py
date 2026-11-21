"""Reject context tampering and cross-project registration before writes."""
from copy import deepcopy
from pathlib import Path

import pytest

from anvil.db import digest
from anvil.golden_kyc_data import generate


@pytest.fixture
def registrar(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts'))
    import register_kyc_context

    return register_kyc_context


@pytest.fixture
def population():
    manifest, apps, controls = generate()
    rows, children, scenarios, lineage = [], [], [], []
    for app, control in zip(apps, controls, strict=True):
        service = {k: v for k, v in control.items()
                   if k not in ('intended_decision', 'independent_expectation_review')}
        child = deepcopy(app)
        child.update(revision=2, assessment_date='2026-11-12',
                     charter_applicability={'profile': 'national-occ-ny-test', 'reviewed': False})
        rows.append({'id': app['id'], 'snapshot': app, 'snapshot_sha256': digest(app), 'controls': service})
        children.append(child)
        scenarios.append(service | {'snapshot_sha256': digest(child)})
        lineage.append({'application_id': app['id'], 'parent_sha256': digest(app), 'child_sha256': digest(child)})
    files = {'context.json': {'parent_population_sha256': manifest['public_sha256']},
             'actor-input.json': {'applications': children},
             'private/scenarios.json': scenarios, 'lineage.json': lineage}
    return files, rows, manifest


def test_actual_parent_controls_and_immutable_lineage_match(registrar, population):
    files, rows, manifest = population
    registrar.checked_parent(files, rows, manifest)


@pytest.mark.parametrize('mutation', ['omitted', 'order', 'snapshot', 'lineage', 'response', 'future', 'parent_control'])
def test_refuses_changed_parent_or_private_behavior(registrar, population, mutation):
    files, rows, manifest = deepcopy(population)
    if mutation == 'omitted':
        rows.pop()
    elif mutation == 'order':
        rows.reverse()
    elif mutation == 'snapshot':
        rows[0]['snapshot']['purpose'] = 'altered'
    elif mutation == 'lineage':
        files['lineage.json'][0]['parent_sha256'] = '0' * 64
    elif mutation == 'response':
        files['private/scenarios.json'][0]['response_mode'] = 'none-or-other-altered-mode'
    elif mutation == 'future':
        files['private/scenarios.json'][0]['future_documents'] = [{'fabricated': True}]
    else:
        rows[0]['controls']['pattern'] = 'altered'
    with pytest.raises(ValueError):
        registrar.checked_parent(files, rows, manifest)


def test_cross_project_context_rejected_before_identity_or_database(registrar):
    project = 'a7454c18-602e-4907-bdd9-277067c36233'
    other = '00000000-0000-0000-0000-000000000001'
    with pytest.raises(ValueError, match='another project'):
        registrar.register(None, project, other, other, '0' * 64,
                           {'context.json': {'parent_project_id': other}}, '0' * 64)
