"""One-Trial integrity reuse must never outlive its immutable admission."""

import copy
import os
import time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from anvil import environment_harbor as native
from anvil.golden_native_mediated import ImmutableRuntimeTrial, MediatedPlan


@pytest.fixture
def trial(monkeypatch):
    plan = MediatedPlan(Path('/synthetic/attempt.json'), 'a' * 64)
    body = {"request": {"original_deadline_monotonic": time.monotonic() + 120},
            "assets": {"runtime_seal": {"components": {}}, "host_image_custody": {"sdk_profile": {"image": "fixed"}}}}
    monkeypatch.setattr(MediatedPlan, 'body', lambda self: body)
    store = Mock()
    store.__enter__ = Mock(return_value=store)
    store.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(native, 'operator_proof_module', lambda: SimpleNamespace(OperatorProofStore=lambda root: store))
    monkeypatch.setattr(native, 'fixed_alarm', lambda seconds: nullcontext())
    monkeypatch.setattr(ImmutableRuntimeTrial, '_mounts', staticmethod(lambda: 'mounts'))
    def readonly(self, store, seal):
        self.roots = ()
        return True
    monkeypatch.setattr(ImmutableRuntimeTrial, '_readonly', readonly)
    return plan, body, store


def test_four_fresh_boundaries_use_two_full_scans_and_close(trial):
    plan, body, store = trial
    with ImmutableRuntimeTrial(plan) as proof:
        for _ in range(4):
            assert proof.admit(plan, body['assets']['runtime_seal'])
        assert store.validate_runtime_seal.call_count == 1
    assert store.validate_runtime_seal.call_count == 2
    assert proof.receipt()['callback_boundaries'] == 4
    with pytest.raises(ValueError):
        proof.admit(plan, body['assets']['runtime_seal'])
    with pytest.raises(ValueError):
        proof.__enter__()


@pytest.mark.parametrize('fault', ['plan', 'seal', 'pid', 'deadline', 'mounts', 'readonly'])
def test_changed_original_binding_is_refused(trial, monkeypatch, fault):
    plan, body, _ = trial
    proof = ImmutableRuntimeTrial(plan).__enter__()
    other, seal = plan, copy.deepcopy(body['assets']['runtime_seal'])
    if fault == 'plan':
        other = MediatedPlan(plan.path, plan.sha256)
    elif fault == 'seal':
        seal['extra'] = True
    elif fault == 'pid':
        proof.pid += 1
    elif fault == 'deadline':
        proof.deadline = time.monotonic() - 1
    elif fault == 'mounts':
        monkeypatch.setattr(ImmutableRuntimeTrial, '_mounts', staticmethod(lambda: 'changed'))
    else:
        proof.roots = (Path('/synthetic'),)
        monkeypatch.setattr(os, 'statvfs', lambda path: SimpleNamespace(f_flag=0))
    with pytest.raises(ValueError):
        proof.admit(other, seal)
    proof.__exit__(RuntimeError, RuntimeError('abort'), None)
    assert proof.state == 'failed'


def test_writable_closure_never_admits_reuse(trial, monkeypatch):
    plan, body, store = trial
    monkeypatch.setattr(ImmutableRuntimeTrial, '_readonly', lambda *args: False)
    with ImmutableRuntimeTrial(plan) as proof:
        assert not proof.admit(plan, body['assets']['runtime_seal'])
    assert store.validate_runtime_seal.call_count == 2
    assert not proof.receipt()['readonly_reuse']


@pytest.mark.parametrize('fault', ['hash', 'expired'])
def test_final_failure_prevents_success_receipt(trial, fault):
    plan, _, store = trial
    proof = ImmutableRuntimeTrial(plan).__enter__()
    if fault == 'hash':
        store.validate_runtime_seal.side_effect = ValueError('source changed')
    else:
        proof.deadline = time.monotonic() - 1
    with pytest.raises(ValueError):
        proof.__exit__(None, None, None)
    with pytest.raises(ValueError):
        proof.receipt()
    assert proof.state == 'failed'


def test_original_failure_is_preserved_without_acceptance(trial):
    plan, _, store = trial
    with pytest.raises(RuntimeError, match='original failure'):
        with ImmutableRuntimeTrial(plan) as proof:
            raise RuntimeError('original failure')
    assert proof.state == 'failed'
    assert store.validate_runtime_seal.call_count == 1


def test_subclass_cannot_mint_admission(trial):
    plan, _, _ = trial
    class Forged(ImmutableRuntimeTrial):
        pass
    with pytest.raises(ValueError):
        Forged(plan).__enter__()


def test_source_mirror_nested_writable_mount_disables_reuse(tmp_path, monkeypatch):
    mirror = tmp_path / 'services/backend/src/anvil'
    mirror.mkdir(parents=True)
    nested = mirror / 'nested.py'
    nested.write_text('synthetic')
    installed = tmp_path / 'installed'
    installed.mkdir()
    record = {key: str(installed) for key in ('prefix', 'site_packages', 'stdlib_root', 'interpreter')}
    record['source_packages'] = {'anvil': str(installed)}
    store = SimpleNamespace(repository=tmp_path, _runtime_install_readonly=lambda record: True)
    monkeypatch.setattr(os, 'statvfs', lambda path: SimpleNamespace(f_flag=0 if path == nested else os.ST_RDONLY))
    proof = ImmutableRuntimeTrial(MediatedPlan(tmp_path / 'plan', 'a' * 64))
    assert not proof._readonly(store, {'components': {'backend': record}})
