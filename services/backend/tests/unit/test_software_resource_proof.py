"""Operation-local byte reuse must never cache authority or escape rollback."""

import os
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from threading import Thread

import pytest

from anvil import evaluator_configurations as evaluators
from anvil import golden_kyc_anvil as golden
from anvil import golden_kyc_source as source
from anvil import software_resource_proof as resources


@pytest.fixture
def measured(tmp_path, monkeypatch):
    path = tmp_path / "code.py"
    path.write_text("value = 1\n")
    scans = []
    monkeypatch.setattr(resources.resources, "qualification_root", lambda: scans.append(True) or tmp_path)
    monkeypatch.setattr(source, "_source_paths", lambda root: [root / "code.py"])
    monkeypatch.setattr(evaluators, "_source_paths", lambda adapter: ["code.py"])
    return path, scans


def test_fifty_configurations_reuse_bytes_but_two_full_scans_per_operation(measured):
    _, scans = measured
    connection = object()
    for _ in range(2):
        with resources.software_resources(connection) as proof:
            expected = source.source_hash(_resource_proof=proof)
            for _ in range(50):
                assert source.source_hash(_resource_proof=proof) == expected
                for adapter in ("zen", "builtin", "opa-local"):
                    assert len(evaluators.adapter_source_sha256(adapter, _resource_proof=proof)) == 64
            with pytest.raises(FrozenInstanceError):
                proof._active = False
            with pytest.raises(TypeError):
                proof._digests["code.py"] = "0" * 64
    assert len(scans) == 4
    with pytest.raises(RuntimeError, match="Inactive"):
        source.source_hash(_resource_proof=proof)


@pytest.mark.parametrize("mutation", ["bytes", "same_bytes_restored", "mode", "inode", "symlink"])
def test_mutation_rejected_before_success_even_restored_mtime(measured, mutation):
    path, _ = measured
    original = path.stat()
    with pytest.raises(RuntimeError):
        with resources.software_resources(object()) as proof:
            resources.checked_sha256(proof, "code.py")
            if mutation in {"bytes", "same_bytes_restored"}:
                path.write_text("value = 2\n")
                if mutation == "same_bytes_restored":
                    path.write_text("value = 1\n")
                os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
            elif mutation == "mode":
                path.chmod(0o600 if original.st_mode & 0o077 else 0o644)
            elif mutation == "inode":
                new = path.with_suffix(".replacement")
                new.write_bytes(path.read_bytes())
                new.replace(path)
            else:
                target = path.with_suffix(".target")
                path.rename(target)
                path.symlink_to(target)
    with pytest.raises(RuntimeError, match="Inactive"):
        proof.root()


def test_exception_foreign_process_thread_connection_expiry_and_forgery(measured, monkeypatch):
    with resources.software_resources(object()) as proof:
        with pytest.raises(RuntimeError, match="Foreign.*connection"):
            resources.check_connection(proof, object())
        with pytest.raises(RuntimeError, match="Exact"):
            resources.checked_root(type("Forged", (), {"root": lambda self: proof._root})())
        failures = []

        def foreign_thread():
            try:
                proof.root()
            except RuntimeError:
                failures.append(True)

        thread = Thread(target=foreign_thread)
        thread.start()
        thread.join()
        assert failures == [True]
        with monkeypatch.context() as patch:
            patch.setattr(resources.os, "getpid", lambda: proof._pid + 1)
            with pytest.raises(RuntimeError, match="foreign"):
                proof.root()
        with monkeypatch.context() as patch:
            patch.setattr(resources.time, "monotonic", lambda: proof._deadline)
            with pytest.raises(RuntimeError, match="Inactive"):
                proof.root()
    with pytest.raises(KeyboardInterrupt):
        with resources.software_resources(object()) as proof:
            raise KeyboardInterrupt
    with pytest.raises(RuntimeError, match="Inactive"):
        proof.root()


def test_final_loader_scan_failure_rolls_back_before_registration_return(measured, monkeypatch):
    events = []

    class Connection:
        @contextmanager
        def transaction(self):
            events.append("savepoint")
            try:
                yield
            except BaseException:
                events.append("rollback")
                raise
            events.append("commit")

    def register(*args, **kwargs):
        events.append("writes")
        return {"software": "candidate"}

    scans = []

    def verify():
        scans.append(True)
        if len(scans) == 2:
            raise RuntimeError("late-loaded module changed")
        return measured[0].parent

    monkeypatch.setattr(resources.resources, "qualification_root", verify)
    monkeypatch.setattr(golden, "_register", register)
    with pytest.raises(RuntimeError, match="late-loaded"):
        golden.register(Connection(), "project", "user", "pack")
    assert events == ["savepoint", "writes", "rollback"]


def test_software_validation_is_explicit_and_default_run_validation_has_no_proof(measured, monkeypatch):
    calls = []

    @contextmanager
    def transaction():
        calls.append("savepoint")
        yield
        calls.append("commit")

    connection = type("Connection", (), {"transaction": staticmethod(transaction)})()
    monkeypatch.setattr(golden, "_validate", lambda c, row, **kw: calls.append(kw))
    golden.validate(connection, {})
    assert calls == [{}]
    golden.validate_software(connection, {})
    assert calls[1] == "savepoint" and calls[-1] == "commit"
    proof = calls[2]["_resource_proof"]
    with pytest.raises(RuntimeError, match="Inactive"):
        proof.root()
